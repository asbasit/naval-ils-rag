# naval-ils-rag

[![tests](https://github.com/asbasit/naval-ils-rag/actions/workflows/tests.yml/badge.svg)](https://github.com/asbasit/naval-ils-rag/actions/workflows/tests.yml)

A retrieval stack over public naval maintenance and in-service support (ISS) documents, with a Claude agent that answers maintenance-planning questions and cites the page or section behind each claim. Citations are checked after the answer is written: any chunk id the model cites that no search actually returned is flagged `UNVERIFIED`, and `ask` exits non-zero. The same search tools are served over MCP, so Claude Desktop or Claude Code can use the corpus directly.

The corpus mixes Canadian policy (DAOD 3000-series, the CF Preventive Maintenance Instruction spec, ADM(RS) naval evaluations, the Victoria-class fleet status sheet) with USN practice (MIL-STD-3034A, the ship RCM process), the ASD S4000P Issue 3.0 preventive maintenance spec, and NATO logistics material: 13 documents, 2,458 passages. Every passage carries its issuer, and the agent is instructed never to pass off USN or NATO practice as RCN policy. That distinction is the one a real LCMM would care about.

Built by Abdul Salam Basit, retired naval Commander (submarines) and electrical engineer, as a working example of retrieval and agent tooling applied to in-service support.

### Status

| Part | State |
|---|---|
| Fetch, parse, chunk, hybrid index, reranker | Done; run on the real corpus |
| Retrieval evaluation (41 questions, 4 setups compared, passage-level check) | Done; results below and in `eval/results/` |
| MCP server | Done; tested over a real stdio client session |
| Engineering-change impact assessment (`ec-impact`) | Done; 17 rules, all 24 cited passages verified in the real corpus |
| LSA workbook (`lsa`): RAM/RBD, sparing, LORA, FMECA, parts count | Done; checked against hand-worked values |
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

## Engineering-change impact assessment

The day-to-day ILS question on an in-service support contract is: *this engineering change is coming, which ILS products does it touch?* `ec-impact` answers it from a short change description:

```
$ python -m ilsrag ec-impact examples/ec/ec-demo-001-radar-psu.toml --out report.md
EC-DEMO-001: 13 affected, 0 to confirm, 4 not affected, 0 basis not found -> report.md
```

You describe the change as twelve yes / no / unknown characteristics (new part number? form-fit-function change? software? new tools? hazardous material? obsolescence-driven? ...). The rules in [`corpus/ec_rules.toml`](corpus/ec_rules.toml) map them to 17 ILS products across the twelve DND ILS elements of DAOD 3007-0: configuration records, LSA records (FMECA, maintenance task analysis, LORA), RAM predictions and RBDs, the maintenance plan and PM schedule, maintenance-system task data, spares and provisioning, obsolescence, technical data, safety precautions, training, personnel, support and test equipment, software, facilities, PHS&T, materiel assurance, and support-solution V&V.

The report gives, for each product, why it is affected, what to do, and the passage that requires it, cited to the page or section. Two worked reports on fictional changes are in [`examples/ec/reports/`](examples/ec/reports/): [an obsolescence-driven radar power supply replacement](examples/ec/reports/ec-demo-001-radar-psu.md) and [a console software update](examples/ec/reports/ec-demo-002-console-software.md).

Design choices:

- **Unknown is not "no".** A characteristic the change request leaves open puts the products it would affect on a *confirm with the EC team* list, and the report lists every open question with the products whose scope depends on it. In the radar example, whether the new unit's capacitor bank needs special handling is still open, and it bears on materiel assurance, safety precautions and PHS&T.
- **Citations by exact phrase, not search.** Each rule names a document and a phrase the passage must contain. A planning record has to give the same answer every run, and if a passage disappears (document not downloaded, reworded in a new issue) the report says *basis not found* rather than citing something close. `ec-impact --check-rules` verifies all 24 phrases against the index.
- **Provenance stays visible.** Where a rule leans on MIL-STD-3034A (USN) or NATO material, the report says that source describes that organization's practice, not RCN policy.
- **The rules are meant to be edited.** Triggers and actions are the judgement an experienced ILS practitioner owns; the file is plain TOML.
- Also exposed as the MCP tool `ec_impact`, so Claude can run an assessment from a change described in conversation.

## LSA workbook

The EC report says *which* products to update; the workbook does the numbers for the analytical ones. One case file, one report, before and after the change:

```
$ python -m ilsrag lsa examples/lsa/radar-psu.toml --out report.md
```

The [worked example](examples/lsa/reports/radar-psu.md) follows the same fictional radar power-supply replacement as EC-DEMO-001 (new unit, MTBF 4,000 h to 9,000 h, two redundant transceiver channels, 90-day patrol, six ships):

| Analysis | Method (in `ilsrag/lsa/`) | What the example shows |
|---|---|---|
| RAM and RBD | Inherent, achieved, operational availability; series, parallel and k-of-n block diagrams | System availability barely moves (99.9166% to 99.9167%) because the supply sits in a redundant channel; patrol reliability without repair rises from 43% to 51% |
| Operational availability | Ao = MTBM / (MTBM + MDT), with logistic delay | Same supply: 99.94% with a spare onboard, 94.6% if one takes 21 days to arrive |
| Sparing | Poisson demand over the patrol, smallest stock meeting the protection target | 95% protection needs 3 spares per ship before the change and 2 after |
| LORA | Life-cycle cost per option: repair or replace events, pipeline stock, fixed support costs | Repair at the fleet maintenance facility is cheapest over 20 years; onboard repair is second and carries an unresolved capacitor-hazard constraint from the EC report |
| FMECA | MIL-STD-1629A-style criticality, Cm = beta x alpha x lambda x t; criticality matrix | Overvoltage ranks first: lower probability than "no output" but critical severity |
| Parts count | MIL-HDBK-217 method, sum of N x lambda_g x pi_Q | Predicts 9,025 h against the supplier's 9,000 h |

All figures in the example are invented and labelled so. The parts count module ships no handbook tables; the example's failure rates are marked illustrative, and real use takes lambda_g and pi_Q from MIL-HDBK-217 or an approved source. Each formula is documented at the top of its module and checked in `tests/test_lsa.py` against values worked by hand.

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

- `eval/questions_ops.jsonl`: 9 operational planning questions (task intervals, configuration change, task-card resources, safety and tag-out, in-service optimisation, keeping the maintenance system in step with instruction changes, spares for older ships, grouping tasks, test-equipment calibration) plus 3 ship-specific questions no public corpus can answer ("which PMS tasks are overdue on HMCS Victoria this month?"). They were shortlisted from a 25-item list of maintenance-system acceptance tests: the 11 that test system behaviour (work-order closeout, audit trails, stock levels, deferral workflows) were dropped because no document covers them. These were written after reading the corpus, so they are not blind.

Questions can also list `evidence` phrases. Then the eval checks the *passage*, not just the document: the right document can rank first while its top passage is the wrong one, and document-level scoring hides that.

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

**Operational set** (13 documents, default setup): document recall@1 1.00, passage evidence@1 0.78, evidence@5 0.89 (9 questions). The gap is the point: for "when should separate maintenance tasks be grouped?" MIL-STD-3034A ranks first, but its top passage is a general RCM decision question rather than the "related maintenance" rule that answers it.

What this says:

- **Embeddings alone made things worse here.** Three long evaluation reports make up ~400 of the 521 passages and talk about RCN maintenance in general on every page; in vector space they crowd out the short, precise DAODs. Hybrid search lost to plain BM25 on paraphrased questions.
- **A cross-encoder reranker fixes that.** Fusing BM25 and embeddings for candidates, then rescoring the top 30 with a small cross-encoder (`ms-marco-MiniLM-L-6-v2`, 80 MB), gave the best numbers on every column. Cost: ~3 s per search on a MacBook Air M1 CPU versus ~0.01 s without. `--no-rerank` turns it off.
- **Two questions still miss** (h04 "who investigates a serious equipment failure", h06 "which departments outside Defence help design support"). In both, the answer is one bullet inside a long DAOD requirements list. The agent's multi-search loop and `issuers=["DND/CAF"]` filter are meant to recover these; `eval --agent` measures whether they do.

Caveats, stated plainly: 32 answerable questions is small, so one question moves paraphrase recall by about 0.08. The configurations were compared on the same questions used to report them, so there is no held-out set yet. Treat the table as direction, not proof. The next step is a held-out set written by someone who has done the maintenance planning, which is the part of this demo nobody else can write.

## Roadmap

Next, in order:

1. **Live agent run and `eval --agent`** with an API key: citation verified-rate, cites-expected-document rate, and decline rate on the four unanswerable questions. This also shows whether the agent's issuer filter recovers h02, h04 and h06.
2. **Held-out questions** written from maintenance-planning experience without looking at the corpus, so the reported numbers aren't measured on the same questions used to choose the setup.
3. **Maintenance task analysis** in the workbook: task times, skills and spares per task, rolled up into man-hours per patrol.
4. **Add ASD S3000L** (logistic support analysis) and public AJISS tender documents to the corpus.
5. **Split the bilingual PMI spec** into English and French passages.
6. **Claude Code demo script** using the MCP server, for live walkthroughs.

## What the real documents broke

The first run against the real corpus found problems the synthetic tests didn't. Each now has a regression test:

- **canada.ca's older news releases put the article body inside `<aside>`.** The parser was dropping `<aside>` as sidebar clutter, so the Victoria-class fleet status sheet indexed as one empty chunk. It now yields 11.
- **`<p>` nested in `<dd>`, and text in `<div>`s separated by `<br>`,** gave duplicated or missing text. The HTML parser now reads only the innermost text blocks.
- **Definition terms are short bold paragraphs** ("**available** (disponible)") and fell under the minimum length, which left definitions without their term.
- **The 2019 Ready Naval Forces evaluation PDF is AES-encrypted** (no password, but `pypdf` needs `cryptography` to open it).
- **Short list items were dropped.** DAOD 3007-0 lists the twelve ILS elements as `<li>` items like "supply support;", under the length filter meant for page clutter; only five of twelve survived. Found while writing the EC rules, which cite that list.
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
ilsrag/mcp_server.py   the same tools as a read-only MCP server, plus ec_impact
ilsrag/ec_impact.py    engineering-change impact assessment
corpus/ec_rules.toml   EC rules: change characteristics -> ILS products, with cited basis
examples/ec/           fictional example ECs and their generated reports
ilsrag/lsa/            RAM/RBD, sparing, LORA, FMECA, parts count, and the workbook that runs them
examples/lsa/          fictional LSA case and its generated report
ilsrag/evaluate.py     retrieval and end-to-end metrics
ilsrag/cli.py          command line
eval/questions*.jsonl  direct, hard (paraphrase / cross-doc / unanswerable) and operational question sets
eval/results/          eval runs on the real corpus (11-doc and 13-doc)
tests/                 fixture corpus + tests
```

## Licence

Code: MIT (see `LICENSE`). The documents in the corpus are not part of this repository and remain under their owners' terms.
