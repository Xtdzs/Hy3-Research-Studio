"""matplotlib 中文字体配置（可选）。缺字体时静默降级为英文标签。"""
from __future__ import annotations

import platform

CJK_FONTS = {
    "Windows": ["Microsoft YaHei", "SimHei", "SimSun"],
    "Darwin": ["PingFang SC", "Heiti SC", "Arial Unicode MS"],
    "Linux": ["Noto Sans CJK SC", "WenQuanYi Zen Hei", "Source Han Sans SC"],
}


def apply_cjk() -> str:
    """设置中文字体，返回实际使用的字体名（失败返回空串）。"""
    import matplotlib  # noqa: PLC0415
    from matplotlib import font_manager  # noqa: PLC0415

    system = platform.system()
    for name in CJK_FONTS.get(system, []):
        try:
            font_manager.findfont(name, fallback_to_default=False)
        except Exception:  # noqa: BLE001
            continue
        matplotlib.rcParams["font.sans-serif"] = [name] + \
            list(matplotlib.rcParams.get("font.sans-serif", []))
        matplotlib.rcParams["axes.unicode_minus"] = False
        return name
    matplotlib.rcParams["axes.unicode_minus"] = False
    return ""
