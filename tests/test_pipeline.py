from __future__ import annotations
import json

from types import SimpleNamespace

import pytest

from ilsrag.agent import MaintenanceAgent, ToolBox, resolve_citations
from ilsrag.corpus import load_manifest
from ilsrag.glossary import expand_query
from ilsrag.index import HybridIndex, tokenize
from ilsrag.parse import parse_pdf, parse_html


# ------------------------------------------------------------------ parsing

def test_pdf_pages_and_boilerplate(fixture_dirs):
    blocks = parse_pdf(fixture_dirs / "raw" / "fx-eval.pdf")
    assert {b.page for b in blocks} == {1, 2, 3, 4}
    text = " ".join(b.text for b in blocks)
    assert "Information UNCLASSIFIED" not in text, "running header should be stripped"
    assert "2/4" not in text, "page numbers should be stripped"
    findings = [b for b in blocks if "thirty percent" in b.text]
    assert findings and findings[0].page == 2 and findings[0].heading == "2 FINDINGS"


def test_single_page_pdf_drops_marking(fixture_dirs):
    blocks = parse_pdf(fixture_dirs / "raw" / "fx-usn.pdf")
    assert blocks and all("UNCLASSIFIED" not in b.text for b in blocks)
    assert blocks[0].heading == "1 PURPOSE"


def test_html_drops_nav_and_keeps_anchor(fixture_dirs):
    blocks = parse_html(fixture_dirs / "raw" / "fx-policy.html")
    text = " ".join(b.text for b in blocks)
    assert "Menu Home" not in text and "Date modified" not in text
    one_at_a_time = [b for b in blocks if "no more than one" in b.text][0]
    assert one_at_a_time.anchor == "s3" and one_at_a_time.heading.startswith("3.")


# ----------------------------------------------------------------- chunking

def test_chunks_never_span_pages(fixture_index):
    for c in fixture_index.chunks:
        if c.doc_id == "fx-eval":
            assert c.page is not None
            assert c.url.endswith(f"#page={c.page}")
    ids = [c.chunk_id for c in fixture_index.chunks]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------- retrieval

def test_tokenizer_keeps_identifiers():
    toks = tokenize("Per MIL-STD-3034A and NAVSEAINST 4790.26A, CBM+ applies")
    assert "mil-std-3034a" in toks and "3034a" in toks
    assert "4790.26a" in toks and "cbm+" in toks


def test_acronym_expansion():
    assert "extended docking work period" in expand_query("How often is an EDWP?")
    assert "rcm" in expand_query("condition-based maintenance vs reliability-centered maintenance").lower() \
        or "cbm" in expand_query("condition-based maintenance").lower()


def test_acronym_query_finds_spelled_out_text(fixture_index):
    # The fixture never writes "EDWP"; expansion has to bridge it.
    hits = fixture_index.search("How long between EDWPs for a Kestrel?", k=3)
    assert hits and hits[0].chunk.doc_id == "fx-policy"


def test_issuer_filter(fixture_index):
    hits = fixture_index.search("condition-based maintenance", k=5, issuers=["DND/CAF"])
    assert hits and all(h.chunk.issuer == "DND/CAF" for h in hits)
    hits = fixture_index.search("condition-based maintenance", k=5, issuers=["USN"])
    assert hits and hits[0].chunk.doc_id == "fx-usn"


def test_save_load_roundtrip(fixture_index, tmp_path):
    fixture_index.save(tmp_path)
    again = HybridIndex.load(tmp_path)
    q = "why did readiness fall"
    assert [h.chunk.chunk_id for h in again.search(q)] == [h.chunk.chunk_id for h in fixture_index.search(q)]


