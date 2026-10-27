# naval-ils-rag

[![tests](https://github.com/asbasit/naval-ils-rag/actions/workflows/tests.yml/badge.svg)](https://github.com/asbasit/naval-ils-rag/actions/workflows/tests.yml)

A retrieval stack over public naval maintenance and in-service support (ISS) documents, with a Claude agent that answers maintenance-planning questions and cites the page or section behind each claim. Citations are checked after the answer is written: any chunk id the model cites that no search actually returned is flagged `UNVERIFIED`, and `ask` exits non-zero. The same search tools are served over MCP, so Claude Desktop or Claude Code can use the corpus directly.

The corpus mixes Canadian policy (DAOD 3000-series, the CF Preventive Maintenance Instruction spec, ADM(RS) naval evaluations, the Victoria-class fleet status sheet) with USN practice (MIL-STD-3034A, the ship RCM process), the ASD S4000P Issue 3.0 preventive maintenance spec, and NATO logistics material: 13 documents, 2,458 passages. Every passage carries its issuer, and the agent is instructed never to pass off USN or NATO practice as RCN policy. That distinction is the one a real LCMM would care about.

Built by Abdul Salam Basit, retired naval Commander (submarines) and electrical engineer, as a working example of retrieval and agent tooling applied to in-service support.

### Status

| Part | State |
|---|---|
| Fetch, parse, chunk, hybrid index, reranker | Done; run on the real corpus |
| Retrieval evaluation (32 questions, 4 setups compared) | Done; results below and in `eval/results/` |
| MCP server | Done; tested over a real stdio client session |
| Citing agent + citation verification | Built and tested against a scripted client; **live API run pending** |
| End-to-end agent eval (`eval --agent`) | Built; **pending API run** |

### What a search returns

```
$ python -m ilsrag search "Why can only one Victoria-class submarine be in deep maintenance at a time?" -k 2

[1] RCN Fact Sheet FS 12.001, Royal Canadian Navy Submarines: Fleet Status (2012) (DND/CAF) HMCS Corner Brook   (bm25 #1, dense #5)
    … The actual repairs to the submarine will occur during the scheduled EDWP at Victoria Shipyards Co. Ltd,
    which is to commence in January 2013. Due to contractual and program management reasons relating to DND's
    In-Service Support Contract, only one submarine at a time is to be in deep maintenance. Corner Brook will
    therefore be maintained at the minimum level necessary, as she awaits her scheduled EDWP …
    https://www.canada.ca/en/news/archive/2012/02/royal-canadian-navy-submarines-fleet-status.html#wb-cont

[2] RCN Fact Sheet FS 12.001 … (DND/CAF) Submarine Fleet Status   (bm25 #2, dense #2)
    … An EDWP is a deep maintenance period that provides the submarines' 200-plus systems with the repairs,
    maintenance, and upgrades needed to enable six years of effective operation. …
```

Without the reranker the general fleet-status paragraph comes first; with it, the passage that actually gives the reason does.

## Quick start

```powershell
py -3.12 -m venv .venv            # macOS/Linux: python3 -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

python -m ilsrag fetch          # downloads the 11 auto-fetch documents (uses curl)
python -m ilsrag docs           # shows what's present / what needs manual download
python -m ilsrag ingest         # parse, chunk, embed (first run downloads a 130 MB embedding model)

python -m ilsrag search "EDWP Victoria-class interval"        # retrieval only, no API key needed
python -m ilsrag ask "Why can only one Victoria-class boat be in deep maintenance at a time?" --no-llm

set ANTHROPIC_API_KEY=sk-ant-...
python -m ilsrag ask "Who is accountable for maintenance of RCN systems, and how does USN practice for reviewing maintenance effectiveness compare?" -v
python -m ilsrag eval --questions eval/questions_hard.jsonl            # retrieval metrics
python -m ilsrag eval --questions eval/questions_hard.jsonl --agent    # end to end (API cost)
```

The first search also downloads an 80 MB reranking model. Searches take ~3 s each with reranking on; add `--no-rerank` for instant, less precise results.

Python 3.10+. Model defaults to `claude-sonnet-5-5`; override with `--model` or `ILSRAG_MODEL`.

### Manual downloads

`fetch` gets the 11 DND/CAF and NATO documents itself. The two standards can't be fetched by script. Download them in a browser, put them in `data/raw/` with the file name shown, and re-run `ingest`:

| File | Where | Why manual |
|---|---|---|
| `mil-std-3034a.pdf` | EverySpec / ASSIST | download page, no stable PDF link |
| `s4000p.pdf` | s-series.org/s4000p/downloads | free, but you accept ASD terms first (Issue 3.0, 2025) |
| `nato-alp-10.pdf` | optional | not public; only if you hold a releasable copy |

`ingest` skips anything missing and the eval skips questions whose source isn't present, so the stack works with whatever subset you have.

### Use it from Claude Desktop or Claude Code (MCP)

The same three tools the agent uses are exposed as an MCP server (`ilsrag/mcp_server.py`), read-only:

```
claude mcp add naval-ils -e ILSRAG_HOME=<path to this folder> -- <path to venv python> -m ilsrag.mcp_server
```

Then ask Claude a maintenance-planning question and it will call `search_corpus` / `read_passage` itself. The server's instructions carry the same provenance and citation rules as the built-in agent.

## How it works

```
manifest.toml ──fetch──> data/raw/*.pdf|html ──parse──> blocks (text, page, heading, anchor)
                                                  │
                                              chunk (≈180 words, never across a page or heading)
                                                  │
                                 ┌────────────────┴────────────────┐
                              BM25 (identifier-aware)      bge-small embeddings
                                 └────────── RRF fusion ───────────┘
                                                  │
                              cross-encoder rerank of top 30 + per-doc cap
                                                  │
                     agent: search_corpus / read_passage / list_documents (Claude tool use)
                     (same tools also served over MCP: ilsrag/mcp_server.py)
                                                  │
                         answer with [chunk-id] → verified against retrieved set → [n] + Sources
```

Choices worth knowing about:

- **Chunks never cross a PDF page.** It costs a little retrieval quality and buys citations that point at exactly one page (`…pdf#page=14`). HTML chunks carry the nearest heading anchor instead.
- **Running headers and security markings are stripped.** DND evaluation PDFs repeat "Reviewed by ADM(RS)… Information UNCLASSIFIED" on every page; left in, that line dominates similarity scores.
- **The tokenizer keeps identifiers whole** (`mil-std-3034a`, `d-01-100-204`, `cbm+`) and also indexes their parts, so "3034A" and "MIL-STD-3034A" both hit.
- **Acronym expansion** (`ilsrag/glossary.py`) bridges planners' shorthand and document prose: a question about an EDWP finds text that only says "extended docking work period". Add your own terms there.
- **Hybrid with reciprocal rank fusion, then a reranker**: BM25 catches document numbers, embeddings add paraphrase candidates, RRF merges them without calibrating scores, and a cross-encoder makes the final call. See Evaluation for why the reranker isn't optional in practice on this corpus.
- **Forced answer on the last turn** (`tool_choice: none`) so the agent can't loop on searches forever.

## Evaluation

Two question sets, each question tagged with the document(s) a correct answer must draw on. Scoring is at document level, so it stays valid when chunking changes.

- `eval/questions.jsonl`: 16 direct questions that use the documents' own vocabulary (4 of them need the two manually downloaded standards).
- `eval/questions_hard.jsonl`: 12 paraphrased questions asked in a planner's words ("what happens to a sub that needs repairs while another boat is in the dock?"), 4 cross-document questions, and 4 questions the corpus **cannot** answer, such as the MTBF of the LM2500 or whether Chicoutimi is operational today, when the corpus holds a 2012 fact sheet. The unanswerable ones are skipped by retrieval scoring; the agent eval checks that it says the corpus doesn't cover them.

`python -m ilsrag eval --questions eval/questions_hard.jsonl` reports recall@k, MRR, per-type breakdowns and, for cross-document questions, whether *all* the needed documents came back. Results are saved under `eval/results/`. `--agent` adds an end-to-end run (API cost): does the answer cite an expected document, are all citations verified, does it decline on unanswerable questions.

### Results (Oct 2026)

First run, 11 DND/CAF + NATO documents, 521 passages:

| Retrieval setup | Direct R@5 | Hard R@1 | Hard R@5 | Hard MRR | Paraphrase R@5 | Cross-doc: all docs found |
|---|---|---|---|---|---|---|
| Keyword (BM25) only | 1.00 | 0.57 | 0.79 | 0.68 | 0.73 | 3/3 |
| Hybrid (BM25 + bge-small) | 0.92 | 0.64 | 0.71 | 0.68 | 0.64 | 2/3 |
| BM25 + reranker | 1.00 | 0.71 | 0.79 | 0.74 | 0.73 | 3/3 |
| **Hybrid + reranker (default)** | **1.00** | **0.71** | **0.86** | **0.76** | **0.82** | **3/3** |

**After adding MIL-STD-3034A and S4000P Issue 3.0** (13 documents, 2,458 passages; S4000P alone is 1,616 of them), default setup:

| Corpus | Direct R@1 | Direct R@5 | Hard R@1 | Hard R@5 | Hard MRR | Paraphrase R@5 | Cross-doc: all docs found |
|---|---|---|---|---|---|---|---|
| 11 docs, 521 passages | 0.83 | 1.00 | 0.71 | 0.86 | 0.76 | 0.82 | 3/3 |
| 13 docs, 2,458 passages | 0.88 | 1.00 | 0.69 | 0.81 | 0.73 | 0.75 | 4/4 |

The direct set now covers USN RCM and S4000P questions and gets all 16. The hard set lost a little: one Canadian-policy paraphrase (h02, "what four things are weighed equally when deciding how kit is supported") now loses to S4000P passages that discuss the same idea in general terms. That is the crowding effect again, from a large foreign standard this time. The agent's `issuers=["DND/CAF"]` filter exists for exactly this; whether it uses it is what `eval --agent` will show.

What this says:

- **Embeddings alone made things worse here.** Three long evaluation reports make up ~400 of the 521 passages and talk about RCN maintenance in general on every page; in vector space they crowd out the short, precise DAODs. Hybrid search lost to plain BM25 on paraphrased questions.
- **A cross-encoder reranker fixes that.** Fusing BM25 and embeddings for candidates, then rescoring the top 30 with a small cross-encoder (`ms-marco-MiniLM-L-6-v2`, 80 MB), gave the best numbers on every column. Cost: ~3 s per search on a MacBook Air M1 CPU versus ~0.01 s without. `--no-rerank` turns it off.
- **Two questions still miss** (h04 "who investigates a serious equipment failure", h06 "which departments outside Defence help design support"). In both, the answer is one bullet inside a long DAOD requirements list. The agent's multi-search loop and `issuers=["DND/CAF"]` filter are meant to recover these; `eval --agent` measures whether they do.

Caveats, stated plainly: 32 answerable questions is small, so one question moves paraphrase recall by about 0.08. The configurations were compared on the same questions used to report them, so there is no held-out set yet. Treat the table as direction, not proof. The next step is a held-out set written by someone who has done the maintenance planning, which is the part of this demo nobody else can write.

## Roadmap

Next, in order:

1. **Live agent run and `eval --agent`** with an API key: citation verified-rate, cites-expected-document rate, and decline rate on the four unanswerable questions. This also shows whether the agent's issuer filter recovers h02, h04 and h06.
2. **Held-out questions** written from maintenance-planning experience without looking at the corpus, so the reported numbers aren't measured on the same questions used to choose the setup.
3. **Engineering-change impact query:** given a described change to a system, list the ILS documents and DAOD requirements it touches (configuration management, materiel assurance, maintenance instructions).
4. **Split the bilingual PMI spec** into English and French passages.
5. **Claude Code demo script** using the MCP server, for live walkthroughs.

## What the real documents broke

The first run against the real corpus found problems the synthetic tests didn't. Each now has a regression test:

- **canada.ca's older news releases put the article body inside `<aside>`.** The parser was dropping `<aside>` as sidebar clutter, so the Victoria-class fleet status sheet indexed as one empty chunk. It now yields 11.
- **`<p>` nested in `<dd>`, and text in `<div>`s separated by `<br>`,** gave duplicated or missing text. The HTML parser now reads only the innermost text blocks.
- **Definition terms are short bold paragraphs** ("**available** (disponible)") and fell under the minimum length, which left definitions without their term.
- **The 2019 Ready Naval Forces evaluation PDF is AES-encrypted** (no password, but `pypdf` needs `cryptography` to open it).
- **PDF table rows looked like headings** ("FY 2013/14 FY 2014/15", "90% 75% 100%"), and title-case headings like "Executive Summary" were missed.
- **Python's `urllib` stalls on canada.ca** at the TLS read while `curl` gets the same page in half a second, so `fetch` uses `curl` first.
- **NAVSEA's old instruction links now redirect to a different document.** NAVSEAINST 4790.26A, 4790.27B and 4790.30 have been withdrawn; their URLs serve COMNAVAIRFORINST 4790.2E, the 1,930-page Naval Aviation Maintenance Program. Saved under the old name, an aviation manual would have been indexed and cited as NAVSEA ship policy. Caught by reading the first page before ingesting; the three entries are out of the manifest and the file is kept aside in `data/excluded/`. Lesson: check what a download *is*, not just that it's a PDF.
- **nato.int removed the 1997 Logistics Handbook pages** in its redesign; the manifest now points at the Internet Archive copy.

Still open: the CF Preventive Maintenance Instruction spec is printed English and French side by side, so its chunks mix both languages.

## Tests

```
pip install -r requirements-dev.txt
pytest -q
```

Tests run in CI on every push (`.github/workflows/tests.yml`) against a synthetic fixture corpus (an invented "Kestrel-class"), so they need no network and can't be mistaken for real policy. They cover page-accurate PDF parsing, marking/boilerplate removal, HTML anchors, acronym bridging, issuer filters, index save/load, citation verification (a fabricated id must be flagged), the tool-use loop with a scripted client, reranking order, the document identity check, the resumable embedding cache, and the MCP server (tools listed and called over the SDK).

## Known limits

- Scanned PDFs (no text layer) come out empty; `ingest` reports `EMPTY`. Run them through OCR (e.g. `ocrmypdf`) first.
- navsea.navy.mil refuses scripted downloads and has withdrawn the 4790-series ship maintenance instructions from public view, so the corpus relies on MIL-STD-3034A for USN ship RCM.
- Heading detection in PDFs is heuristic (numbered or upper-case lines). Section labels in citations are a convenience; the page number is the reliable locator.
- Corpus documents are public but each keeps its own copyright/terms (Crown copyright for DND; ASD terms for S4000P). The repo ships the manifest and code, not the documents; `data/` is git-ignored.

## Layout

```
corpus/manifest.toml   document list (id, issuer, url, fetch mode)
ilsrag/corpus.py       manifest + downloader with sha256 ledger
ilsrag/parse.py        PDF/HTML → blocks with page/heading/anchor
ilsrag/chunk.py        blocks → chunks
ilsrag/index.py        BM25, embeddings, hybrid search
ilsrag/glossary.py     naval/ILS acronym expansion
ilsrag/agent.py        Claude tool loop, citation verification, extractive fallback
ilsrag/mcp_server.py   the same tools as a read-only MCP server
ilsrag/evaluate.py     retrieval and end-to-end metrics
ilsrag/cli.py          command line
eval/questions*.jsonl  direct and hard (paraphrase / cross-doc / unanswerable) question sets
eval/results/          eval runs on the real corpus (11-doc and 13-doc)
tests/                 fixture corpus + tests
```

## Licence

Code: MIT (see `LICENSE`). The documents in the corpus are not part of this repository and remain under their owners' terms.
