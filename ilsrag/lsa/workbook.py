"""LSA workbook: run RAM, sparing, LORA, FMECA and parts count on one case
file and write a report, comparing before and after an engineering change.

Case files are TOML; see examples/lsa/radar-psu.toml. Block names in the
reliability block diagram may carry an instance suffix ("psu#a", "psu#b"):
each is an independent copy of block "psu".
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from . import fmeca as fm
from . import lora as lo
from . import parts_count as pc
from . import ram
from . import sparing as sp


def _blocks(case: dict, mtbf_override: dict[str, float] | None = None) -> dict[str, ram.Block]:
    out = {}
    for b in case["block"]:
        mtbf = (mtbf_override or {}).get(b["name"], b["mtbf"])
        out[b["name"]] = ram.Block(b["name"], mtbf, b.get("mttr", 0.0))
    return out


def _resolve(spec, blocks: dict[str, ram.Block]):
    """Expand 'name#instance' references into independent copies of a block."""
    if isinstance(spec, str):
        base = spec.split("#", 1)[0]
        if base not in blocks:
            raise ValueError(f"RBD refers to unknown block '{base}'")
        return replace(blocks[base], name=spec)
    kind, body = next(iter(spec.items()))
    if kind == "k_of_n":
        return {kind: {"k": body["k"], "blocks": [_resolve(s, blocks) for s in body["blocks"]]}}
    return {kind: [_resolve(s, blocks) for s in body]}


def _build(spec):
    if isinstance(spec, ram.Block):
        return spec
    kind, body = next(iter(spec.items()))
    if kind == "series":
        return ram.Series([_build(s) for s in body])
    if kind == "parallel":
        return ram.Parallel([_build(s) for s in body])
    if kind == "k_of_n":
        return ram.KofN(int(body["k"]), [_build(s) for s in body["blocks"]])
    raise ValueError(f"unknown RBD node type '{kind}'")


def rbd_for(case: dict, mtbf_override: dict[str, float] | None = None):
    return _build(_resolve(case["rbd"], _blocks(case, mtbf_override)))


@dataclass
class Results:
    case: dict
    patrol_hours: float
    rbd_before: object
    rbd_after: object
    ao: dict
    sparing_before: sp.SparingResult
    sparing_after: sp.SparingResult
    lora: list
    fmeca: list
    fmeca_warnings: list[str]
    parts: pc.PartsCountResult | None


def run(path: Path) -> Results:
    case = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    c = case["case"]
    patrol_hours = c["patrol_days"] * c["operating_hours_per_day"]
    ch = case["change"]
    item = ch["block"]

    before = rbd_for(case, {item: ch["mtbf_before"]})
    after = rbd_for(case, {item: ch["mtbf_after"]})

    a = case["ao"]
    blk = next(b for b in case["block"] if b["name"] == item)
    m = ram.mtbm(ch["mtbf_after"], a.get("pm_interval_hours"))
    ao = {
        "item": item,
        "ai": ram.inherent_availability(ch["mtbf_after"], blk["mttr"]),
        "ao_spare_onboard": ram.operational_availability(m, blk["mttr"] + a["admin_delay_hours"]),
        "ao_no_spare": ram.operational_availability(
            m, blk["mttr"] + a["admin_delay_hours"] + a["logistic_delay_hours_no_spare"]),
        "mtbm": m,
        "logistic_delay_hours_no_spare": a["logistic_delay_hours_no_spare"],
    }

    s = case["sparing"]
    qty = s["installed_per_ship"]
    sb = sp.sparing(item, qty, patrol_hours, ch.get("mtbur_before", ch["mtbf_before"]), s["protection"])
    sa = sp.sparing(item, qty, patrol_hours, ch.get("mtbur_after", ch["mtbf_after"]), s["protection"])

    L = case["lora"]
    options = [lo.LoraOption(**o) for o in L["option"]]
    lora_lines = lo.lora(item, L["unit_price"], ch["mtbf_after"], L["fleet_hours_per_year"], L["years"], options)

    modes = [fm.FailureMode(item=x.get("item", item), mtbf=x.get("mtbf", ch["mtbf_after"]),
                            **{k: v for k, v in x.items() if k not in ("item", "mtbf")})
             for x in case["fmeca"]["mode"]]
    rows = fm.criticality(modes, patrol_hours)

    parts = None
    if "parts_count" in case:
        P = case["parts_count"]
        parts = pc.parts_count(P["item"], P["environment"], [pc.PartLine(**p) for p in P["part"]])

    return Results(case, patrol_hours, before, after, ao, sb, sa, lora_lines, rows,
                   fm.check_alphas(modes), parts)


# ------------------------------------------------------------------ report

def _pct(x: float, digits: int = 3) -> str:
    return f"{100 * x:.{digits}f}%"


def _money(x: float) -> str:
    return f"${x:,.0f}"


def render(r: Results) -> str:
    c, ch = r.case["case"], r.case["change"]
    item = ch["block"]
    L = []
    w = L.append
    w(f"# LSA workbook: {c['title']}")
    w("")
    if c.get("fictional", True):
        w("> **Fictional example.** Equipment, figures and costs are invented to show the method. "
          "They are not real data for any ship, system or supplier.")
        w("")
    if c.get("linked_ec"):
        w(f"Linked engineering change: **{c['linked_ec']}** (see the EC impact report). "
          "This workbook does the numbers for the products that report marks as affected: "
          "RAM predictions and RBDs, spares and provisioning, LSA records (LORA, FMECA).")
        w("")
    w(f"Patrol assumed: {c['patrol_days']} days at {c['operating_hours_per_day']} operating hours/day "
      f"= **{r.patrol_hours:,.0f} h**. Fleet: {c.get('ships', '?')} ships.")
    w("")
    w(f"The change: `{item}` MTBF {ch['mtbf_before']:,.0f} h -> {ch['mtbf_after']:,.0f} h"
      + (f", MTBUR {ch['mtbur_before']:,.0f} h -> {ch['mtbur_after']:,.0f} h" if "mtbur_before" in ch else "") + ".")

    # 1. RAM
    w("")
    w("## 1. Reliability block diagram and availability")
    w("")
    w(f"Structure: `{r.rbd_after.describe()}`")
    w("")
    w("| Block | MTBF (h) | MTTR (h) | Inherent availability |")
    w("|---|---|---|---|")
    for b in r.case["block"]:
        mtbf = ch["mtbf_after"] if b["name"] == item else b["mtbf"]
        note = f" (was {ch['mtbf_before']:,.0f})" if b["name"] == item else ""
        w(f"| {b['name']} | {mtbf:,.0f}{note} | {b.get('mttr', 0):g} | "
          f"{_pct(ram.inherent_availability(mtbf, b.get('mttr', 0)))} |")
    w("")
    w("| System | Before | After |")
    w("|---|---|---|")
    w(f"| Inherent availability | {_pct(r.rbd_before.availability(), 4)} | {_pct(r.rbd_after.availability(), 4)} |")
    w(f"| Reliability over one patrol ({r.patrol_hours:,.0f} h, no repair) | "
      f"{_pct(r.rbd_before.reliability(r.patrol_hours), 2)} | {_pct(r.rbd_after.reliability(r.patrol_hours), 2)} |")
    w("")
    w("Patrol reliability assumes nothing is repaired during the patrol, so it is a worst case; "
      "with repair onboard, availability is the better measure.")

    a = r.ao
    w("")
    w(f"### Operational availability of `{item}`")
    w("")
    w("| Measure | Value |")
    w("|---|---|")
    w(f"| Inherent (design only) | {_pct(a['ai'])} |")
    w(f"| Operational, spare onboard | {_pct(a['ao_spare_onboard'])} |")
    w(f"| Operational, no spare (waits {a['logistic_delay_hours_no_spare']:,.0f} h for one) | {_pct(a['ao_no_spare'])} |")
    w("")
    w("Same equipment, same design. The difference between the last two rows is supply support.")

    # 2. Sparing
    w("")
    w("## 2. Sparing for one patrol")
    w("")
    sb, sa = r.sparing_before, r.sparing_after
    w(f"Target protection: **{_pct(sb.protection_target, 0)}** chance of no stock-out over the patrol, "
      f"{r.case['sparing']['installed_per_ship']} installed per ship.")
    w("")
    w("| | Expected demands | Spares to carry | Protection achieved |")
    w("|---|---|---|---|")
    w(f"| Before | {sb.demand:.2f} | **{sb.spares}** | {_pct(sb.achieved_protection, 1)} |")
    w(f"| After | {sa.demand:.2f} | **{sa.spares}** | {_pct(sa.achieved_protection, 1)} |")
    w("")
    w("Protection by number of spares (after):")
    w("")
    w("| Spares | " + " | ".join(str(k) for k, _ in sa.table) + " |")
    w("|---|" + "---|" * len(sa.table))
    w("| Protection | " + " | ".join(_pct(p, 1) for _, p in sa.table) + " |")

    # 3. LORA
    Lc = r.case["lora"]
    w("")
    w("## 3. Level of repair analysis (economic)")
    w("")
    w(f"Unit price {_money(Lc['unit_price'])}, fleet {Lc['fleet_hours_per_year']:,.0f} operating h/yr, "
      f"{Lc['years']} years, MTBF {ch['mtbf_after']:,.0f} h.")
    w("")
    w("| Rank | Option | Failures | Repair/replace cost | Pipeline stock | Fixed cost | Life-cycle cost |")
    w("|---|---|---|---|---|---|---|")
    for n, l in enumerate(r.lora, 1):
        w(f"| {n} | {l.option} | {l.failures_total:,.0f} | {_money(l.event_cost)} | {_money(l.pipeline_cost)} | "
          f"{_money(l.fixed_cost)} | **{_money(l.total)}** |")
    cons = [(l.option, c_) for l in r.lora for c_ in l.constraints]
    if cons:
        w("")
        w("Non-economic constraints to settle before choosing:")
        w("")
        for o, c_ in cons:
            w(f"- {o}: {c_}")

    # 4. FMECA
    w("")
    w(f"## 4. FMECA criticality (t = {r.patrol_hours:,.0f} h)")
    w("")
    w("| Severity | Item | Failure mode | Effect | alpha | beta | Cm |")
    w("|---|---|---|---|---|---|---|")
    for row in r.fmeca:
        m = row.mode
        w(f"| {m.severity} ({fm.SEVERITY[m.severity]}) | {m.item} | {m.mode} | {m.effect} | "
          f"{m.alpha:g} | {m.beta:g} | {row.cm:.2e} |")
    for warn in r.fmeca_warnings:
        w(f"\nWarning: {warn}")
    w("")
    w("Criticality matrix (count of modes):")
    w("")
    cols = sorted({fm.matrix_column(row.cm) for row in r.fmeca}, key=float)
    w("| Severity | " + " | ".join(f"Cm ~ {c_}" for c_ in cols) + " |")
    w("|---|" + "---|" * len(cols))
    for sev in fm.SEVERITY:
        counts = [sum(1 for row in r.fmeca if row.mode.severity == sev and fm.matrix_column(row.cm) == c_) for c_ in cols]
        w(f"| {sev} | " + " | ".join(str(x) if x else "" for x in counts) + " |")

    # 5. Parts count
    if r.parts:
        p = r.parts
        w("")
        w(f"## 5. Reliability prediction, parts count ({p.environment})")
        w("")
        w("| Part type | Qty | lambda_g (/10^6 h) | pi_Q | Contribution | Share | Source |")
        w("|---|---|---|---|---|---|---|")
        for line in p.lines:
            w(f"| {line.part_type} | {line.quantity} | {line.lambda_g:g} | {line.pi_q:g} | "
              f"{line.contribution:.1f} | {_pct(p.share(line), 0)} | {line.source} |")
        w("")
        w(f"Total {p.lambda_total:.1f} failures per 10^6 h, **predicted MTBF {p.mtbf:,.0f} h**, "
          f"against the {ch['mtbf_after']:,.0f} h used above "
          f"({(p.mtbf / ch['mtbf_after'] - 1) * 100:+.0f}%).")

    w("")
    w("---")
    w("")
    w("Generated by naval-ils-rag `lsa`. Formulas and assumptions are documented in `ilsrag/lsa/`. "
      "A planning aid, not an approved analysis.")
    return "\n".join(L) + "\n"