def test_dense_hybrid(fixture_dirs):
    pytest.importorskip("fastembed")
    from ilsrag.chunk import chunk_blocks
    from ilsrag.parse import parse_document

    docs = load_manifest(fixture_dirs / "manifest.toml")
    chunks = [c for m in docs.values() for c in chunk_blocks(m, parse_document(m.raw_path(fixture_dirs / "raw")))]
    try:
        index = HybridIndex.build(chunks, dense=True)
    except Exception as exc:  # no network for model download
        pytest.skip(f"embedding model unavailable: {exc}")
    # Pure paraphrase: no keyword overlap with "trades staff" / "removed from service".
    hits = index.search("what caused the drop in ship availability", k=3)
    assert any(h.chunk.doc_id == "fx-eval" and h.chunk.page == 2 for h in hits)
    assert any(h.dense_rank is not None for h in hits)


# -------------------------------------------------------------- citations

def test_resolve_citations_flags_fabricated(fixture_index):
    real = fixture_index.chunks[0].chunk_id
    seen = {real: fixture_index.chunks[0]}
    raw = (f"Only one vessel may be in deep maintenance at once [{real}]. "
           f"The limit was set in 1999 by the fleet commander [fx-policy#0999; {real}]. "
           "This sentence has more than eight words and no citation at all.")
    text, cites, uncited = resolve_citations(raw, seen, fixture_index)
    assert "[1]" in text and "[2, 1]" in text
    assert [c.verified for c in cites] == [True, False]
    assert cites[1].chunk is None
    assert len(uncited) == 1


# -------------------------------------------------------------------- agent

def _block(**kw):
    return SimpleNamespace(**kw)


