"""Evaluation for retrieval and for the agent end to end.

Each question lists the document(s) a correct answer must draw on. Scoring is
at document level because chunk boundaries move every time the parser or
chunk size changes; the expected document doesn't.

Question types (optional "type" field):
  paraphrase    asked in a planner's words, not the document's
  cross_doc     needs two or more documents; also scored on whether ALL appear
  unanswerable  the corpus does not hold the answer; retrieval skips these, the
                agent must say the corpus doesn't cover it instead of answering
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .index import HybridIndex


def load_questions(path: Path) -> list[dict]:
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def _summ(rows: list[dict], ks) -> dict:
    n = len(rows) or 1
    out = {f"recall@{k}": round(sum(r[f"hit@{k}"] for r in rows) / n, 3) for k in ks}
    out["mrr"] = round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3)
    multi = [r for r in rows if len(r["expected"]) > 1]
    if multi:
        out[f"all_docs@{max(ks)}"] = round(sum(r["all_found"] for r in multi) / len(multi), 3)
    out["n"] = len(rows)
    return out


def evaluate_retrieval(index: HybridIndex, questions: list[dict], ks=(1, 3, 5)) -> dict:
    present = {c.doc_id for c in index.chunks}
    rows, skipped = [], []
    for q in questions:
        if q.get("answerable") is False:
            continue  # nothing to retrieve; judged in the agent eval
        expected = [d for d in q["expected_docs"] if d in present]
        if not expected:
            skipped.append(q["id"])  # its source document hasn't been ingested
            continue
        hits = index.search(q["question"], k=max(ks))
        ranked_docs: list[str] = []
        for h in hits:
            if h.chunk.doc_id not in ranked_docs:
                ranked_docs.append(h.chunk.doc_id)
        first = next((i for i, d in enumerate(ranked_docs) if d in expected), None)
        rows.append({
            "id": q["id"],
            "type": q.get("type", "direct"),
            "question": q["question"],
            "expected": expected,
            "got": ranked_docs[:max(ks)],
            "rank": None if first is None else first + 1,
            "all_found": all(d in ranked_docs[:max(ks)] for d in expected),
            **{f"hit@{k}": any(d in expected for d in ranked_docs[:k]) for k in ks},
        })
    by_type = defaultdict(list)
    for r in rows:
        by_type[r["type"]].append(r)
    summary = _summ(rows, ks)
    summary["skipped_missing_docs"] = skipped
    if len(by_type) > 1:
        summary["by_type"] = {t: _summ(rs, ks) for t, rs in by_type.items()}
    return {"summary": summary, "rows": rows}


# Crude but transparent: an "unanswerable" question passes if the answer says
# the corpus doesn't cover it. Read the transcripts too; this is a smoke test.
_DECLINE = re.compile(
    r"(corpus|passages?|documents?|sources?)\s+(does not|doesn't|do not|don't|did not)\s+"
    r"(cover|contain|include|say|address|give|provide|mention)"
    r"|not (covered|in the corpus|found in)|(couldn't|could not|cannot|can't) find"
    r"|no (passage|document|information)",
    re.I,
)


def evaluate_agent(agent, questions: list[dict], present: set[str]) -> dict:
    """End-to-end: does the answer cite an expected document, are all of its
    citations verified, and does it decline when it should? Costs API calls."""
    rows = []
    for q in questions:
        unanswerable = q.get("answerable") is False
        expected = [d for d in q["expected_docs"] if d in present]
        if not expected and not unanswerable:
            continue
        ans = agent.ask(q["question"])
        cited_docs = {c.chunk.doc_id for c in ans.citations if c.chunk}
        row = {
            "id": q["id"],
            "type": q.get("type", "direct"),
            "n_citations": len(ans.citations),
            "unverified": len(ans.unverified),
            "uncited_sentences": len(ans.uncited_sentences),
            "tool_calls": len(ans.tool_calls),
            "answer": ans.text,
        }
        if unanswerable:
            row["declined"] = bool(_DECLINE.search(ans.raw_text))
        else:
            row["cites_expected_doc"] = bool(cited_docs & set(expected))
        rows.append(row)

    ans_rows = [r for r in rows if "cites_expected_doc" in r]
    un_rows = [r for r in rows if "declined" in r]
    total_cites = sum(r["n_citations"] for r in rows)
    return {
        "summary": {
            "answers": len(rows),
            "cites_expected_doc": round(sum(r["cites_expected_doc"] for r in ans_rows) / max(1, len(ans_rows)), 3),
            "declined_when_unanswerable": (round(sum(r["declined"] for r in un_rows) / len(un_rows), 3)
                                           if un_rows else None),
            "citation_verified_rate": round(1 - sum(r["unverified"] for r in rows) / max(1, total_cites), 3),
            "avg_uncited_sentences": round(sum(r["uncited_sentences"] for r in rows) / max(1, len(rows)), 2),
            "avg_tool_calls": round(sum(r["tool_calls"] for r in rows) / max(1, len(rows)), 2),
        },
        "rows": rows,
    }
