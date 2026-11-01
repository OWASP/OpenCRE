"""Per-account daily LLM budget for the chatbot and MCP ``ask`` (complements ``rate_limit``).

Rate limits count questions; this counts money. Every LiteLLM call made through
``prompt_client.litellm_router`` reports its cost here, charged to the account that is currently
asking (set with :func:`charging` or :func:`run_charged`). Before a question starts, :func:`check_budget`
refuses an account that has already spent its day's budget, so one question may overshoot a little.

Counters live in Redis (shared by every web and MCP process; in-process fallback), reset at 00:00 UTC.

Defaults: 1.00 USD per account per day; admins get RATE_LIMIT_ADMIN_MULTIPLIER x that (default 4).
Override with BUDGET_DAILY_USD; exempt accounts with RATE_LIMIT_EXEMPT_EMAILS; disable with
BUDGET_ENABLED=0. Costs come from LiteLLM's price table, so an unknown model counts as 0.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Dict, Iterator, Optional, Tuple, TypeVar

from cre_logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")
MICRO = 1_000_000  # counters hold millionths of a dollar
DEFAULT_DAILY_USD = 1.0

_account: ContextVar[Optional[str]] = ContextVar("opencre_spend_account", default=None)
_mem: Dict[str, Tuple[int, float]] = {}
_mem_lock = threading.Lock()


class BudgetExceeded(Exception):
    def __init__(self, budget_usd: float, retry_after: int) -> None:
        self.budget_usd, self.retry_after = budget_usd, retry_after
        super().__init__(self.message())

    def message(self) -> str:
        hours = max(1, (self.retry_after + 3599) // 3600)
        return (
            f"You have used today's usage budget for this account (${self.budget_usd:.2f}). "
            f"It resets at 00:00 UTC, in about {hours} hour{'s' if hours != 1 else ''}."
        )


def enabled() -> bool:
    return (os.environ.get("BUDGET_ENABLED", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def daily_budget_usd(role: Optional[str]) -> float:
    from application.utils import roles

    try:
        base = float(os.environ.get("BUDGET_DAILY_USD", "") or DEFAULT_DAILY_USD)
    except ValueError:
        base = DEFAULT_DAILY_USD
    try:
        mult = max(1, int(os.environ.get("RATE_LIMIT_ADMIN_MULTIPLIER", "") or 4))
    except ValueError:
        mult = 4
    return max(0.0, base) * (mult if role == roles.ADMIN else 1)


def _exempt(who: str) -> bool:
    return who in {
        e.strip().lower()
        for e in (os.environ.get("RATE_LIMIT_EXEMPT_EMAILS") or "").split(",")
        if e.strip()
    }


def _key(who: str) -> str:
    return f"spend:{who}:{time.strftime('%Y%m%d', time.gmtime())}"


def _seconds_to_reset() -> int:
    now = time.time()
    return int(86400 - (now % 86400))


def _redis():
    from application.utils import rate_limit

    return rate_limit._redis_conn()


def spent_usd(account: str) -> float:
    key = _key(account.strip().lower())
    conn = _redis()
    if conn is not None:
        try:
            return int(conn.get(key) or 0) / MICRO
        except Exception:  # noqa: BLE001
            pass
    with _mem_lock:
        value, expires = _mem.get(key, (0, 0.0))
        return (value if expires > time.time() else 0) / MICRO


def _add(account: str, micro: int) -> None:
    key = _key(account.strip().lower())
    ttl = 2 * 86400
    conn = _redis()
    if conn is not None:
        try:
            pipe = conn.pipeline()
            pipe.incrby(key, micro)
            pipe.expire(key, ttl)
            pipe.execute()
            return
        except Exception:  # noqa: BLE001
            pass
    with _mem_lock:
        value, expires = _mem.get(key, (0, 0.0))
        _mem[key] = ((value if expires > time.time() else 0) + micro, time.time() + ttl)


def check_budget(account: Optional[str], role: Optional[str]) -> None:
    """Raise :class:`BudgetExceeded` when the account has spent today's budget."""
    who = (account or "").strip().lower()
    if not enabled() or not who or _exempt(who):
        return
    cap = daily_budget_usd(role)
    if spent_usd(who) >= cap:
        raise BudgetExceeded(cap, _seconds_to_reset())


@contextmanager
def charging(account: Optional[str]) -> Iterator[None]:
    """Charge LLM calls made inside the block to ``account`` (no-op for an empty account)."""
    token = _account.set((account or "").strip().lower() or None)
    try:
        yield
    finally:
        _account.reset(token)


def run_charged(account: Optional[str], fn: Callable[[], T]) -> T:
    with charging(account):
        return fn()


def set_account(account: Optional[str]) -> None:
    """Request-scoped variant of :func:`charging`; pair it with :func:`clear` at request end."""
    _account.set((account or "").strip().lower() or None)


def clear() -> None:
    _account.set(None)


def current_account() -> Optional[str]:
    return _account.get()


def record(response: Any, model: Optional[str] = None) -> None:
    """Charge one LiteLLM response to the current account. Never raises."""
    who = current_account()
    if not who or not enabled():
        return
    try:
        import litellm  # type: ignore

        cost = float(litellm.completion_cost(completion_response=response, model=model))
    except Exception:  # noqa: BLE001 - unknown model, odd response shape: count nothing
        return
    if cost > 0:
        try:
            _add(who, int(round(cost * MICRO)))
        except Exception:  # noqa: BLE001
            logger.warning("could not record LLM spend")


def reset_memory() -> None:
    """Test helper."""
    with _mem_lock:
        _mem.clear()