class FakeClient:
    """Scripted stand-in for anthropic.Anthropic: first searches, then answers
    citing whatever chunk the search returned plus one invented id."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return SimpleNamespace(content=[
                _block(type="text", text="Searching."),
                _block(type="tool_use", id="tu1", name="search_corpus",
                       input={"query": "EDWP one at a time Kestrel", "issuers": ["DND/CAF"]}),
            ])
        tool_result = kwargs["messages"][-1]["content"][0]["content"]
        import json
        first = json.loads(tool_result)["results"][0]["chunk_id"]
        return SimpleNamespace(content=[_block(
            type="text",
            text=f"Only one Kestrel-class vessel may be in an extended docking work period at a time [{first}]. "
                 f"This keeps dockyard labour within contract capacity [fx-policy#0042].")])


def test_agent_loop_and_verification(fixture_index):
    client = FakeClient()
    agent = MaintenanceAgent(fixture_index, client=client, model="test-model")
    ans = agent.ask("Can two Kestrels be in EDWP together?")
    assert len(client.calls) == 2
    assert client.calls[0]["tool_choice"] == {"type": "auto"}
    assert ans.tool_calls[0]["tool"] == "search_corpus"
    assert len(ans.citations) == 2
    assert ans.citations[0].verified and ans.citations[0].chunk.doc_id == "fx-policy"
    assert not ans.citations[1].verified
    rendered = ans.render()
    assert "UNVERIFIED" in rendered and "#s3" in rendered


def test_agent_forced_answer_on_last_turn(fixture_index):
    class Looper(FakeClient):
        def create(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["tool_choice"]["type"] == "none":
                return SimpleNamespace(content=[_block(type="text", text="Corpus doesn't cover it.")])
            return SimpleNamespace(content=[_block(type="tool_use", id=f"t{len(self.calls)}",
                                                   name="list_documents", input={})])
    client = Looper()
    ans = MaintenanceAgent(fixture_index, client=client, max_turns=3).ask("anything")
    assert len(client.calls) == 3 and ans.raw_text == "Corpus doesn't cover it."


def test_toolbox_read_passage(fixture_index):
    tb = ToolBox(fixture_index)
    cid = next(c.chunk_id for c in fixture_index.chunks if c.doc_id == "fx-eval" and c.seq == 1)
    out = tb.run("read_passage", {"chunk_id": cid, "radius": 1})
    assert "fx-eval#0000" in out and "fx-eval#0002" in out
    assert "unknown chunk_id" in tb.run("read_passage", {"chunk_id": "nope#0001"})


def test_html_real_world_shapes(tmp_path):
    """Shapes found in real canada.ca pages: article body inside <aside>,
    <p> nested in <dd>, text in a <div> separated by <br>, archive banner."""
    html = """<html><body><main>
    <section class="gc-archv"><h2>We have archived this page</h2><p>You can use it for research or reference.</p></section>
    <h1 id="t">Fleet Status</h1>
    <aside><div class="mwsbodytext"><h2>Achievements</h2>
      <p>The fixture fleet has accumulated approximately 900 days at sea since entering service.</p></div></aside>
    <dl><dt>ADM(IM)</dt><dd><p>Assistant Deputy Minister (Information Management) of the fixture.</p></dd></dl>
    <p><strong>available</strong> (<em>disponible</em>)</p><p>Ready for operations from a support view.</p>
    <div>Deep maintenance occurs every six years for each fixture boat.<br>Only one boat is in deep maintenance at a time.</div>
    </main></body></html>"""
    p = tmp_path / "x.html"
    p.write_text(html)
    blocks = parse_html(p)
    text = " ".join(b.text for b in blocks)
    assert "900 days at sea" in text, "content inside <aside> must be kept"
    assert text.count("Assistant Deputy Minister (Information Management)") == 1, "no double read of dd>p"
    assert "Only one boat is in deep maintenance" in text, "div text with <br> must be kept"
    assert "archived" not in text.lower()
    assert "available (disponible)" in text, "short bold definition terms must be kept"
    assert [b for b in blocks if "900 days" in b.text][0].heading == "Achievements"


def test_pdf_heading_rejects_table_rows():
    from ilsrag.parse import _looks_like_heading
    assert _looks_like_heading("2.1 Relevance")
    assert _looks_like_heading("Executive Summary")
    assert _looks_like_heading("ASSISTANT DEPUTY MINISTER REVIEW")
    assert not _looks_like_heading("FY 2013/14 FY 2014/15 FY 2015/16")
    assert not _looks_like_heading("ER WIN 90% 75% 100% 50%")
    assert not _looks_like_heading("MCDV")


def test_mcp_server_tools(fixture_index, tmp_path, monkeypatch):
    """The MCP server exposes the same tools as the agent and returns the same data."""
    pytest.importorskip("mcp")
    import asyncio
    import ilsrag.mcp_server as ms

    fixture_index.save(tmp_path / "data" / "index")
    monkeypatch.setattr(ms, "HOME", tmp_path)
    monkeypatch.setenv("ILSRAG_DENSE", "0")
    monkeypatch.setenv("ILSRAG_RERANK", "0")
    ms._toolbox.cache_clear()

    tools = {t.name for t in asyncio.run(ms.server.list_tools())}
    assert tools == {"search_corpus", "read_passage", "list_documents", "ec_impact"}

    out = ms.search_corpus("deep maintenance one at a time", k=3, issuers=["DND/CAF"])
    assert out["results"] and out["results"][0]["issuer"] == "DND/CAF"
    first = out["results"][0]["chunk_id"]
    assert first in json.dumps(ms.read_passage(first, radius=0))
    assert {d["id"] for d in ms.list_documents()["documents"]} == {"fx-policy", "fx-eval", "fx-usn"}
    ms._toolbox.cache_clear()


def test_rerank_reorders_shortlist(fixture_index):
    """A reranker reorders the fused shortlist; the per-document cap still applies."""
    class FakeReranker:
        def scores(self, query, texts):
            import numpy as np
            return np.array([10.0 if "thirty percent" in t else 0.0 for t in texts])

    plain = fixture_index.search("maintenance", k=3)
    fixture_index.reranker = FakeReranker()
    try:
        hits = fixture_index.search("maintenance", k=3)
    finally:
        fixture_index.reranker = None
    assert "thirty percent" in hits[0].chunk.text
    assert [h.chunk.chunk_id for h in hits] != [h.chunk.chunk_id for h in plain] or "thirty percent" in plain[0].chunk.text


def test_ingest_refuses_wrong_document(fixture_dirs, tmp_path, capsys):
    """A download that redirected to a different document must not be indexed
    under the manifest's name (NAVSEA links now serve an aviation manual)."""
    import shutil
    from ilsrag.cli import main
    m = (fixture_dirs / "manifest.toml").read_text()
    m = m.replace('id = "fx-usn"\n', 'id = "fx-usn"\nexpect = "condition-based maintenance plus"\n')
    m = m.replace('id = "fx-eval"\n', 'id = "fx-eval"\nexpect = "Shipboard Fire Main Survey"\n')
    (tmp_path / "manifest.toml").write_text(m)
    shutil.copytree(fixture_dirs / "raw", tmp_path / "raw")
    main(["--manifest", str(tmp_path / "manifest.toml"), "--data-dir", str(tmp_path), "ingest", "--no-dense"])
    out = capsys.readouterr().out
    assert "WRONG  fx-eval" in out
    assert "ok     fx-usn" in out
    ids = (tmp_path / "index" / "chunks.jsonl").read_text()
    assert "fx-eval#" not in ids and "fx-usn#" in ids


