"""Sparing: how many spares to carry so the ship doesn't run out.

Removals of an item with a constant failure rate follow a Poisson process.
Over a period the expected number of demands is

    lambda = installed quantity x operating hours in the period / MTBUR

(MTBUR, mean time between unscheduled removals, is lower than MTBF because it
also counts no-fault-found removals; use MTBF if MTBUR isn't known). The
probability that s spares cover every demand is the Poisson cumulative
probability P(N <= s). The protection level is the target for that
probability, often 0.90 or 0.95 for mission-critical items on a deployment
with no resupply.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


def expected_demand(quantity: int, operating_hours: float, mtbur: float) -> float:
    if quantity < 0 or operating_hours < 0:
        raise ValueError("quantity and operating_hours must be >= 0")
    if mtbur <= 0:
        raise ValueError("mtbur must be > 0")
    return quantity * operating_hours / mtbur


def poisson_cdf(s: int, lam: float) -> float:
    """P(N <= s) for N ~ Poisson(lam)."""
    if lam < 0:
        raise ValueError("lambda must be >= 0")
    term = math.exp(-lam)
    total = term
    for k in range(1, s + 1):
        term *= lam / k
        total += term
    return min(total, 1.0)


def spares_for_protection(lam: float, protection: float, max_spares: int = 500) -> int:
    """Smallest s with P(N <= s) >= protection."""
    if not 0 < protection < 1:
        raise ValueError("protection must be between 0 and 1")
    for s in range(max_spares + 1):
        if poisson_cdf(s, lam) >= protection:
            return s
    raise ValueError(f"more than {max_spares} spares needed; check inputs")


@dataclass
class SparingResult:
    item: str
    demand: float
    protection_target: float
    spares: int
    achieved_protection: float
    table: list[tuple[int, float]]   # (spares, protection) for 0..spares+2


def sparing(item: str, quantity: int, operating_hours: float, mtbur: float,
            protection: float) -> SparingResult:
    lam = expected_demand(quantity, operating_hours, mtbur)
    s = spares_for_protection(lam, protection)
    table = [(k, poisson_cdf(k, lam)) for k in range(0, s + 3)]
    return SparingResult(item, lam, protection, s, poisson_cdf(s, lam), table)
