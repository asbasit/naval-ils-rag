"""Maintenance-planning agent: Claude + retrieval tools + citation checking.

The model decides what to search for (often several searches: policy first,
then practice, then a specific standard), reads passages, and answers with
inline chunk-id citations. After it finishes, every citation is checked
against the passages the tools actually returned in this session. A citation
to anything else is flagged as unverified rather than silently trusted.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .chunk import Chunk
from .index import HybridIndex

DEFAULT_MODEL = os.environ.get("ILSRAG_MODEL", "claude-sonnet-5-5")

SYSTEM_PROMPT = """\
You are a maintenance-planning analyst for naval in-service support (ISS). You \
answer questions from planners, LCMMs and engineering staff using ONLY the \
passages returned by your tools from a corpus of public RCN/DND, USN, NATO and \
ASD documents.

Method:
1. Search before answering. Use several focused searches when a question has \
parts (e.g. "who is accountable" and "what the process is"). Use the exact \
document identifiers you see (DAOD numbers, MIL-STD numbers) as search terms \
when following a reference.
2. Read neighbouring passages with read_passage when a hit is cut off mid-list \
or mid-definition.
3. Answer, citing the chunk id in square brackets right after each claim it \
supports, e.g. "...twelve ILS elements [daod-3007-0#0007]." Several ids may \
share a bracket: [id1; id2]. Every factual sentence needs at least one citation.

