"""Naval maintenance / ILS acronyms used for query expansion.

Planners ask in acronyms ("what triggers an EDWP?") while documents often
spell the term out once and abbreviate afterwards, or the reverse. Expanding
both directions closes that gap for keyword search.
"""
from __future__ import annotations

import re

ACRONYMS: dict[str, str] = {
    "ils": "integrated logistics support",
    "ilsp": "integrated logistics support plan",
    "ips": "integrated product support",
    "lsa": "logistics support analysis",
    "lcmm": "life cycle materiel manager",
    "lcc": "life cycle cost",
    "iss": "in-service support",
    "issc": "in-service support contract",
    "vissc": "victoria in-service support contract",
    "ma&s": "materiel acquisition and support",
    "adm(mat)": "assistant deputy minister materiel",
    "sbca": "sustainment business case analysis",
    "daod": "defence administrative orders and directives",
    "rcn": "royal canadian navy",
    "caf": "canadian armed forces",
    "dnd": "department of national defence",
    "fmf": "fleet maintenance facility",
    "mep": "maritime equipment program",
    "mepm": "maritime equipment program management",
    "hcm": "halifax-class modernization",
    "felex": "frigate life extension",
    "edwp": "extended docking work period",
    "rcm": "reliability-centered maintenance reliability centred maintenance",
    "cbm": "condition-based maintenance",
    "cbm+": "condition-based maintenance plus",
    "pms": "planned maintenance system",
    "pmi": "preventive maintenance instruction",
    "pmtr": "preventive maintenance task requirements",
    "ismo": "in-service maintenance optimization",
    "mp-ea": "maintenance planning engineering analysis",
    "fleetmer": "fleet maintenance effectiveness review",
    "mer": "maintenance effectiveness review",
    "cmp": "class maintenance plan",
    "mtbf": "mean time between failures",
    "mttr": "mean time to repair",
    "fmea": "failure modes and effects analysis",
    "fmeca": "failure modes effects and criticality analysis",
    "rams": "reliability availability maintainability safety",
    "ram": "reliability availability maintainability",
    "ncs": "nato codification system",
    "alp": "allied logistics publication",
    "s&te": "support and test equipment",
    "cfto": "canadian forces technical order",
    "navsea": "naval sea systems command",
    "insurv": "board of inspection and survey",
    "aops": "arctic and offshore patrol ship",
    "jss": "joint support ship",
    "mcdv": "maritime coastal defence vessel",
}

_EXPANSION_TO_ACRONYM = {v: k for k, v in ACRONYMS.items()}


def expand_query(query: str) -> str:
    """Append expansions for acronyms in the query, and acronyms for spelled-out
    terms. The original query is kept intact at the front."""
    lowered = query.lower()
    extra: list[str] = []
    for token in re.findall(r"[a-z0-9&()+\-]+", lowered):
        if token in ACRONYMS:
            extra.append(ACRONYMS[token])
    for phrase, acro in _EXPANSION_TO_ACRONYM.items():
        if phrase in lowered:
            extra.append(acro)
    return query if not extra else f"{query} {' '.join(extra)}"
