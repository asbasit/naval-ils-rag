"""Pack parse blocks into retrieval chunks.

Rules that matter for citation quality:
- A chunk never spans two PDF pages, so every citation points at one page.
- A chunk never spans two headings, so the section label stays honest.
- Chunks carry a small word overlap with their predecessor, so a definition
  split across a boundary is still retrievable from either side.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .corpus import DocMeta
from .parse import Block


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    seq: int
    text: str
    page: int | None
    heading: str
    anchor: str | None
    title: str
    issuer: str
    kind: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)

    def label(self) -> str:
        loc = f"p.{self.page}" if self.page else (self.heading or "web page")
        return f"{self.title}, {loc}"


def chunk_blocks(meta: DocMeta, blocks: list[Block], target_words: int = 180,
                 max_words: int = 260, overlap_words: int = 35) -> list[Chunk]:
    chunks: list[Chunk] = []
    buf: list[str] = []
    buf_words = 0
    current: Block | None = None
    carry = ""

    def emit():
        nonlocal buf, buf_words, carry
        if not buf or current is None:
            return
        body = " ".join(buf)
        text = f"{carry} {body}".strip() if carry else body
        seq = len(chunks)
        chunks.append(Chunk(
            chunk_id=f"{meta.id}#{seq:04d}", doc_id=meta.id, seq=seq, text=text,
            page=current.page, heading=current.heading, anchor=current.anchor,
            title=meta.title, issuer=meta.issuer, kind=meta.kind,
            url=meta.cite_url(current.page, current.anchor),
        ))
        words = body.split()
        carry = "… " + " ".join(words[-overlap_words:]) if len(words) > overlap_words * 2 else ""
        buf, buf_words = [], 0

    for block in blocks:
        boundary = current is not None and (
            block.page != current.page or block.heading != current.heading
        )
        if boundary:
            emit()
            carry = ""  # no overlap across pages/sections: it would mislabel the location
        if current is None or boundary or not buf:
            current = block
        words = block.text.split()
        # A single huge paragraph (tables, run-on PDF text) is split on its own.
        while len(words) > max_words:
            if buf:
                emit()
            buf, buf_words = [" ".join(words[:target_words])], target_words
            emit()
            words = words[target_words - overlap_words:]
        if buf_words + len(words) > max_words:
            emit()
        buf.append(" ".join(words))
        buf_words += len(words)
        if buf_words >= target_words:
            emit()
    emit()
    return chunks
