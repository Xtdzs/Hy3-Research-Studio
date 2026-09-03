"""Hy3-as-judge：单次调用输出 7 维评分。

工程约束：
- temperature=0，输出 JSON schema 固定
- 解析失败重试 2 次；仍失败则落盘标记，绝不静默丢弃
- 兼容模型把 JSON 包在 ```json 代码块 / 前后带散文的情况
- 缓存：同一 (task_id, system, content_hash) 不重复调用
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .. import rate_limit
from ..env import load_dotenv
from ..schema import Answer, RubricScore, Task
from . import rubric

_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)
_VALID = {"D1", "D2", "D3", "D4", "D5", "D6", "D7"}
_CHUNKABLE = {"T1", "T2", "T6"}   # [DeepResearchEval] 页级评测适用的长文任务族


def split_chunks(content: str, max_chars: int = 2200, max_chunks: int = 6) -> list[str]:
    """按标题/空行把长报告切块（[DeepResearchEval] 以"页"为基本单元的思想）。

    规则：优先按 "## " / "# " 标题切；没有标题则按空行分段；
    单段过长再按句子边界硬切。返回前 max_chunks 块。
    """
    text = (content or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    import re as _re
    parts = _re.split(r"\n(?=#{1,3} )", text)
    if len(parts) == 1:
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    out: list[str] = []
    for p in parts:
        if len(p) > max_chars:
            sentences = _re.split(r"(?<=[。．.!?！？])", p)
            buf = ""
            for s in sentences:
                if len(buf) + len(s) > max_chars and buf:
                    out.append(buf.strip())
                    buf = s
                else:
                    buf += s
            if buf.strip():
                out.append(buf.strip())
        else:
            out.append(p.strip())
    return out[:max_chunks]


def _load_env() -> None:
    """加载 .env（搜索顺序见 scholarbench/env.py）。"""
    load_dotenv()


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    for cand in (text,):
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            pass
    m = _JSON_FENCE.search(text)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    if start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    raise ValueError(f"无法解析 judge 输出：{text[:200]}")


class Judge:
    """LLM-as-judge。可用任意 OpenAI 兼容模型（默认 Hy3）。"""

    def __init__(self, model: str | None = None, cache_dir: str | Path | None = None,
                 verbose: bool = False, chunked: bool = False,
                 max_chunks: int = 6) -> None:
        _load_env()
        from openai import OpenAI  # noqa: PLC0415
        self.model = model or os.getenv("JUDGE_MODEL") or os.getenv("HY3_MODEL", "hy3")
        self.client = OpenAI(
            api_key=os.getenv("HY3_API_KEY", ""),
            base_url=os.getenv("HY3_BASE_URL", "https://tokenhub.tencentmaas.com/v1"),
            timeout=float(os.getenv("HY3_TIMEOUT", "300")),
        )
        # 关闭思考链（HY3_DISABLE_THINKING=1）：7 维评分更快更省；
        # glm 等"始终思考"模型发送该参数会 400，_chat_create 内自动降级。
        self.disable_thinking = os.getenv("HY3_DISABLE_THINKING", "0").lower() \
            in ("1", "true", "yes", "on")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.verbose = verbose
        self.chunked = chunked                      # [DeepResearchEval] 分块评测
        self.max_chunks = max_chunks
        self.calls = 0
        self.tokens = 0

    def _chat_create(self, kw: dict) -> Any:
        """带 thinking 关闭与全局节拍的模型调用。

        - 请求前过全局限速器（间隔 + 429 冷却，与生成阶段同一节拍）；
        - 429 交给外层 score 的 retries 重试，每次重试前会自动等待冷却；
        - 模型不支持 thinking 关闭（如 glm）时去掉参数重试一次。
        """
        while True:
            rate_limit.wait_before_request()
            try:
                return self.client.chat.completions.create(**kw)
            except Exception as exc:  # noqa: BLE001
                err = str(exc)
                if rate_limit.is_rate_error(err):
                    cool = rate_limit.on_429()
                    if self.verbose:
                        print(f"  [judge] 429，全局冷却约 {cool:.0f}s")
                    raise
                if kw.get("extra_body") and any(
                    k in err for k in ("始终思考", "不支持关闭")
                ):
                    kw.pop("extra_body", None)  # 强制思考模型：去掉参数重试
                    continue
                raise

    # -- 缓存 ---------------------------------------------------------------
    def _cache_key(self, task: Task, answer: Answer) -> str:
        h = hashlib.sha1(
            (task.task_id + "|" + self.model + "|" + answer.content[:4000]).encode("utf-8")
        ).hexdigest()[:20]
        return h

    def _read_cache(self, key: str) -> list[RubricScore] | None:
        if not self.cache_dir:
            return None
        p = self.cache_dir / f"{key}.json"
        if p.exists():
            try:
                return [RubricScore(**d) for d in json.loads(p.read_text(encoding="utf-8"))]
            except Exception:  # noqa: BLE001
                return None
        return None

    def _write_cache(self, key: str, scores: list[RubricScore]) -> None:
        if not self.cache_dir:
            return
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / f"{key}.json").write_text(
            json.dumps([s.__dict__ for s in scores], ensure_ascii=False), encoding="utf-8"
        )

    # -- 主入口 -------------------------------------------------------------
    def score(self, task: Task, answer: Answer, key: dict | None = None,
              retries: int = 2) -> list[RubricScore]:
        if not answer.ok:
            return [RubricScore(dim=d, score=1.0, reason="回答为空或生成失败", quote="")
                    for d in rubric.DIM_ORDER]
        ck = self._cache_key(task, answer)
        cached = self._read_cache(ck)
        if cached:
            return cached
        if self.chunked and task.family in _CHUNKABLE and len(answer.content) > 2400:
            return self._score_chunked(task, answer, key, retries)
        return self._score_single(task, answer, key, retries, ck)

    def _score_single(self, task: Task, answer: Answer, key: dict | None,
                      retries: int, ck: str) -> list[RubricScore]:
        """单次（单块）评分的核心逻辑。"""
        prompt = rubric.build_judge_prompt(task, answer, key or {})
        kw: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": rubric.JUDGE_SYSTEM},
                {"role": "user", "content":
                 f"{self._rubric_block(task)}\n\n{prompt}"},
            ],
            "temperature": 0.0,
        }
        if self.disable_thinking:
            kw["extra_body"] = {"thinking": {"type": "disabled"}}
        last_err = ""
        for attempt in range(retries + 1):
            try:
                resp = self._chat_create(kw)
                if resp.usage:
                    self.tokens += resp.usage.total_tokens
                self.calls += 1
                data = _extract_json(resp.choices[0].message.content or "")
                scores = self._normalize(data)
                self._write_cache(ck, scores)
                if self.verbose:
                    print(f"  [judge] {task.task_id} -> " +
                          " ".join(f"{s.dim}:{s.score}" for s in scores))
                return scores
            except Exception as exc:  # noqa: BLE001
                last_err = f"{type(exc).__name__}: {exc}"
                if self.verbose:
                    print(f"  [judge] {task.task_id} attempt {attempt+1} 失败: {last_err}")
        # 全部重试失败：落盘标记，返回可识别的失败分
        scores = [RubricScore(dim=d, score=0.0, reason=f"judge 失败：{last_err}", quote="")
                  for d in rubric.DIM_ORDER]
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            (self.cache_dir / f"FAILED_{ck}.json").write_text(
                json.dumps({"task_id": task.task_id, "system": answer.system,
                            "error": last_err}, ensure_ascii=False), encoding="utf-8")
        return scores

    def _score_chunked(self, task: Task, answer: Answer, key: dict | None,
                       retries: int) -> list[RubricScore]:
        """[DeepResearchEval] 分块评测：逐块评分，按块字符数加权合并。

        长报告一次 judge 会把 D5（逻辑）D7（可读性）D4（覆盖）摊平到全篇；
        分块后每块的逻辑与可读性被单独检验，等价于论文的"页级自适应评分"。
        """
        chunks = split_chunks(answer.content, max_chunks=self.max_chunks)
        if len(chunks) <= 1:
            ck = self._cache_key(task, answer)
            return self._score_single(task, answer, key, retries, ck)

        weights, all_scores = [], []
        for i, chunk in enumerate(chunks):
            sub = Answer(task_id=f"{task.task_id}#c{i+1}", system=answer.system,
                         content=chunk, citations=answer.citations,
                         tool_calls=list(answer.tool_calls), meta=answer.meta)
            ck = self._cache_key(task, sub)
            scores = self._read_cache(ck)
            if scores is None:
                scores = self._score_single(task, sub, key, retries, ck)
            weights.append(len(chunk))
            all_scores.append(scores)

        merged: dict[str, list[tuple[float, float]]] = defaultdict(list)
        for w, scores in zip(weights, all_scores):
            for s in scores:
                merged[s.dim].append((s.score, w))
        wsum = sum(weights)
        out = []
        for dim in rubric.DIM_ORDER:
            if dim not in merged:
                continue
            avg = sum(sc * w for sc, w in merged[dim]) / max(1, wsum)
            reasons = "；".join(s.reason for s in
                                [sc for w, scs in zip(weights, all_scores)
                                 for sc in scs if sc.dim == dim and sc.quote][:2])
            out.append(RubricScore(dim=dim, score=round(avg, 2),
                                   reason=reasons[:300] or "分块加权合并", quote=""))
        self._write_cache(self._cache_key(task, answer), out)
        return out

    @staticmethod
    def _rubric_block(task: Task) -> str:
        w = rubric.weights_for(task.family)
        lines = ["# Rubric（1-5 分锚点）", rubric.dims_text()]
        lines.append("# 本任务族权重：" +
                     ", ".join(f"{k}={v:.2f}" for k, v in sorted(w.items())))
        return "\n".join(lines)

    @staticmethod
    def _normalize(data: dict) -> list[RubricScore]:
        raw = data.get("scores") or []
        out: list[RubricScore] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            dim = str(item.get("dim", "")).strip().upper()
            if dim not in _VALID or dim in seen:
                continue
            try:
                sc = float(item.get("score", 0))
            except (TypeError, ValueError):
                continue
            sc = max(1.0, min(5.0, sc))
            seen.add(dim)
            out.append(RubricScore(dim=dim, score=sc,
                                   reason=str(item.get("reason", ""))[:300],
                                   quote=str(item.get("quote", ""))[:300]))
        if not out:
            raise ValueError("judge 未返回任何有效维度")
        return out
