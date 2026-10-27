"""FMECA criticality analysis, quantitative method (MIL-STD-1629A style).

For each failure mode of an item:

  Cm = beta x alpha x lambda_p x t

  lambda_p  item failure rate (failures per hour, = 1 / MTBF)
  alpha     failure mode ratio: share of the item's failures that are this mode
            (the alphas of an item's modes should sum to 1)
  beta      conditional probability that the mode produces the stated effect
            (1.0 actual, roughly 0.1-1.0 probable, up to 0.1 possible, 0 none)
  t         operating time of interest, hours (e.g. one patrol)

Item criticality for a severity category is the sum of Cm over the item's
modes in that category. Severity categories:

  I    catastrophic   death, or loss of the ship or system
  II   critical       severe injury, major damage, or mission loss
  III  marginal       minor injury, minor damage, or mission degradation
  IV   minor          less than the above; unscheduled maintenance

The criticality matrix places each mode by severity (rows) and Cm (columns);
modes high on both get design or maintenance attention first.

MIL-STD-1629A was cancelled in 1998 but its method is still the common
reference for quantitative criticality; S3000L and SAE ARP5580 cover FMEA as
part of current LSA practice.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

SEVERITY = {
    "I": "catastrophic",
    "II": "critical",
    "III": "marginal",
    "IV": "minor",
}


@dataclass
class FailureMode:
    item: str
    mode: str
    effect: str
    severity: str        # I, II, III, IV
    alpha: float
    beta: float
    mtbf: float

    def criticality(self, t: float) -> float:
        if self.severity not in SEVERITY:
            raise ValueError(f"{self.item}/{self.mode}: severity must be one of {list(SEVERITY)}")
        if not (0 <= self.alpha <= 1 and 0 <= self.beta <= 1):
            raise ValueError(f"{self.item}/{self.mode}: alpha and beta must be between 0 and 1")
        return self.beta * self.alpha * (1 / self.mtbf) * t


def check_alphas(modes: list[FailureMode], tol: float = 0.01) -> list[str]:
    """Alphas for each item should sum to 1; return warnings where they don't."""
    sums: dict[str, float] = {}
    for m in modes:
        sums[m.item] = sums.get(m.item, 0) + m.alpha
    return [f"{item}: failure mode ratios sum to {s:.2f}, not 1.00"
            for item, s in sums.items() if abs(s - 1) > tol]


@dataclass
class CriticalityRow:
    mode: FailureMode
    cm: float


def criticality(modes: list[FailureMode], t: float) -> list[CriticalityRow]:
    """Modes ranked: worst severity first, then highest Cm."""
    order = {k: i for i, k in enumerate(SEVERITY)}
    rows = [CriticalityRow(m, m.criticality(t)) for m in modes]
    return sorted(rows, key=lambda r: (order[r.mode.severity], -r.cm))


def item_criticality(rows: list[CriticalityRow]) -> dict[tuple[str, str], float]:
    """Cr per (item, severity)."""
    out: dict[tuple[str, str], float] = {}
    for r in rows:
        key = (r.mode.item, r.mode.severity)
        out[key] = out.get(key, 0) + r.cm
    return out


def matrix_column(cm: float) -> str:
    """Bucket Cm by order of magnitude for the criticality matrix."""
    if cm <= 0:
        return "0"
    exp = math.floor(math.log10(cm))
    return f"1e{exp}"
