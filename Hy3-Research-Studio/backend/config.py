"""Global configuration for Hy3 Research Studio.

All Hy3 access goes through an OpenAI-compatible endpoint. Provide the API key
via the HY3_API_KEY environment variable (or a .env file) and the app is ready
to run. Defaults target Tencent TokenHub; switch BASE_URL/MODEL for Novita, etc.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# --- lightweight .env loader (no extra dependency required) ----------------
def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        # do not overwrite variables already present in the real environment
        os.environ.setdefault(key, value)


_load_dotenv()


@dataclass
class Settings:
    # --- Hy3 / LLM ---------------------------------------------------------
    api_key: str = field(default_factory=lambda: os.getenv("HY3_API_KEY", ""))
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "HY3_BASE_URL", "https://tokenhub.tencentmaas.com/v1"
        )
    )
    model: str = field(default_factory=lambda: os.getenv("HY3_MODEL", "hy3"))
    # thinking 模型单次推理常达 1-3 分钟，默认给足 300s（评测/应用可用 --timeout 覆盖）
    request_timeout: float = field(
        default_factory=lambda: float(os.getenv("HY3_TIMEOUT", "300"))
    )
    # 关闭思考链：HY3_DISABLE_THINKING=1 时请求带 thinking={"type":"disabled"}。
    # hy3/hy4-preview/deepseek 支持关闭（实测提速约 5x、token 省 ~80%）；
    # glm 等"始终思考"的模型会自动降级（去掉该参数按平台默认重试一次）。
    disable_thinking: bool = field(
        default_factory=lambda: os.getenv("HY3_DISABLE_THINKING", "0").lower()
        in ("1", "true", "yes", "on")
    )

    # --- Retrieval ---------------------------------------------------------
    # 默认启用免 Key 的可靠学术源：Crossref / arXiv。
    # Semantic Scholar 仅在提供 S2_API_KEY 时启用（限流更宽松、召回更稳）。
    s2_api_key: str = field(default_factory=lambda: os.getenv("S2_API_KEY", ""))
    default_sources: list[str] = field(
        default_factory=lambda: [
            s for s in os.getenv(
                "DEFAULT_SOURCES", "crossref,arxiv"
            ).split(",") if s
        ]
    )
    max_sources_per_query: int = field(
        default_factory=lambda: int(os.getenv("MAX_SOURCES_PER_QUERY", "6"))
    )
    http_timeout: float = field(
        default_factory=lambda: float(os.getenv("HTTP_TIMEOUT", "20"))
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


settings = Settings()
