"""T4 论文全文下载：从 arXiv 拉取 OA PDF 到 data/v0.1/papers/。

    python -m scholarbench.download_papers            # 下载 T4 需要的全部论文
    python -m scholarbench.download_papers --paper bert

论文只作为评测输入（开放获取），不随仓库分发（.gitignore 已排除 *.pdf）。
"""
from __future__ import annotations

import argparse
import urllib.request
from pathlib import Path

from .dataset import version_dir

# seedbank 中 paper 字段 -> arXiv ID
PAPER_ARXIV = {
    "attention-is-all-you-need": "1706.03762",
    "bert": "1810.04805",
    "chain-of-thought": "2201.11903",
    "rag": "2005.11401",
    "lora": "2106.09685",
    "lost-in-the-middle": "2307.03172",
    "self-consistency": "2203.11171",
    "instruction-tuning": "2210.11416",  # Scaling Instruction-Finetuned Language Models
}


def paper_dir() -> Path:
    d = version_dir() / "papers"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download(name: str, timeout: float = 60.0) -> Path | None:
    arxiv_id = PAPER_ARXIV.get(name)
    if not arxiv_id:
        print(f"  [skip] {name}: 未知论文（可在 PAPER_ARXIV 中补充 arXiv ID）")
        return None
    dest = paper_dir() / f"{name}.pdf"
    if dest.exists() and dest.stat().st_size > 10_000:
        print(f"  [ok]   {name}.pdf 已存在")
        return dest
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "ScholarBench/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        dest.write_bytes(data)
        print(f"  [ok]   {name}.pdf  <- arXiv:{arxiv_id}  ({len(data) // 1024} KB)")
        return dest
    except Exception as exc:  # noqa: BLE001
        print(f"  [fail] {name}: {exc}")
        return None


def main() -> None:
    ap = argparse.ArgumentParser(description="下载 T4 论文全文（arXiv OA）")
    ap.add_argument("--paper", nargs="*", default=None,
                    help="只下载指定论文（默认全部）")
    args = ap.parse_args()

    names = args.paper or sorted(PAPER_ARXIV)
    print(f"下载 {len(names)} 篇论文到 {paper_dir()}")
    ok = sum(1 for n in names if download(n) is not None)
    print(f"\n完成：{ok}/{len(names)}。T4 评测依赖这些 PDF；"
          f"缺失时对应任务会因『论文全文不可用』计为失败。")


if __name__ == "__main__":
    main()
