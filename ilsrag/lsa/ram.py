"""Reliability, availability and maintainability (RAM).

Availability measures (standard definitions):

  inherent     Ai = MTBF / (MTBF + MTTR)
               design only: corrective repair time, nothing else.
  achieved     Aa = MTBM / (MTBM + M)
               adds preventive maintenance: MTBM counts every maintenance
               action, M is mean active maintenance time (corrective + preventive).
  operational  Ao = MTBM / (MTBM + MDT)
               what the ship actually sees: MDT adds logistics and administrative
               delay (waiting for spares, technicians, a port).

The gap between Ai and Ao is where supply support earns its keep: the same
equipment with spares onboard and with spares 3 weeks away has the same Ai and
very different Ao.

Reliability block diagrams: Block, Series, Parallel and KofN compose into a
tree; availability() and reliability(t) evaluate it assuming independent
blocks with exponential (constant failure rate) behaviour. Identical blocks
are not required for KofN.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations


def inherent_availability(mtbf: float, mttr: float) -> float:
    _positive(mtbf=mtbf)
    _non_negative(mttr=mttr)
    return mtbf / (mtbf + mttr)


def achieved_availability(mtbm: float, mean_active_maintenance: float) -> float:
    _positive(mtbm=mtbm)
    _non_negative(mean_active_maintenance=mean_active_maintenance)
    return mtbm / (mtbm + mean_active_maintenance)


def operational_availability(mtbm: float, mdt: float) -> float:
    _positive(mtbm=mtbm)
    _non_negative(mdt=mdt)
    return mtbm / (mtbm + mdt)


def mtbm(mtbf: float, pm_interval: float | None) -> float:
    """Mean time between maintenance when corrective (1/MTBF) and preventive
    (1/interval) actions both occur."""
    _positive(mtbf=mtbf)
    rate = 1 / mtbf + (1 / pm_interval if pm_interval else 0)
    return 1 / rate


def reliability(mtbf: float, t: float) -> float:
    """Probability of no failure over t hours, constant failure rate."""
    _positive(mtbf=mtbf)
    return math.exp(-t / mtbf)


# --------------------------------------------------------------- block diagrams

@dataclass
class Block:
    name: str
    mtbf: float
    mttr: float = 0.0

    def availability(self) -> float:
        return inherent_availability(self.mtbf, self.mttr)

    def reliability(self, t: float) -> float:
        return reliability(self.mtbf, t)

    def describe(self) -> str:
        return self.name


@dataclass
class Series:
    """Every block must work."""
    blocks: list = field(default_factory=list)
    name: str = "series"

    def availability(self) -> float:
        return math.prod(b.availability() for b in self.blocks)

    def reliability(self, t: float) -> float:
        return math.prod(b.reliability(t) for b in self.blocks)

    def describe(self) -> str:
        return "(" + " -> ".join(b.describe() for b in self.blocks) + ")"


@dataclass
class Parallel:
    """At least one block must work (active redundancy)."""
    blocks: list = field(default_factory=list)
    name: str = "parallel"

    def availability(self) -> float:
        return 1 - math.prod(1 - b.availability() for b in self.blocks)

    def reliability(self, t: float) -> float:
        return 1 - math.prod(1 - b.reliability(t) for b in self.blocks)

    def describe(self) -> str:
        return "[" + " || ".join(b.describe() for b in self.blocks) + "]"


@dataclass
class KofN:
    """At least k of the n blocks must work. Blocks need not be identical."""
    k: int
    blocks: list = field(default_factory=list)
    name: str = "k-of-n"

    def _prob(self, probs: list[float]) -> float:
        n = len(probs)
        if not 1 <= self.k <= n:
            raise ValueError(f"k={self.k} must be between 1 and n={n}")
        total = 0.0
        for m in range(self.k, n + 1):
            for up in combinations(range(n), m):
                upset = set(up)
                total += math.prod(p if i in upset else 1 - p for i, p in enumerate(probs))
        return total

    def availability(self) -> float:
        return self._prob([b.availability() for b in self.blocks])

    def reliability(self, t: float) -> float:
        return self._prob([b.reliability(t) for b in self.blocks])

    def describe(self) -> str:
        return f"{self.k}-of-{len(self.blocks)}{{" + ", ".join(b.describe() for b in self.blocks) + "}"


def build_rbd(spec: dict, blocks: dict[str, Block]):
    """Build a diagram from a nested dict, e.g.
    {"series": ["antenna", {"parallel": ["psu_a", "psu_b"]}, "processor"]}."""
    if isinstance(spec, str):
        if spec not in blocks:
            raise ValueError(f"RBD refers to unknown block '{spec}'")
        return blocks[spec]
    if len(spec) != 1:
        raise ValueError(f"each RBD node needs exactly one of series/parallel/k_of_n, got {list(spec)}")
    kind, body = next(iter(spec.items()))
    if kind == "series":
        return Series([build_rbd(s, blocks) for s in body])
    if kind == "parallel":
        return Parallel([build_rbd(s, blocks) for s in body])
    if kind == "k_of_n":
        return KofN(int(body["k"]), [build_rbd(s, blocks) for s in body["blocks"]])
    raise ValueError(f"unknown RBD node type '{kind}'")


def _positive(**kw: float) -> None:
    for k, v in kw.items():
        if v is None or v <= 0:
            raise ValueError(f"{k} must be > 0, got {v}")


def _non_negative(**kw: float) -> None:
    for k, v in kw.items():
        if v is None or v < 0:
            raise ValueError(f"{k} must be >= 0, got {v}")