def test_embedding_cache_resumes(fixture_index, tmp_path):
    """Interrupted or repeated ingests reuse cached vectors instead of re-embedding."""
    import numpy as np
    from ilsrag.index import _embed_cached

    class CountingEmbedder:
        model_name = "fake"
        calls = 0

        def passages(self, texts):
            CountingEmbedder.calls += len(texts)
            return np.array([[len(t), 1.0] for t in texts], dtype=np.float32)

    texts = [c.text for c in fixture_index.chunks]
    cache = tmp_path / "cache.npz"
    first = _embed_cached(CountingEmbedder(), texts[:3], cache, batch=2, progress=None)
    assert CountingEmbedder.calls == 3
    full = _embed_cached(CountingEmbedder(), texts, cache, batch=2, progress=None)
    assert CountingEmbedder.calls == len(texts)  # only the new ones were embedded
    assert np.allclose(full[:3], first)


def test_evidence_rank(fixture_index):
    """Passage-level scoring: right document is not enough, the passage must hold the answer."""
    from ilsrag.evaluate import evaluate_retrieval
    qs = [{"id": "e1", "question": "deep maintenance one at a time", "expected_docs": ["fx-policy"],
           "evidence": ["no more than one Kestrel-class"]},
          {"id": "e2", "question": "deep maintenance one at a time", "expected_docs": ["fx-policy"],
           "evidence": ["phrase that appears nowhere"]}]
    res = evaluate_retrieval(fixture_index, qs)
    ranks = {r["id"]: r["evidence_rank"] for r in res["rows"]}
    assert ranks["e1"] is not None and ranks["e2"] is None
    assert res["summary"]["evidence@5"] == 0.5


def test_short_list_items_kept(tmp_path):
    """DAOD 3007-0 lists the twelve ILS elements as short <li> items; all must survive."""
    items = ["maintenance management;", "supply support;", "computer resources;", "technical data;",
             "design influence;", "support equipment."]
    html = "<html><body><main><h2>Context</h2><p>ILS consists of the following ILS elements:</p><ol>" + \
           "".join(f"<li>{i}</li>" for i in items) + "</ol></main></body></html>"
    p = tmp_path / "x.html"
    p.write_text(html)
    text = " ".join(b.text for b in parse_html(p))
    for i in items:
        assert i.rstrip(";.") in text


# ------------------------------------------------------------- EC impact

