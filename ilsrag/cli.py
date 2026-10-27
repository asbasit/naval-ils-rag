"""Command line: fetch -> ingest -> search / ask / eval."""
from __future__ import annotations

import argparse
import json
import re
import os
import sys
from pathlib import Path

from .chunk import chunk_blocks
from .corpus import fetch_all, load_manifest
from .index import HybridIndex
from .parse import parse_document

ROOT = Path(__file__).resolve().parent.parent


def _paths(args):
    data = Path(args.data_dir)
    return Path(args.manifest), data / "raw", data / "index"


def cmd_fetch(args):
    manifest, raw, _ = _paths(args)
    report = fetch_all(load_manifest(manifest), raw, force=args.force)
    ok = sum(l.startswith(("[ok]", "[cached]")) for l in report)
    print(f"\n{ok} of {len(report)} documents ready in {raw}")


def _document_head(path: Path, blocks) -> str:
    """Opening text of a document for the identity check. For PDFs read the raw
    first pages: the parser strips running headers, and a standard's own number
    ("MIL-STD-3034A") is exactly what it prints in every page header."""
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        raw = " ".join((reader.pages[i].extract_text() or "") for i in range(min(3, len(reader.pages))))
    else:
        raw = " ".join(f"{b.heading} {b.text}" for b in blocks[:40])
    return re.sub(r"\s+", " ", raw).lower()


def cmd_ingest(args):
    manifest, raw, index_dir = _paths(args)
    docs = load_manifest(manifest)
    chunks, report = [], []
    for meta in docs.values():
        path = meta.raw_path(raw)
        if not path.exists():
            report.append(f"  skip   {meta.id:34s} (not downloaded)")
            continue
        try:
            blocks = parse_document(path)
        except Exception as exc:
            report.append(f"  FAIL   {meta.id:34s} {exc}")
            continue
        if meta.expect:
            # Identity check: a URL that now redirects elsewhere still yields a
            # valid PDF. Make sure the file is the document the manifest names.
            head = _document_head(path, blocks)
            if re.sub(r"\s+", " ", meta.expect).lower() not in head:
                report.append(f"  WRONG  {meta.id:34s} expected '{meta.expect}' near the start; "
                              "the file looks like a different document, not indexed")
                continue
        doc_chunks = chunk_blocks(meta, blocks)
        if not doc_chunks:
            report.append(f"  EMPTY  {meta.id:34s} (no text extracted; scanned PDF? needs OCR)")
            continue
        chunks.extend(doc_chunks)
        pages = {c.page for c in doc_chunks if c.page}
        report.append(f"  ok     {meta.id:34s} {len(doc_chunks):4d} chunks"
                      + (f", {len(pages)} pages" if pages else ""))
    print("\n".join(report))
    if not chunks:
        sys.exit("Nothing to index. Run `fetch` first, or check data/raw/.")
    print(f"Indexing {len(chunks)} chunks (dense={'off' if args.no_dense else 'on'}) ...")
    index_dir.mkdir(parents=True, exist_ok=True)

    def progress(done, total):
        print(f"  embedded {done}/{total} new passages", flush=True)

    index = HybridIndex.build(chunks, dense=not args.no_dense,
                              cache_path=index_dir / "embedding_cache.npz", progress=progress)
    index.save(index_dir)
    print(f"Saved to {index_dir}")


def _load_index(args) -> HybridIndex:
    _, _, index_dir = _paths(args)
    if not (index_dir / "index_info.json").exists():
        sys.exit("No index found. Run `fetch` then `ingest` first.")
    return HybridIndex.load(index_dir, dense=not getattr(args, "no_dense", False),
                            rerank=_rerank_setting(getattr(args, "no_rerank", False)))


def _rerank_setting(disabled: bool = False):
    """Reranking is on by default (best on the eval, ~3 s per search on CPU).
    --no-rerank or ILSRAG_RERANK=0 turns it off; ILSRAG_RERANK=<model> picks a model."""
    env = os.environ.get("ILSRAG_RERANK", "1")
    if disabled or env == "0":
        return None
    return True if env == "1" else env


def cmd_search(args):
    from .agent import extractive_answer
    print(extractive_answer(_load_index(args), args.query, k=args.k))


