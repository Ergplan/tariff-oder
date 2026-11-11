"""Policy, the spend ledger and the daily caps.

Every paid call (Extractor, Director, LlamaParse) asks ``Budget.reserve(agent, estimate)`` before
it is made and ``Budget.record(...)`` after, with the tokens and the cost.  ``reserve`` raises
``BudgetExceeded`` when today's recorded spend plus the estimate would pass the daily cap or the
agent's own cap — the cap is enforced here, in code, whatever a planner or a model proposes.
"""

from __future__ import annotations

import datetime as dt
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import config, store


class BudgetExceeded(RuntimeError):
    pass


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def policy(path: str | Path | None = None) -> dict[str, Any]:
    return _load(str(path or config.HERE / "policy.yaml"))


def token_cost(pol: dict[str, Any], model: str, usage: dict[str, int]) -> float:
    p = pol["prices_usd_per_mtok"].get(model)
    if p is None:
        raise BudgetExceeded(f"no price for model {model} in policy.yaml: a call with an unknown price is not made")
    return (
        usage.get("input_tokens", 0) * p["input"]
        + usage.get("output_tokens", 0) * p["output"]
        + usage.get("cache_read_input_tokens", 0) * p.get("cache_read", p["input"])
        + usage.get("cache_creation_input_tokens", 0) * p.get("cache_write", p["input"])
    ) / 1e6


def today() -> str:
    return dt.datetime.now(dt.UTC).date().isoformat()


class Budget:
    def __init__(self, pol: dict[str, Any] | None = None, ledger: str = "spend") -> None:
        self.pol = pol or policy()
        self.ledger = ledger

    def spent(self, agent: str | None = None, day: str | None = None) -> float:
        day = day or today()
        return sum(
            float(r.get("cost_usd", 0))
            for r in store.read_jsonl(self.ledger)
            if r.get("day") == day and r.get("is_real") and (agent is None or r.get("agent") == agent)
        )

    def caps(self, agent: str) -> tuple[float, float | None]:
        b = self.pol.get("budget", {})
        total = float(os.environ.get("ARRNET_BUDGET_DAILY_USD") or b.get("daily_usd", 0.0))
        return total, (b.get("per_agent_daily_usd") or {}).get(agent)

    def remaining(self, agent: str) -> float:
        total, mine = self.caps(agent)
        left = total - self.spent()
        if mine is not None:
            left = min(left, float(mine) - self.spent(agent))
        return max(0.0, left)

    def reserve(self, agent: str, estimate_usd: float) -> None:
        total, mine = self.caps(agent)
        if self.spent() + estimate_usd > total:
            raise BudgetExceeded(
                f"{agent}: estimated ${estimate_usd:.4f} would pass the daily cap ${total:.2f} "
                f"(spent today ${self.spent():.4f})"
            )
        if mine is not None and self.spent(agent) + estimate_usd > float(mine):
            raise BudgetExceeded(f"{agent}: estimated ${estimate_usd:.4f} would pass its daily cap ${float(mine):.2f}")

    def record(self, agent: str, provider: str, model: str | None, cost_usd: float, *, is_real: bool, **kw: Any) -> None:
        store.append_jsonl(
            self.ledger,
            [
                {
                    "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                    "day": today(),
                    "agent": agent,
                    "provider": provider,
                    "model": model,
                    "is_real": is_real,
                    "cost_usd": round(cost_usd, 6),
                    **kw,
                }
            ],
        )
