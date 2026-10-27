"""Level of repair analysis (LORA), economic part.

For one repairable item, compare the life-cycle cost of each maintenance
option: throw away and replace, or repair at a given level (onboard,
intermediate e.g. a fleet maintenance facility, depot e.g. the OEM).

For each option over the analysis period:

  failures         = fleet operating hours / MTBF  (per year, times years)
  per-failure cost = (discard: unit price) or (repair: labour + material + transport)
  pipeline spares  = failures per year x turnaround time (years) x unit price
                     (stock tied up while items are away being repaired;
                      for discard, the replenishment lead time)
  fixed cost       = support and test equipment, facilities, training, data
                     for that level, paid once (or per site)

  life-cycle cost  = years x failures/yr x per-failure cost + pipeline + fixed

The cheapest option is the economic answer. A real LORA then applies the
non-economic checks: can the repair be done safely onboard, is the skill
available at that level, does turnaround time hurt operational availability,
is the item classified or controlled. Those go in `constraints` and are
reported next to the numbers, not folded into them.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoraOption:
    name: str
    kind: str                        # "discard" or "repair"
    turnaround_days: float
    repair_cost: float = 0.0         # labour + material per repair event
    transport_cost: float = 0.0      # per event, both ways
    fixed_cost: float = 0.0          # S&TE, facilities, training, data for this level
    constraints: list[str] = field(default_factory=list)


@dataclass
class LoraLine:
    option: str
    failures_total: float
    event_cost: float
    pipeline_cost: float
    fixed_cost: float
    total: float
    constraints: list[str]


def lora(item: str, unit_price: float, mtbf: float, fleet_hours_per_year: float,
         years: float, options: list[LoraOption]) -> list[LoraLine]:
    if mtbf <= 0 or unit_price < 0 or fleet_hours_per_year < 0 or years <= 0:
        raise ValueError("check LORA inputs: mtbf > 0, years > 0, others >= 0")
    if not options:
        raise ValueError("LORA needs at least one option")
    failures_per_year = fleet_hours_per_year / mtbf
    lines = []
    for o in options:
        if o.kind not in ("discard", "repair"):
            raise ValueError(f"option {o.name}: kind must be 'discard' or 'repair'")
        per_event = (unit_price if o.kind == "discard" else o.repair_cost) + o.transport_cost
        pipeline = failures_per_year * (o.turnaround_days / 365.0) * unit_price
        failures = failures_per_year * years
        total = failures * per_event + pipeline + o.fixed_cost
        lines.append(LoraLine(o.name, failures, failures * per_event, pipeline, o.fixed_cost, total,
                              list(o.constraints)))
    return sorted(lines, key=lambda l: l.total)
