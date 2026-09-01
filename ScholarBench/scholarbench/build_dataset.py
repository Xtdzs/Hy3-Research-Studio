"""数据集构建：从种子题库 + 公开元数据生成 scholarbench 数据文件。

    python -m scholarbench.build_dataset      # 仅用种子库 + 本地 gold 池快照（无需联网）

产出：
    data/v0.1/T*.jsonl              题目（公开）
    data/v0.1/keys_heldout/T*.json  答案锚点（不公开，抗污染）
    data/v0.1/gold_pools/T3-*.json  T3 的 gold 文献池快照
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from . import seedbank as sb
from .dataset import DATA_ROOT, VERSION, version_dir
from .schema import FAMILY_CAPABILITIES, Task, write_jsonl


# --- T1 / T2 ---------------------------------------------------------------
def build_t1t2() -> tuple[list[Task], dict]:
    tasks: list[Task] = []
    keys: dict = {}
    for seeds, family in ((sb.T1_SEEDS, "T1"), (sb.T2_SEEDS, "T2")):
        for s in seeds:
            t = Task(task_id=s["id"], family=family, suite=f"{family}_survey"
                     if family == "T1" else f"{family}_proposal",
                     difficulty=s["d"], prompt=s["q"],
                     context={"depth": "quick" if s["d"] == "easy" else "standard"})
            tasks.append(t)
            keys[s["id"]] = {"key_points": s["kp"], "redlines": s.get("redlines", []),
                             **({"experiment_elements": s["elems"]} if family == "T2" else {})}
    return tasks, keys


# --- T3 学术检索 -----------------------------------------------------------
def build_t3() -> tuple[list[Task], dict]:
    tasks: list[Task] = []
    keys: dict = {}
    pool_dir = version_dir() / "gold_pools"
    pool_dir.mkdir(parents=True, exist_ok=True)

    for s in sb.T3_SEEDS:
        t = Task(task_id=s["id"], family="T3", suite="T3_search",
                 difficulty=s["d"], prompt=s["q"],
                 context={"per_query": 10, "top_k": 20})
        tasks.append(t)

        # 仅使用本地 gold 池快照（已随仓库分发，无需联网）
        pool_file = pool_dir / f"{s['id']}.json"
        docs: list[dict] = []
        if pool_file.exists():
            docs = json.loads(pool_file.read_text(encoding="utf-8"))
        # gold = 被引次数前 12 条（作为"高相关"近似）
        gold = sorted(docs, key=lambda d: -d.get("cited_by_count", 0))[:12]
        keys[s["id"]] = {"gold_docs": gold, "pool_size": len(docs)}
    return tasks, keys


# --- T4 论文问答 -----------------------------------------------------------
def build_t4() -> tuple[list[Task], dict]:
    tasks: list[Task] = []
    keys: dict = {}
    for s in sb.T4_SEEDS:
        t = Task(task_id=s["id"], family="T4", suite="T4_paperqa",
                 difficulty=s["d"], prompt=s["q"],
                 context={"pdf_path": f"papers/{s['paper']}.pdf"})
        tasks.append(t)
        keys[s["id"]] = {"gold_answer": s["gold"], "gold_spans": s["spans"],
                         "paper": s["paper"]}
    return tasks, keys


# --- T5 引用核对 -----------------------------------------------------------
_FAKE_SUFFIX = [
    ": A Unified Framework for Cross-Modal Graph Reasoning",
    " Revisited: An Empirical Study on Large-Scale Benchmarks",
]


def _mutate_title(title: str, i: int) -> str:
    """确定性生成"看似合理但不存在"的标题。"""
    if i % 2 == 0:
        return title + _FAKE_SUFFIX[(i // 2) % len(_FAKE_SUFFIX)]
    words = title.split()
    if len(words) > 3:
        words[1] = "Efficient" if words[1] != "Efficient" else "Robust"
    return " ".join(words)


def _fake_doi(seed: str) -> str:
    return "10.0000/fake." + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def build_t5() -> tuple[list[Task], dict]:
    """构造三分类样本：supported / unrelated / nonexistent。"""
    tasks: list[Task] = []
    keys: dict = {}
    n = 0

    # 1) supported：真实文献 + 支撑该论断
    for claim, idx, verdict in sb.CLAIMS:
        if verdict != "supported":
            continue
        n += 1
        ref = sb.REAL_REFS[idx]
        tid = f"T5-{n:03d}"
        tasks.append(Task(
            task_id=tid, family="T5", suite="T5_citation",
            difficulty="easy" if n <= 4 else "medium",
            prompt=f"请核查以下论断与其被引文献的关系：\n论断：{claim}",
            context={"reference": ref}))
        keys[tid] = {"verdict": "supported", "claim": claim, "ref_title": ref["title"]}

    # 2) unrelated（显式）：文献真实但与论断无关
    for claim, idx, verdict in sb.CLAIMS:
        if verdict != "unrelated":
            continue
        n += 1
        ref = sb.REAL_REFS[idx]
        tid = f"T5-{n:03d}"
        tasks.append(Task(
            task_id=tid, family="T5", suite="T5_citation",
            difficulty="medium",
            prompt=f"请核查以下论断与其被引文献的关系：\n论断：{claim}",
            context={"reference": ref}))
        keys[tid] = {"verdict": "unrelated", "claim": claim, "ref_title": ref["title"]}

    # 3) unrelated（交叉配对）：把 supported 论断配到另一篇真实文献
    supported = [(c, i) for c, i, v in sb.CLAIMS if v == "supported"]
    for k, (claim, idx) in enumerate(supported):
        other = sb.REAL_REFS[(idx + 3) % len(sb.REAL_REFS)]
        n += 1
        tid = f"T5-{n:03d}"
        tasks.append(Task(
            task_id=tid, family="T5", suite="T5_citation", difficulty="medium",
            prompt=f"请核查以下论断与其被引文献的关系：\n论断：{claim}",
            context={"reference": other}))
        keys[tid] = {"verdict": "unrelated", "claim": claim,
                     "ref_title": other["title"], "construct": "cross_pair"}

    # 4) nonexistent：对真实标题做确定性改写 + 伪造 DOI
    for k, (claim, idx) in enumerate(supported[:10]):
        base = sb.REAL_REFS[(idx + 1) % len(sb.REAL_REFS)]
        fake_title = _mutate_title(base["title"], k)
        ref = {"title": fake_title, "doi": _fake_doi(fake_title),
               "year": (base["year"] or 2020) + 1,
               "abstract": (base["abstract"] or "")}
        n += 1
        tid = f"T5-{n:03d}"
        tasks.append(Task(
            task_id=tid, family="T5", suite="T5_citation", difficulty="hard",
            prompt=f"请核查以下论断与其被引文献的关系：\n论断：{claim}",
            context={"reference": ref}))
        keys[tid] = {"verdict": "nonexistent", "claim": claim,
                     "ref_title": fake_title, "construct": "mutated_title"}

    return tasks, keys


# --- T6 / T7 / T8 ----------------------------------------------------------
def build_t6() -> tuple[list[Task], dict]:
    tasks, keys = [], {}
    for s in sb.T6_SEEDS:
        tasks.append(Task(task_id=s["id"], family="T6", suite="T6_writing",
                          difficulty=s["d"], prompt=s["q"],
                          context={"writing_type": s["type"],
                                   "min_outline_items": 6}))
        keys[s["id"]] = {"reference_answer": s["ref"], "writing_type": s["type"]}
    return tasks, keys


def build_t7() -> tuple[list[Task], dict]:
    tasks, keys = [], {}
    for s in sb.T7_SEEDS:
        tasks.append(Task(task_id=s["id"], family="T7", suite="T7_advisor",
                          difficulty=s["d"], prompt=s["q"]))
        keys[s["id"]] = {"expected_tools": s["tools"], "key_points": s["kp"]}
    return tasks, keys


def build_t8() -> tuple[list[Task], dict]:
    tasks, keys = [], {}
    for s in sb.T8_SEEDS:
        tasks.append(Task(task_id=s["id"], family="T8", suite="T8_workflow",
                          difficulty=s["d"], prompt=s["q"],
                          context={"steps": s["steps"]}))
        keys[s["id"]] = {"expected_tools": s["tools"],
                         "required_sections": s["req"]}
    return tasks, keys


# --- 主流程 ---------------------------------------------------------------
BUILDERS = {
    "T1": build_t1t2, "T2": build_t1t2, "T3": build_t3,
    "T4": build_t4, "T5": build_t5, "T6": build_t6,
    "T7": build_t7, "T8": build_t8,
}
SUITE_FILE = {
    "T1": "T1_survey.jsonl", "T2": "T2_proposal.jsonl", "T3": "T3_search.jsonl",
    "T4": "T4_paperqa.jsonl", "T5": "T5_citation.jsonl", "T6": "T6_writing.jsonl",
    "T7": "T7_advisor.jsonl", "T8": "T8_workflow.jsonl",
}


def main() -> None:
    ap = argparse.ArgumentParser(description="构建 ScholarBench 数据集")
    ap.add_argument("--families", nargs="*", default=list(SUITE_FILE))
    ap.add_argument("--version", default=VERSION)
    args = ap.parse_args()

    vdir = DATA_ROOT / args.version
    (vdir / "keys_heldout").mkdir(parents=True, exist_ok=True)

    total = 0
    for fam in args.families:
        builder = BUILDERS[fam]
        if fam in ("T1", "T2"):
            tasks, keys = builder()
            tasks = [t for t in tasks if t.family == fam]
            keys = {k: v for k, v in keys.items() if k.startswith(fam)}
        elif fam == "T3":
            tasks, keys = build_t3()
        else:
            tasks, keys = builder()

        write_jsonl(vdir / SUITE_FILE[fam], [t.to_dict() for t in tasks])
        (vdir / "keys_heldout" / f"{fam}.json").write_text(
            json.dumps(keys, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {fam}: {len(tasks)} 条 -> {SUITE_FILE[fam]}")
        total += len(tasks)

    _write_splits(vdir)
    print(f"\n完成，共 {total} 条。数据目录：{vdir}")


def _write_splits(vdir: Path) -> None:
    """生成 lite / full / hard 三档 split 定义。

    lite：每族前 8 条（快速迭代，约 1 小时内跑完）
    full：全部
    hard：仅 hard 难度（能力悬崖探测）
    """
    splits_dir = DATA_ROOT / "splits"
    splits_dir.mkdir(parents=True, exist_ok=True)
    from .schema import load_tasks

    lite: dict[str, list[str]] = {}
    full: dict[str, list[str]] = {}
    hard: dict[str, list[str]] = {}
    for fam, fname in SUITE_FILE.items():
        p = vdir / fname
        if not p.exists():
            continue
        tasks = load_tasks(p)
        full[fam] = [t.task_id for t in tasks]
        lite[fam] = [t.task_id for t in tasks[:8]]
        hard[fam] = [t.task_id for t in tasks if t.difficulty == "hard"]

    for name, payload in (("lite", lite), ("full", full), ("hard", hard)):
        (splits_dir / f"{name}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  splits: lite {sum(len(v) for v in lite.values())} / "
          f"full {sum(len(v) for v in full.values())} / "
          f"hard {sum(len(v) for v in hard.values())} 条")


if __name__ == "__main__":
    main()
