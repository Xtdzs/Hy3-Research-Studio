"""轻量 .env 加载（零依赖）。

搜索顺序（先到先得，不覆盖已有环境变量）：
    1. 当前工作目录
    2. ScholarBench 包根目录
    3. 同级目录 ../Hy3-Research-Studio（若用户在被测应用里配置了 key，评测端可直接复用）
    4. 环境变量 STUDIO_ROOT 指向的目录
"""
from __future__ import annotations

import os
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parents[1]


def _candidates() -> list[Path]:
    out = [Path.cwd(), PKG_ROOT, PKG_ROOT.parent / "Hy3-Research-Studio",
           PKG_ROOT.parent / "Hy3 Research Studio"]
    root = os.getenv("STUDIO_ROOT")
    if root:
        out.append(Path(root))
    return out


def load_dotenv() -> Path | None:
    for base in _candidates():
        env = base / ".env"
        if not env.exists():
            continue
        try:
            lines = env.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        return env
    return None


def is_configured() -> bool:
    return bool(os.getenv("HY3_API_KEY"))