def cmd_ask(args):
    index = _load_index(args)
    if args.no_llm:
        from .agent import extractive_answer
        print(extractive_answer(index, args.question))
        return
    from .agent import MaintenanceAgent
    agent = MaintenanceAgent(index, model=args.model) if args.model else MaintenanceAgent(index)
    answer = agent.ask(args.question, verbose=args.verbose)
    if args.json:
        print(json.dumps(answer.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(answer.render())
    if answer.unverified:
        sys.exit(2)  # non-zero so scripts notice an answer with unverified citations


def cmd_eval(args):
    import time
    from .evaluate import evaluate_agent, evaluate_retrieval, load_questions
    index = _load_index(args)
    qpath = Path(args.questions)
    questions = load_questions(qpath)
    result = evaluate_retrieval(index, questions)
    for r in result["rows"]:
        mark = "✓" if r["hit@5"] else "✗"
        both = "" if len(r["expected"]) < 2 else ("  [all docs found]" if r["all_found"] else "  [missing a doc]")
        evid = "" if not r.get("has_evidence") else f"  passage={r['evidence_rank'] or '-'}"
        print(f"{mark} {r['id']:5s} {r['type']:11s} rank={r['rank'] or '-':>2}{evid}  {r['question'][:60]}{both}")
        if not r["hit@5"] or not r["all_found"]:
            print(f"        expected {r['expected']}, got {r['got']}")
    print(json.dumps(result["summary"], indent=2))

    out_dir = qpath.parent / "results"
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M")
    mode = ("bm25" if args.no_dense else "hybrid") + ("+rerank" if index.reranker else "")
    (out_dir / f"{qpath.stem}-retrieval-{mode}-{stamp}.json").write_text(json.dumps(result, indent=2))

    if args.agent:
        from .agent import MaintenanceAgent
        present = {c.doc_id for c in index.chunks}
        agent_res = evaluate_agent(MaintenanceAgent(index), questions, present)
        for r in agent_res["rows"]:
            ok = r.get("cites_expected_doc", r.get("declined"))
            print(f"{'✓' if ok else '✗'} {r['id']:5s} {r['type']:11s} cites={r['n_citations']} "
                  f"unverified={r['unverified']} tools={r['tool_calls']}")
        print(json.dumps(agent_res["summary"], indent=2))
        (out_dir / f"{qpath.stem}-agent-{stamp}.json").write_text(json.dumps(agent_res, indent=2, ensure_ascii=False))
    print(f"Results saved in {out_dir}")


def cmd_docs(args):
    manifest, raw, _ = _paths(args)
    for meta in load_manifest(manifest).values():
        state = "have" if meta.raw_path(raw).exists() else ("manual" if meta.fetch == "manual" else "----")
        print(f"[{state:6s}] {meta.id:34s} {meta.issuer:8s} {meta.title}")


def main(argv=None):
    p = argparse.ArgumentParser(prog="ilsrag", description="Naval maintenance-planning RAG demo")
    p.add_argument("--manifest", default=str(ROOT / "corpus" / "manifest.toml"))
    p.add_argument("--data-dir", default=str(ROOT / "data"))
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("fetch", help="download public documents in the manifest")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("ingest", help="parse, chunk and index downloaded documents")
    s.add_argument("--no-dense", action="store_true", help="BM25 only, no embedding model")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("docs", help="show corpus status")
    s.set_defaults(func=cmd_docs)

    s = sub.add_parser("search", help="hybrid search, no LLM")
    s.add_argument("query")
    s.add_argument("-k", type=int, default=5)
    s.add_argument("--no-dense", action="store_true", help="keyword search only, no embeddings")
    s.add_argument("--no-rerank", action="store_true", help="skip the cross-encoder rerank (faster, less precise)")
    s.set_defaults(func=cmd_search)

    s = sub.add_parser("ask", help="ask the agent a maintenance-planning question")
    s.add_argument("question")
    s.add_argument("--model", default=None)
    s.add_argument("--no-llm", action="store_true", help="extractive answer, no API call")
    s.add_argument("--json", action="store_true")
    s.add_argument("-v", "--verbose", action="store_true", help="print tool calls")
    s.add_argument("--no-dense", action="store_true", help="keyword search only, no embeddings")
    s.add_argument("--no-rerank", action="store_true", help="skip the cross-encoder rerank (faster, less precise)")
    s.set_defaults(func=cmd_ask)

    s = sub.add_parser("eval", help="retrieval recall@k / MRR on the question set")
    s.add_argument("--questions", default=str(ROOT / "eval" / "questions.jsonl"))
    s.add_argument("--agent", action="store_true", help="also run end-to-end agent eval (API cost)")
    s.add_argument("--no-dense", action="store_true", help="keyword search only, no embeddings")
    s.add_argument("--no-rerank", action="store_true", help="skip the cross-encoder rerank (faster, less precise)")
    s.set_defaults(func=cmd_eval)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
