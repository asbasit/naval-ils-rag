"""Synthetic fixture corpus.

Everything here is invented (the "Kestrel-class" doesn't exist) so the tests
can't be mistaken for real policy. It mimics the shape of the real corpus:
a multi-page PDF with running headers and numbered headings, a canada.ca-style
HTML page, and a USN-style instruction.
"""
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURE_MANIFEST = """
[[doc]]
id = "fx-policy"
title = "FIXTURE Policy 9001-0, Kestrel-class Maintenance Management"
issuer = "DND/CAF"
kind = "policy"
format = "html"
url = "https://example.invalid/fx-policy.html"

[[doc]]
id = "fx-eval"
title = "FIXTURE Evaluation of Kestrel-class Readiness"
issuer = "DND/CAF"
kind = "evaluation"
format = "pdf"
url = "https://example.invalid/fx-eval.pdf"

[[doc]]
id = "fx-usn"
title = "FIXTURE NAVINST 0000.1, Condition Monitoring for Surface Ships"
issuer = "USN"
kind = "instruction"
format = "pdf"
url = "https://example.invalid/fx-usn.pdf"
"""

POLICY_HTML = """<html><body><nav>Menu Home Contact</nav><main>
<h1 id="top">FIXTURE Policy 9001-0, Kestrel-class Maintenance Management</h1>
<h2 id="s2">2. Definitions</h2>
<p>Extended docking work period means a deep maintenance period in which the
Kestrel-class hull and its forty principal systems are repaired and upgraded so
that the vessel can operate for five years between deep maintenance periods.</p>
<h2 id="s3">3. Policy Direction</h2>
<p>The fleet maintenance authority shall schedule no more than one Kestrel-class
vessel in an extended docking work period at any time, to keep dockyard labour
within the capacity of the in-service support contract.</p>
<ul><li>planned maintenance shall be recorded in the maintenance management system within ten working days;</li>
<li>deferred defects older than ninety days shall be reported to the life cycle materiel manager.</li></ul>
<footer>Date modified: 2026-01-01</footer></main></body></html>"""


def _make_pdf(path: Path, title: str, pages: list[list[tuple[str, str]]]):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=letter)
    for n, sections in enumerate(pages, 1):
        y = 750
        c.setFont("Helvetica", 8)
        c.drawString(72, 770, "Information UNCLASSIFIED - FIXTURE DOCUMENT")
        c.setFont("Helvetica", 10)
        for heading, body in sections:
            c.setFont("Helvetica-Bold", 11)
            c.drawString(72, y, heading)
            y -= 18
            c.setFont("Helvetica", 10)
            words, line = body.split(), ""
            for w in words:
                if len(line) + len(w) > 90:
                    c.drawString(72, y, line)
                    y -= 13
                    line = ""
                line += w + " "
            c.drawString(72, y, line.strip())
            y -= 24
        c.setFont("Helvetica", 8)
        c.drawString(300, 40, f"{n}/{len(pages)}")
        c.showPage()
    c.save()


@pytest.fixture(scope="session")
def fixture_dirs(tmp_path_factory):
    root = tmp_path_factory.mktemp("fx")
    raw = root / "raw"
    raw.mkdir()
    (root / "manifest.toml").write_text(FIXTURE_MANIFEST)
    (raw / "fx-policy.html").write_text(POLICY_HTML)
    filler = ("The evaluation team interviewed staff at both coasts and reviewed "
              "maintenance records for the period under review. ") * 3
    _make_pdf(raw / "fx-eval.pdf", "eval", [
        [("1 INTRODUCTION", "This evaluation examined readiness of the Kestrel-class. " + filler)],
        [("2 FINDINGS", "Readiness fell because two vessels were removed from service for "
                        "modernization while the fleet maintenance facility lost thirty percent "
                        "of its trades staff. " + filler)],
        [("3 RECOMMENDATIONS", "The program should rebalance work between the fleet maintenance "
                               "facility and the in-service support contractor. " + filler)],
        [("4 ANNEX", "Annex material. " + filler)],
    ])
    _make_pdf(raw / "fx-usn.pdf", "usn", [
        [("1 PURPOSE", "This instruction establishes condition-based maintenance plus as the basis "
                       "for planned maintenance of surface ship gas turbines. Vibration and lube oil "
                       "analysis replace fixed-interval overhauls where the reliability-centered "
                       "maintenance analysis supports it. " + filler)],
    ])
    return root


@pytest.fixture(scope="session")
def fixture_index(fixture_dirs):
    from ilsrag.chunk import chunk_blocks
    from ilsrag.corpus import load_manifest
    from ilsrag.index import HybridIndex
    from ilsrag.parse import parse_document

    docs = load_manifest(fixture_dirs / "manifest.toml")
    chunks = []
    for meta in docs.values():
        chunks += chunk_blocks(meta, parse_document(meta.raw_path(fixture_dirs / "raw")))
    return HybridIndex.build(chunks, dense=False)
