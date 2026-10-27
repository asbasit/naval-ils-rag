"""LSA calculations checked against values worked by hand."""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from ilsrag.lsa import fmeca as fm
from ilsrag.lsa import lora as lo
from ilsrag.lsa import parts_count as pc
from ilsrag.lsa import ram
from ilsrag.lsa import sparing as sp

ROOT = Path(__file__).resolve().parent.parent


def test_availability_measures():
    assert ram.inherent_availability(1000, 10) == pytest.approx(1000 / 1010)
    # MTBM with corrective (1/1000) and preventive (1/500) actions: 1/(0.001+0.002)
    assert ram.mtbm(1000, 500) == pytest.approx(333.333, rel=1e-4)
    assert ram.operational_availability(1000, 90) == pytest.approx(1000 / 1090)
    assert ram.reliability(1000, 1000) == pytest.approx(math.exp(-1))
    with pytest.raises(ValueError):
        ram.inherent_availability(0, 1)


def test_rbd_series_parallel_kofn():
    a = ram.Block("a", mtbf=900, mttr=100)        # availability 0.9
    b = ram.Block("b", mtbf=900, mttr=100)
    c = ram.Block("c", mtbf=900, mttr=100)
    assert ram.Series([a, b]).availability() == pytest.approx(0.81)
    assert ram.Parallel([a, b]).availability() == pytest.approx(0.99)
    # 2-of-3 at 0.9: 3*0.9^2*0.1 + 0.9^3 = 0.972
    assert ram.KofN(2, [a, b, c]).availability() == pytest.approx(0.972)
    # 1-of-n equals parallel, n-of-n equals series
    assert ram.KofN(1, [a, b]).availability() == pytest.approx(0.99)
    assert ram.KofN(2, [a, b]).availability() == pytest.approx(0.81)
    built = ram.build_rbd({"series": ["a", {"parallel": ["b", "c"]}]}, {"a": a, "b": b, "c": c})
    assert built.availability() == pytest.approx(0.9 * 0.99)


def test_poisson_sparing():
    # lambda = 2: P(<=3) = 0.857, P(<=4) = 0.947, so 90% needs 4
    assert sp.poisson_cdf(3, 2) == pytest.approx(0.8571, abs=1e-4)
    assert sp.spares_for_protection(2, 0.90) == 4
    r = sp.sparing("x", quantity=2, operating_hours=1800, mtbur=3600, protection=0.90)
    assert r.demand == pytest.approx(1.0)
    assert r.spares == 2 and r.achieved_protection == pytest.approx(0.9197, abs=1e-4)
    assert sp.spares_for_protection(0.0, 0.95) == 0


def test_lora_ranking_and_costs():
    opts = [
        lo.LoraOption("discard", "discard", turnaround_days=73, transport_cost=0),
        lo.LoraOption("depot", "repair", turnaround_days=36.5, repair_cost=100, fixed_cost=1000),
    ]
    # 10,000 h/yr / MTBF 1,000 = 10 failures/yr, 5 years = 50 failures
    lines = lo.lora("x", unit_price=500, mtbf=1000, fleet_hours_per_year=10000, years=5, options=opts)
    depot = next(l for l in lines if l.option == "depot")
    discard = next(l for l in lines if l.option == "discard")
    assert depot.event_cost == pytest.approx(50 * 100)
    assert depot.pipeline_cost == pytest.approx(10 * 0.1 * 500)     # 10/yr x 0.1 yr x $500
    assert depot.total == pytest.approx(5000 + 500 + 1000)
    assert discard.total == pytest.approx(50 * 500 + 10 * 0.2 * 500)
    assert lines[0].option == "depot"


def test_fmeca_criticality_and_ordering():
    modes = [
        fm.FailureMode("psu", "no output", "channel lost", "III", alpha=0.6, beta=1.0, mtbf=1000),
        fm.FailureMode("psu", "overvoltage", "damage", "II", alpha=0.4, beta=0.5, mtbf=1000),
    ]
    rows = fm.criticality(modes, t=100)
    assert rows[0].mode.mode == "overvoltage"          # worse severity ranks first
    assert rows[0].cm == pytest.approx(0.5 * 0.4 * 0.001 * 100)
    assert rows[1].cm == pytest.approx(0.06)
    assert fm.check_alphas(modes) == []
    assert fm.check_alphas(modes[:1])                  # 0.6 alone doesn't sum to 1
    with pytest.raises(ValueError):
        fm.FailureMode("x", "m", "e", "V", 0.5, 0.5, 100).criticality(1)


def test_parts_count():
    r = pc.parts_count("x", "env", [pc.PartLine("cap", 10, 2.0, 1.0), pc.PartLine("ic", 5, 4.0, 2.0)])
    assert r.lambda_total == pytest.approx(60.0)
    assert r.mtbf == pytest.approx(1e6 / 60)
    assert r.lines[0].part_type == "ic"                # largest contributor first


def test_workbook_example_runs():
    from ilsrag.lsa import workbook as wb
    r = wb.run(ROOT / "examples" / "lsa" / "radar-psu.toml")
    assert r.patrol_hours == 1800
    assert r.rbd_after.reliability(1800) > r.rbd_before.reliability(1800)
    assert r.sparing_after.spares < r.sparing_before.spares
    assert r.fmeca_warnings == []
    md = wb.render(r)
    assert "Fictional example" in md and "## 5. Reliability prediction" in md
