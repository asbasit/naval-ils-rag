"""Reliability prediction by the parts count method (MIL-HDBK-217 style).

    lambda_equipment = sum over part types of  N_i x lambda_g,i x pi_Q,i

  N_i       quantity of part type i
  lambda_g  generic failure rate for that part type in the chosen environment
            (failures per 10^6 hours), from the handbook's parts count tables
  pi_Q      quality factor for that part type's quality level

  MTBF = 10^6 / lambda_equipment   hours

This module does the arithmetic only. It ships no handbook tables: take
lambda_g and pi_Q from MIL-HDBK-217 (parts count appendix) for your
environment (for example naval sheltered) or from your organization's
approved source, and record where each value came from in `source`.
The example data in examples/lsa/ is invented and says so.

Parts count is an early-design estimate; the parts stress method, field data,
or the supplier's demonstrated MTBF replace it when available.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PartLine:
    part_type: str
    quantity: int
    lambda_g: float          # failures per 10^6 hours
    pi_q: float = 1.0
    source: str = ""

    @property
    def contribution(self) -> float:
        if self.quantity < 0 or self.lambda_g < 0 or self.pi_q < 0:
            raise ValueError(f"{self.part_type}: values must be >= 0")
        return self.quantity * self.lambda_g * self.pi_q


@dataclass
class PartsCountResult:
    item: str
    environment: str
    lines: list[PartLine]
    lambda_total: float      # failures per 10^6 hours
    mtbf: float              # hours

    def share(self, line: PartLine) -> float:
        return line.contribution / self.lambda_total if self.lambda_total else 0.0


def parts_count(item: str, environment: str, lines: list[PartLine]) -> PartsCountResult:
    total = sum(l.contribution for l in lines)
    if total <= 0:
        raise ValueError(f"{item}: total failure rate is zero; check the parts list")
    return PartsCountResult(item, environment, sorted(lines, key=lambda l: -l.contribution),
                            total, 1e6 / total)
