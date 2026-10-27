"""Engineering-change (EC) impact assessment.

Given a described engineering change, list the ILS products that need
updating, why, what to do, and the policy or standard passage behind each
recommendation.

The mapping from change characteristics to ILS products lives in
corpus/ec_rules.toml so an ILS practitioner can own and edit it. Citations are
resolved by exact phrase match against the indexed corpus, not by search
ranking: a planning record has to give the same answer every run, and if a
cited passage is missing (document not downloaded, or reworded in a new issue)
the report says "basis not found" rather than citing something nearby.

Change characteristics take three values: true, false, or "unknown". Unknown
answers don't silently drop a product; they put it on a "confirm with the EC
team" list, which is how a real impact assessment handles an incomplete
change request.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

from .chunk import Chunk

UNKNOWN = "unknown"


@dataclass
class Basis:
    doc: str
    evidence: str


@dataclass
class Rule:
    id: str
    product: str
    ils_element: str
    triggers: list[str]
    action: str
    basis: list[Basis]


@dataclass
class ChangeRequest:
    id: str
    title: str
    platform: str
    system: str
    description: str
    changes: dict[str, bool | str]


@dataclass
class Citation:
    doc: str
    evidence: str
    chunk: Chunk | None

    @property
    def found(self) -> bool:
        return self.chunk is not None


@dataclass
class Finding:
    rule: Rule
    status: str                      # "affected" | "confirm" | "not affected"
    because: list[str]               # change characteristics that triggered it
    citations: list[Citation] = field(default_factory=list)


@dataclass
class Assessment:
    change: ChangeRequest
    findings: list[Finding]
    vocabulary: dict[str, str]

    def by_status(self, status: str) -> list[Finding]:
        return [f for f in self.findings if f.status == status]

    def open_questions(self) -> list[tuple[str, list[Finding]]]:
        """Each unknown characteristic and the products whose scope depends on it,
        including products already affected for another reason (an unknown
        hazardous-material answer still widens the PHS&T work)."""
        out = []
        for k, v in self.change.changes.items():
            if v == UNKNOWN:
                out.append((k, [f for f in self.findings if k in f.rule.triggers]))
        return out

    @property
    def missing_basis(self) -> list[Citation]:
        return [c for f in self.findings if f.status != "not affected" for c in f.citations if not c.found]


# --------------------------------------------------------------------- loading

def load_rules(path: Path) -> tuple[dict[str, str], list[Rule]]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    vocab = data.get("vocabulary", {})
    rules = []
    for r in data.get("rule", []):
        unknown = [t for t in r["triggers"] if t != "always" and t not in vocab]
        if unknown:
            raise ValueError(f"rule {r['id']}: triggers not in vocabulary: {unknown}")
        rules.append(Rule(
            id=r["id"], product=r["product"], ils_element=r.get("ils_element", ""),
            triggers=list(r["triggers"]), action=r["action"],
            basis=[Basis(**b) for b in r.get("basis", [])],
        ))
    return vocab, rules


def load_change(path: Path, vocab: dict[str, str]) -> ChangeRequest:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    changes = data.get("changes", {})
    bad = [k for k in changes if k not in vocab]
    if bad:
        raise ValueError(f"unknown change characteristics {bad}; expected some of {sorted(vocab)}")
    for k, v in changes.items():
        if v not in (True, False, UNKNOWN):
            raise ValueError(f"{k} must be true, false or \"unknown\", got {v!r}")
    # Anything the change request doesn't mention is unknown, not "no".
    full = {k: changes.get(k, UNKNOWN) for k in vocab}
    return ChangeRequest(
        id=data["id"], title=data["title"], platform=data.get("platform", ""),
        system=data.get("system", ""), description=data.get("description", "").strip(),
        changes=full,
    )


# ------------------------------------------------------------------ assessing

def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


class EvidenceIndex:
    """Exact-phrase lookup over indexed chunks, per document."""

    def __init__(self, chunks: list[Chunk]):
        self.by_doc: dict[str, list[Chunk]] = {}
        for c in chunks:
            self.by_doc.setdefault(c.doc_id, []).append(c)

    def find(self, doc: str, phrase: str) -> Chunk | None:
        # Chunks are scanned in document order, so a phrase repeated in the
        # overlap at the start of the next chunk resolves to where it first appears.
        p = _norm(phrase)
        for c in self.by_doc.get(doc, []):
            if p in _norm(c.text):
                return c
        return None


def assess(change: ChangeRequest, rules: list[Rule], vocab: dict[str, str],
           chunks: list[Chunk]) -> Assessment:
    ev = EvidenceIndex(chunks)
    findings = []
    for rule in rules:
        if "always" in rule.triggers:
            status, because = "affected", ["every engineering change"]
        else:
            yes = [t for t in rule.triggers if change.changes.get(t) is True]
            maybe = [t for t in rule.triggers if change.changes.get(t) == UNKNOWN]
            if yes:
                status, because = "affected", yes
            elif maybe:
                status, because = "confirm", maybe
            else:
                status, because = "not affected", []
        cites = [Citation(b.doc, b.evidence, ev.find(b.doc, b.evidence)) for b in rule.basis]
        findings.append(Finding(rule, status, because, cites))
    order = {"affected": 0, "confirm": 1, "not affected": 2}
    findings.sort(key=lambda f: order[f.status])
    return Assessment(change, findings, vocab)


# ------------------------------------------------------------------ rendering

def _snippet(chunk: Chunk, phrase: str, width: int = 220) -> str:
    text = re.sub(r"\s+", " ", chunk.text)
    i = text.lower().find(_norm(phrase))
    if i == -1:
        return text[:width]
    start = max(0, i - width // 3)
    out = text[start:start + width].strip()
    return ("…" if start > 0 else "") + out + ("…" if start + width < len(text) else "")


def _where(c: Chunk) -> str:
    return f"p.{c.page}" if c.page else (f"§ {c.heading}" if c.heading else "")


def render_markdown(a: Assessment) -> str:
    ch = a.change
    refs: dict[tuple[str, str], int] = {}

    def ref(c: Citation) -> str:
        if not c.found:
            return "basis not found"
        key = (c.chunk.chunk_id, c.evidence)
        refs.setdefault(key, len(refs) + 1)
        return f"[{refs[key]}]"

    lines = [
        f"# Engineering change impact assessment: {ch.id}",
        "",
        f"**{ch.title}**",
        "",
        f"- Platform: {ch.platform}",
        f"- System: {ch.system}",
        "",
        ch.description,
        "",
        "## Change characteristics",
        "",
        "| Characteristic | Answer |",
        "|---|---|",
    ]
    for k, desc in a.vocabulary.items():
        v = ch.changes[k]
        lines.append(f"| {desc} | {'yes' if v is True else 'no' if v is False else '**unknown**'} |")

    def table(title: str, findings: list[Finding], note: str = "") -> None:
        if not findings:
            return
        lines.extend(["", f"## {title} ({len(findings)})", ""])
        if note:
            lines.extend([note, ""])
        lines.extend(["| # | ILS product | ILS element | Because | Action | Basis |", "|---|---|---|---|---|---|"])
        for n, f in enumerate(findings, 1):
            because = ", ".join(f.because)
            basis = " ".join(ref(c) for c in f.citations) or "-"
            lines.append(f"| {n} | {f.rule.product} | {f.rule.ils_element} | {because} | {f.rule.action} | {basis} |")

    table("Affected ILS products", a.by_status("affected"))
    table("Confirm with the EC team", a.by_status("confirm"),
          "These depend on answers the change request leaves open. Settle the unknown "
          "characteristics listed under *Because* and each item moves to affected or not affected.")
    questions = [(k, fs) for k, fs in a.open_questions() if fs]
    if questions:
        lines.extend(["", f"## Open questions for the EC team ({len(questions)})", "",
                      "Unknown answers in the change request, and the ILS products whose scope depends on each:", ""])
        for k, fs in questions:
            prods = "; ".join(f"{f.rule.product} ({f.status})" for f in fs)
            lines.append(f"- **{a.vocabulary[k]}?** Bears on: {prods}.")

    not_aff = a.by_status("not affected")
    if not_aff:
        lines.extend(["", f"## Not affected ({len(not_aff)})", ""])
        for f in not_aff:
            lines.append(f"- {f.rule.product}: none of its triggers apply "
                         f"({', '.join(f.rule.triggers)}).")

    if refs:
        lines.extend(["", "## Basis", ""])
        lookup = {(c.chunk.chunk_id, c.evidence): c for f in a.findings for c in f.citations if c.found}
        for (cid, phrase), n in sorted(refs.items(), key=lambda kv: kv[1]):
            c = lookup[(cid, phrase)].chunk
            lines.append(f"{n}. **{c.title}** ({c.issuer}) {_where(c)}: \"{_snippet(c, phrase)}\"  ")
            lines.append(f"   {c.url}")
    if a.missing_basis:
        lines.extend(["", "## Basis not found", "",
                      "These cited phrases are not in the indexed corpus (document not downloaded, "
                      "or reworded in a newer issue). Check the source before relying on the rule:", ""])
        for c in a.missing_basis:
            lines.append(f"- `{c.doc}`: \"{c.evidence}\"")

    non_cdn = sorted({c.chunk.issuer for f in a.findings if f.status != "not affected"
                      for c in f.citations if c.found and c.chunk.issuer != "DND/CAF"})
    lines.extend([
        "", "---", "",
        "Generated by naval-ils-rag `ec-impact` from public documents. "
        + (f"Passages from {', '.join(non_cdn)} sources describe that organization's practice, "
           "not RCN policy. " if non_cdn else "")
        + "This is a planning checklist, not an approved engineering or logistics decision.",
    ])
    return "\n".join(lines) + "\n"


def to_dict(a: Assessment) -> dict:
    return {
        "change": a.change.__dict__,
        "findings": [
            {
                "rule": f.rule.id, "product": f.rule.product, "ils_element": f.rule.ils_element,
                "status": f.status, "because": f.because, "action": f.rule.action,
                "basis": [
                    {"doc": c.doc, "evidence": c.evidence, "found": c.found,
                     "chunk_id": c.chunk.chunk_id if c.chunk else None,
                     "page": c.chunk.page if c.chunk else None,
                     "url": c.chunk.url if c.chunk else None}
                    for c in f.citations
                ],
            }
            for f in a.findings
        ],
        "open_questions": [{"characteristic": k, "products": [f.rule.id for f in fs]}
                           for k, fs in a.open_questions()],
        "missing_basis": [{"doc": c.doc, "evidence": c.evidence} for c in a.missing_basis],
    }


def check_rules(rules: list[Rule], chunks: list[Chunk]) -> list[str]:
    """Every rule's cited phrase should resolve in the corpus. Returns problems."""
    ev = EvidenceIndex(chunks)
    present = set(ev.by_doc)
    problems = []
    for r in rules:
        for b in r.basis:
            if b.doc not in present:
                problems.append(f"{r.id}: document {b.doc} is not in the index")
            elif ev.find(b.doc, b.evidence) is None:
                problems.append(f"{r.id}: phrase not found in {b.doc}: \"{b.evidence}\"")
    return problems


def load_chunks(index_dir: Path) -> list[Chunk]:
    path = Path(index_dir) / "chunks.jsonl"
    return [Chunk(**json.loads(l)) for l in path.read_text(encoding="utf-8").splitlines() if l]