Rules:
- Provenance matters. Each passage is tagged with its issuer. Never present a \
USN, NATO or ASD practice as RCN/DND policy. When you use a non-Canadian source \
to answer a Canadian question, say so in the sentence ("USN practice under \
MIL-STD-3034A is...").
- If the corpus does not cover something, say what is missing. Don't fill gaps \
from general knowledge; a planner may act on your answer.
- Prefer the most authoritative passage: policy (DAOD) over evaluations, \
evaluations over fact sheets, standards over commentary.
- Quote sparingly and only short phrases; paraphrase otherwise.
- Lead with the direct answer, then the supporting detail. No preamble.
"""

TOOLS = [
    {
        "name": "search_corpus",
        "description": (
            "Hybrid keyword + semantic search over the naval maintenance corpus. "
            "Returns passages with chunk_id, document title, issuer, page/section. "
            "Acronyms (EDWP, RCM, CBM+, ISSC, FMF, PMI...) are expanded automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for."},
                "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 6},
                "issuers": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["DND/CAF", "USN", "NATO", "ASD"]},
                    "description": "Optional filter, e.g. [\"DND/CAF\"] for Canadian policy only.",
                },
                "doc_ids": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Optional: restrict to specific document ids from list_documents.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_passage",
        "description": "Return a passage plus its neighbours (previous/next chunk) for fuller context.",
        "input_schema": {
            "type": "object",
            "properties": {
                "chunk_id": {"type": "string"},
                "radius": {"type": "integer", "minimum": 0, "maximum": 2, "default": 1},
            },
            "required": ["chunk_id"],
        },
    },
    {
        "name": "list_documents",
        "description": "List the documents in the corpus with id, title, issuer and kind.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

CITE_BRACKET = re.compile(r"\[([a-z0-9][a-z0-9\-]*#\d{4}(?:\s*[;,]\s*[a-z0-9][a-z0-9\-]*#\d{4})*)\]")


@dataclass
class Citation:
    number: int
    chunk_id: str
    verified: bool
    chunk: Chunk | None


@dataclass
class Answer:
    question: str
    text: str                      # answer with [n] markers
    raw_text: str                  # answer as the model wrote it
    citations: list[Citation]
    retrieved: list[str]           # every chunk id the tools returned
    tool_calls: list[dict] = field(default_factory=list)
    uncited_sentences: list[str] = field(default_factory=list)

    @property
    def unverified(self) -> list[Citation]:
        return [c for c in self.citations if not c.verified]

    def render(self) -> str:
        lines = [self.text, "", "Sources"]
        for c in self.citations:
            if c.chunk is None:
                lines.append(f"  [{c.number}] {c.chunk_id}  ** UNVERIFIED: not returned by any search **")
                continue
            ch = c.chunk
            where = f"p.{ch.page}" if ch.page else (f"§ {ch.heading}" if ch.heading else "")
            flag = "" if c.verified else "  ** UNVERIFIED **"
            lines.append(f"  [{c.number}] {ch.title} ({ch.issuer}) {where}{flag}")
            lines.append(f"       {ch.url}")
        if self.uncited_sentences:
            lines.append("")
            lines.append(f"Note: {len(self.uncited_sentences)} sentence(s) carry no citation.")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.text,
            "citations": [
                {"n": c.number, "chunk_id": c.chunk_id, "verified": c.verified,
                 "title": c.chunk.title if c.chunk else None,
                 "page": c.chunk.page if c.chunk else None,
                 "url": c.chunk.url if c.chunk else None}
                for c in self.citations
            ],
            "retrieved": self.retrieved,
            "tool_calls": self.tool_calls,
            "uncited_sentences": self.uncited_sentences,
        }


def _format_passage(c: Chunk) -> dict:
    return {
        "chunk_id": c.chunk_id,
        "document": c.title,
        "issuer": c.issuer,
        "kind": c.kind,
        "location": f"page {c.page}" if c.page else (c.heading or "web page"),
        "section": c.heading,
        "text": c.text,
    }


class ToolBox:
    """Executes tool calls and remembers every chunk it has shown the model."""

    def __init__(self, index: HybridIndex):
        self.index = index
        self.seen: dict[str, Chunk] = {}

    def run(self, name: str, args: dict) -> str:
        if name == "search_corpus":
            hits = self.index.search(
                args["query"], k=int(args.get("k", 6)),
                issuers=args.get("issuers"), doc_ids=args.get("doc_ids"),
            )
            for h in hits:
                self.seen[h.chunk.chunk_id] = h.chunk
            if not hits:
                return json.dumps({"results": [], "note": "No matching passages."})
            return json.dumps({"results": [_format_passage(h.chunk) for h in hits]}, ensure_ascii=False)
        if name == "read_passage":
            cid = args["chunk_id"]
            if cid not in self.index.by_id:
                return json.dumps({"error": f"unknown chunk_id {cid}"})
            chunks = self.index.neighbours(cid, int(args.get("radius", 1)))
            for c in chunks:
                self.seen[c.chunk_id] = c
            return json.dumps({"passages": [_format_passage(c) for c in chunks]}, ensure_ascii=False)
        if name == "list_documents":
            docs = {}
            for c in self.index.chunks:
                docs.setdefault(c.doc_id, {"id": c.doc_id, "title": c.title,
                                           "issuer": c.issuer, "kind": c.kind, "chunks": 0})
                docs[c.doc_id]["chunks"] += 1
            return json.dumps({"documents": list(docs.values())})
        return json.dumps({"error": f"unknown tool {name}"})


def resolve_citations(raw: str, seen: dict[str, Chunk], index: HybridIndex):
    """Replace [chunk-id] markers with [n] and check each against what the
    tools returned. Returns (text, citations, uncited_sentences)."""
    numbers: dict[str, int] = {}
    citations: list[Citation] = []

    def sub(match: re.Match) -> str:
        out = []
        for cid in re.split(r"\s*[;,]\s*", match.group(1)):
            if cid not in numbers:
                numbers[cid] = len(numbers) + 1
                chunk = seen.get(cid) or index.by_id.get(cid)
                citations.append(Citation(numbers[cid], cid, cid in seen, chunk))
            out.append(str(numbers[cid]))
        return "[" + ", ".join(out) + "]"

    text = CITE_BRACKET.sub(sub, raw)

    uncited = []
    for para in raw.split("\n"):
        stripped = para.strip().lstrip("-*• ").strip()
        if not stripped or stripped.startswith("#") or stripped.endswith(":"):
            continue
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", stripped):
            if len(sent.split()) >= 8 and not CITE_BRACKET.search(sent):
                uncited.append(sent)
    return text, citations, uncited


class MaintenanceAgent:
    def __init__(self, index: HybridIndex, client=None, model: str = DEFAULT_MODEL,
                 max_turns: int = 8, max_tokens: int = 2000):
        if client is None:
            import anthropic
            client = anthropic.Anthropic()
        self.client = client
        self.index = index
        self.model = model
        self.max_turns = max_turns
        self.max_tokens = max_tokens

    def ask(self, question: str, verbose: bool = False) -> Answer:
        tools = ToolBox(self.index)
        messages: list[dict] = [{"role": "user", "content": question}]
        tool_log: list[dict] = []
        final_text = ""

        for turn in range(self.max_turns):
            last_turn = turn == self.max_turns - 1
            resp = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                # On the final turn, stop searching and make it answer.
                tool_choice={"type": "none"} if last_turn else {"type": "auto"},
                messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})
            tool_uses = [b for b in resp.content if getattr(b, "type", None) == "tool_use"]
            if not tool_uses:
                final_text = "".join(getattr(b, "text", "") for b in resp.content
                                     if getattr(b, "type", None) == "text").strip()
                break
            results = []
            for tu in tool_uses:
                if verbose:
                    print(f"  -> {tu.name}({json.dumps(tu.input)})")
                tool_log.append({"tool": tu.name, "input": tu.input})
                results.append({"type": "tool_result", "tool_use_id": tu.id,
                                "content": tools.run(tu.name, tu.input)})
            messages.append({"role": "user", "content": results})

        text, citations, uncited = resolve_citations(final_text, tools.seen, self.index)
        return Answer(question, text, final_text, citations, list(tools.seen), tool_log, uncited)


def extractive_answer(index: HybridIndex, question: str, k: int = 5) -> str:
    """No-LLM fallback: show the top passages with their citations. Useful for
    demos without an API key and for eyeballing retrieval quality."""
    hits = index.search(question, k=k)
    if not hits:
        return "No matching passages."
    lines = [f"Top {len(hits)} passages for: {question}", ""]
    for n, h in enumerate(hits, 1):
        c = h.chunk
        where = f"p.{c.page}" if c.page else (c.heading or "")
        snippet = c.text if len(c.text) < 600 else c.text[:600].rsplit(" ", 1)[0] + " …"
        ranks = f"bm25 #{h.bm25_rank + 1 if h.bm25_rank is not None else '-'}, " \
                f"dense #{h.dense_rank + 1 if h.dense_rank is not None else '-'}"
        lines += [f"[{n}] {c.title} ({c.issuer}) {where}   ({ranks})",
                  f"    {snippet}", f"    {c.url}", ""]
    return "\n".join(lines)
