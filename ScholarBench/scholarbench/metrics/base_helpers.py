"""客观指标共用的文本处理工具（纯标准库，无 LLM）。"""
from __future__ import annotations

import re


def norm_title(title: str) -> str:
    """标题归一化：小写、去标点、去多余空白。用于文献匹配。"""
    s = (title or "").lower().strip()
    s = re.sub(r"[^\w\u4e00-\u9fff ]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _norm_tokens(text: str) -> list[str]:
    s = (text or "").lower()
    s = re.sub(r"[^\w\u4e00-\u9fff ]", " ", s)
    return [t for t in s.split() if t]


def token_f1(pred: str, gold: str) -> float:
    """归一化后的 token F1（中英文混合可用）。"""
    from collections import Counter
    p = _norm_tokens(pred)
    g = _norm_tokens(gold)
    if not p or not g:
        return float(bool(p) and bool(g))
    cp, cg = Counter(p), Counter(g)
    overlap = sum((cp & cg).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(p)
    recall = overlap / len(g)
    return round(2 * precision * recall / (precision + recall), 4)


def lcs_len(a: list[str], b: list[str]) -> int:
    """最长公共子序列长度（用于 ROUGE-L）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0] * (len(b) + 1)
        for j, y in enumerate(b, 1):
            cur[j] = prev[j - 1] + 1 if x == y else max(prev[j], cur[j - 1])
        prev = cur
    return prev[-1]


def lcs_rouge(pred: str, gold: str) -> float:
    """ROUGE-L F1（基于 token 的 LCS）。"""
    p, g = _norm_tokens(pred), _norm_tokens(gold)
    if not p or not g:
        return float(bool(p) and bool(g))
    l = lcs_len(p, g)
    if l == 0:
        return 0.0
    precision, recall = l / len(p), l / len(g)
    return round(2 * precision * recall / (precision + recall), 4)
