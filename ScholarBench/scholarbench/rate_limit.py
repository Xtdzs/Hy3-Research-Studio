"""轻量全局限速器：模型请求最小间隔 + 429 全局冷却。

评测过程中所有 OpenAI 兼容调用（生成 / 打分）共享同一节拍，
避免瞬时突发请求打满 TokenHub 共享网关触发 429 限流。

用法：
    rate_limit.configure(interval=2.0)  # 两次请求最小间隔 2s（0 = 不限间隔）
    rate_limit.wait_before_request()    # 每次发请求前调用
    rate_limit.on_429()                 # 捕获 429 后调用，进入指数冷却
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_interval = 0.0       # 两次请求之间的最小间隔（秒）
_last = 0.0           # 上一次实际发请求的时刻
_cool_until = 0.0     # 429 冷却结束时刻（epoch 秒）
_cool_s = 15.0        # 当前 429 冷却时长（指数增长 15→30→60→120 封顶）
_streak = 0           # 连续 429 计数（含"冷却结束后重试仍 429"的情形）
_last_429 = 0.0       # 最近一次 429 的时刻（epoch 秒）


def configure(interval: float = 0.0) -> None:
    """设置全局请求最小间隔（秒）。0 = 只做 429 冷却、不限制正常请求间隔。"""
    global _interval
    with _lock:
        _interval = max(0.0, float(interval))


def wait_before_request() -> None:
    """请求前调用：距上次过近则补齐间隔；处于 429 冷却则等到冷却结束。"""
    global _last
    while True:
        with _lock:
            now = time.time()
            wait = _cool_until - now
            if _interval > 0:
                wait = max(wait, _last + _interval - now)
        if wait <= 0:
            break
        time.sleep(wait)
    with _lock:
        _last = time.time()


def on_429() -> float:
    """标记一次 429：进入冷却，连续 429（含冷却结束重试仍 429）冷却时长翻倍。

    修复：旧逻辑只在"冷却期内再次 429"时翻倍，而实际流程是等冷却结束
    才发下一请求，导致连续 429 永远只等 15s 就重试、白白耗尽重试次数。
    现改为滑窗计数：90s 内连续触发 429 视为同一次限流风暴，冷却按
    15→30→60→120→240→300s 封顶指数增长；距上次 429 超过 90s 则复位。

    返回本次设定的冷却秒数（用于终端提示）。
    """
    global _cool_until, _cool_s, _streak, _last_429
    with _lock:
        now = time.time()
        if now - _last_429 <= 90.0:
            _streak += 1
        else:
            _streak = 1
        _last_429 = now
        _cool_s = min(15.0 * (2 ** (_streak - 1)), 300.0)
        _cool_until = now + _cool_s
        return _cool_s


def cooldown_left() -> float:
    """当前 429 冷却剩余秒数（0 = 不在冷却中）。"""
    with _lock:
        return max(0.0, _cool_until - time.time())


def is_rate_error(err: str) -> bool:
    """429 / 服务繁忙 / 容量限流等网关错误的启发式判断。"""
    return any(k in err for k in ("429", "RateLimit", "rate_limit",
                                  "busy", "capacity", "过载", "繁忙", "容量"))
