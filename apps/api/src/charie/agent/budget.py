"""What a run is allowed to spend, and who says so (architecture 4.4)."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

__all__ = [
    "DEFAULT_BUDGET",
    "MAX_OVERRIDES",
    "Budget",
    "BudgetState",
    "Exhaustion",
]

#: Architecture 4.4's defaults, named so the numbers are greppable from the doc.
DEFAULT_ITERATIONS = 12
DEFAULT_QUERIES = 14
#: Raised from 20 to 24 in WP9.1 (D-028).
#: 29 against a ceiling of 32
DEFAULT_LLM_CALLS = 32
#: Scaled with the rest. The run that ran out spent 80,268 tokens over 17 calls.
DEFAULT_TOKENS = 225_000
#: Raised from 240 to 330 in the same change, and for a reason worth stating plainly.
DEFAULT_WALL_SECONDS = 330.0

#: How far an organization may raise a ceiling.
MAX_OVERRIDES: Mapping[str, float] = {
    "iterations": 24,
    "queries": 40,
    "llm_calls": 60,
    "tokens": 600_000,
    "wall_seconds": 900.0,
}

#: Fraction of a ceiling at which the trace says "getting close" (10.3's `budget_warning`).
WARN_AT = 0.75


@dataclass(frozen=True, slots=True)
class Exhaustion:
    """Which ceiling stopped the run, and how it reads to a person."""

    dimension: str
    used: float
    limit: float

    @property
    def reason(self) -> str:
        """Plain words for the answer's caveat, not a metric name."""
        return {
            "iterations": "I reached the maximum number of research steps for one question.",
            "queries": "I reached the maximum number of queries I may run for one question.",
            "llm_calls": "I reached the maximum amount of reasoning allowed for one question.",
            "tokens": "I reached the size limit on how much I may read for one question.",
            "wall_seconds": "I reached the time limit for one question.",
        }.get(self.dimension, "I reached a limit set for one question.")


@dataclass(frozen=True, slots=True)
class Budget:
    """The ceilings for one run."""

    iterations: int = DEFAULT_ITERATIONS
    queries: int = DEFAULT_QUERIES
    llm_calls: int = DEFAULT_LLM_CALLS
    tokens: int = DEFAULT_TOKENS
    wall_seconds: float = DEFAULT_WALL_SECONDS

    @classmethod
    def from_overrides(cls, overrides: Mapping[str, object] | None) -> Budget:
        """Defaults, adjusted by whatever an organization configured."""
        if not overrides:
            return cls()
        values: dict[str, float] = {}
        for name in ("iterations", "queries", "llm_calls", "tokens", "wall_seconds"):
            raw = overrides.get(name)
            if not isinstance(raw, int | float) or isinstance(raw, bool) or raw <= 0:
                continue
            ceiling = MAX_OVERRIDES[name]
            values[name] = min(float(raw), ceiling)
        base = cls()
        return replace(
            base,
            iterations=int(values.get("iterations", base.iterations)),
            queries=int(values.get("queries", base.queries)),
            llm_calls=int(values.get("llm_calls", base.llm_calls)),
            tokens=int(values.get("tokens", base.tokens)),
            wall_seconds=float(values.get("wall_seconds", base.wall_seconds)),
        )

    def as_json(self) -> dict[str, object]:
        """What `agent_runs.budget` holds — the allowance this run was given."""
        return {
            "iterations": self.iterations,
            "queries": self.queries,
            "llm_calls": self.llm_calls,
            "tokens": self.tokens,
            "wall_seconds": self.wall_seconds,
        }


@dataclass
class BudgetState:
    """What has been spent, and whether there is any left."""

    budget: Budget = field(default_factory=Budget)
    iterations: int = 0
    queries: int = 0
    llm_calls: int = 0
    tokens: int = 0
    #: Monotonic, because a wall-clock limit must not be moved by an NTP step or a...
    started_at: float = field(default_factory=time.monotonic)
    #: Dimensions already warned about, so the trace says it once.
    warned: set[str] = field(default_factory=set[str])

    def elapsed(self, *, now: float | None = None) -> float:
        return (now if now is not None else time.monotonic()) - self.started_at

    def spend_iteration(self) -> None:
        self.iterations += 1

    def spend_query(self) -> None:
        self.queries += 1

    def spend_llm(self, tokens: int = 0) -> None:
        """One model call and what it read."""
        self.llm_calls += 1
        self.tokens += max(0, tokens)

    def exhausted(self, *, now: float | None = None) -> Exhaustion | None:
        """The first ceiling reached, or None."""
        elapsed = self.elapsed(now=now)
        checks: tuple[tuple[str, float, float], ...] = (
            ("wall_seconds", elapsed, self.budget.wall_seconds),
            ("iterations", self.iterations, self.budget.iterations),
            ("queries", self.queries, self.budget.queries),
            ("llm_calls", self.llm_calls, self.budget.llm_calls),
            ("tokens", self.tokens, self.budget.tokens),
        )
        for dimension, used, limit in checks:
            if used >= limit:
                return Exhaustion(dimension=dimension, used=used, limit=limit)
        return None

    def approaching(self, *, now: float | None = None) -> str | None:
        """A dimension newly past `WARN_AT`, once each."""
        elapsed = self.elapsed(now=now)
        for dimension, used, limit in (
            ("wall_seconds", elapsed, self.budget.wall_seconds),
            ("iterations", float(self.iterations), float(self.budget.iterations)),
            ("queries", float(self.queries), float(self.budget.queries)),
            ("llm_calls", float(self.llm_calls), float(self.budget.llm_calls)),
            ("tokens", float(self.tokens), float(self.budget.tokens)),
        ):
            if dimension in self.warned or limit <= 0:
                continue
            if used / limit >= WARN_AT:
                self.warned.add(dimension)
                return dimension
        return None

    def as_json(self) -> dict[str, object]:
        return {
            "iterations": self.iterations,
            "queries": self.queries,
            "llm_calls": self.llm_calls,
            "tokens": self.tokens,
            "elapsed_seconds": round(self.elapsed(), 3),
            "limits": self.budget.as_json(),
        }


#: The allowance a run gets when nobody configured one.
DEFAULT_BUDGET = Budget()