EC_RULES = """
[vocabulary]
part_number = "New part number"
software = "Software change"
safety = "Safety-related"

[[rule]]
id = "cm"
product = "Configuration records"
ils_element = "Configuration management"
triggers = ["always"]
action = "Update the baseline."
basis = [{ doc = "fx-policy", evidence = "no more than one Kestrel-class" }]

[[rule]]
id = "spares"
product = "Spares and provisioning"
ils_element = "Supply support"
triggers = ["part_number"]
action = "Rerun sparing."
basis = [{ doc = "fx-eval", evidence = "thirty percent of its trades staff" }]

[[rule]]
id = "sw"
product = "Software support"
ils_element = "Computer resources"
triggers = ["software"]
action = "Update software baseline."
basis = [{ doc = "fx-usn", evidence = "a phrase that is not in the corpus" }]

[[rule]]
id = "safety"
product = "Safety precautions"
ils_element = "Technical data"
triggers = ["safety"]
action = "Review warnings."
basis = []
"""


def _ec_setup(tmp_path, changes: str):
    from ilsrag import ec_impact as ec
    (tmp_path / "rules.toml").write_text(EC_RULES)
    (tmp_path / "ec.toml").write_text('id = "EC-T"\ntitle = "Test change"\n[changes]\n' + changes)
    vocab, rules = ec.load_rules(tmp_path / "rules.toml")
    return ec, vocab, rules, ec.load_change(tmp_path / "ec.toml", vocab)


def test_ec_impact_statuses_and_basis(fixture_index, tmp_path):
    ec, vocab, rules, change = _ec_setup(tmp_path, 'part_number = true\nsoftware = false\n')
    a = ec.assess(change, rules, vocab, fixture_index.chunks)
    status = {f.rule.id: f.status for f in a.findings}
    # "always" and a yes-trigger are affected; a no-trigger is not; an omitted
    # characteristic is unknown, so its product goes to the confirm list.
    assert status == {"cm": "affected", "spares": "affected", "sw": "not affected", "safety": "confirm"}
    cm = next(f for f in a.findings if f.rule.id == "cm")
    assert cm.citations[0].found and cm.citations[0].chunk.doc_id == "fx-policy"
    spares = next(f for f in a.findings if f.rule.id == "spares")
    assert spares.citations[0].chunk.page == 2  # cites the right page
    md = ec.render_markdown(a)
    assert "## Affected ILS products (2)" in md and "## Confirm with the EC team (1)" in md
    assert "p.2" in md and "Basis not found" not in md  # sw is not affected, so its missing basis isn't reported
    # safety was omitted, so it is an open question naming the product it bears on
    assert a.open_questions() and a.open_questions()[0][0] == "safety"
    assert "## Open questions for the EC team (1)" in md and "Safety precautions (confirm)" in md


def test_ec_impact_missing_basis_and_validation(fixture_index, tmp_path):
    ec, vocab, rules, change = _ec_setup(tmp_path, 'software = true\n')
    a = ec.assess(change, rules, vocab, fixture_index.chunks)
    assert [c.evidence for c in a.missing_basis] == ["a phrase that is not in the corpus"]
    assert "## Basis not found" in ec.render_markdown(a)
    problems = ec.check_rules(rules, fixture_index.chunks)
    assert len(problems) == 1 and "sw" in problems[0]
    (tmp_path / "bad.toml").write_text('id = "X"\ntitle = "Y"\n[changes]\nwarp_drive = true\n')
    with pytest.raises(ValueError):
        ec.load_change(tmp_path / "bad.toml", vocab)
    (tmp_path / "bad2.toml").write_text('id = "X"\ntitle = "Y"\n[changes]\nsoftware = "maybe"\n')
    with pytest.raises(ValueError):
        ec.load_change(tmp_path / "bad2.toml", vocab)


def test_shipped_ec_rules_and_examples_load():
    """The real rules file and example ECs parse and use only known characteristics."""
    from pathlib import Path
    from ilsrag import ec_impact as ec
    root = Path(__file__).resolve().parent.parent
    vocab, rules = ec.load_rules(root / "corpus" / "ec_rules.toml")
    assert len(rules) >= 15 and all(r.basis for r in rules)
    for f in sorted((root / "examples" / "ec").glob("*.toml")):
        change = ec.load_change(f, vocab)
        assert change.id.startswith("EC-DEMO")
