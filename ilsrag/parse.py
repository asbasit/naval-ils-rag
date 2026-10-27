"""Turn raw PDFs and HTML pages into ordered text blocks with location metadata.

A block is one paragraph-ish unit that remembers its page (PDF) or anchor
(HTML) and the nearest heading above it. Those three fields are what make a
citation checkable: a reader can open page 14 of the PDF, or jump to #s3 of
the web page, and find the sentence.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Block:
    text: str
    page: int | None = None
    heading: str = ""
    anchor: str | None = None


# --------------------------------------------------------------------------- PDF

_NUMBERED_HEADING = re.compile(r"^(\d+(\.\d+){0,3}|[A-Z]\.|Annex [A-Z]|Appendix \d+)\s+[A-Z][^.]{2,90}$")
_PAGE_NUMBER = re.compile(r"^(page\s+)?\d+(\s*(of|/)\s*\d+)?$|^[ivxlc]+(/[ivxlc]+)?$", re.I)
# Security / release markings appear on every page of DND, NATO and USN documents.
# Short documents defeat the repeat-detection below, so match them directly.
_MARKING = re.compile(
    r"^(information\s+)?(nato\s+)?(unclassified|official(\s*[-–]\s*sensitive)?)\b"
    r"|^classification\s*:|^distribution\s+statement\s+[a-f]\b"
    r"|^reviewed by .{0,40} access to information act",
    re.I,
)


_NAMED_SECTION = re.compile(
    r"^(executive summary|introduction|background|scope|methodology|findings|conclusions?|"
    r"recommendations?|references|acronyms( and abbreviations)?|definitions|purpose|"
    r"overall assessment|management action plan|annex [a-z]\b.*|appendix [a-z0-9]\b.*)$",
    re.I,
)


def _looks_like_heading(line: str) -> bool:
    if len(line) > 100 or len(line) < 4 or line.endswith((",", ";", ".")) and not _NUMBERED_HEADING.match(line):
        return False
    if _NAMED_SECTION.match(line.strip()):
        return True
    words = re.findall(r"[A-Za-z]{2,}", line)
    digits = sum(c.isdigit() for c in line)
    # Table rows ("FY 2013/14 FY 2014/15", "90% 75% 100%") and lone acronyms ("MCDV")
    # look upper-case too; require real words and few numbers.
    if "%" in line or digits > len(line) * 0.25:
        return False
    if _NUMBERED_HEADING.match(line):
        return True
    if len(words) < 2:
        return False
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 8 and sum(c.isupper() for c in letters) / len(letters) > 0.85


def _normalise_line(line: str) -> str:
    line = re.sub(r"\s+", " ", line).strip()
    # get_text(" ") puts spaces inside brackets and before punctuation
    # ("( disponible )", "Act , Policy"); tidy them so text reads and matches normally.
    return re.sub(r"\(\s+", "(", re.sub(r"\s+([),.;:])", r"\1", line))


def _boilerplate_lines(pages: list[list[str]], threshold: float = 0.4) -> set[str]:
    """Lines repeated on many pages are running headers/footers ("Information
    UNCLASSIFIED", report numbers). They pollute every chunk, so drop them."""
    if len(pages) < 4:
        return set()
    counts = Counter(line for page in pages for line in set(page))
    # Strip digits so "ADM(RS) iv/ix" and "ADM(RS) v/ix" count as the same line.
    digitless = Counter(re.sub(r"[\divxlc/]+", "#", l) for page in pages for l in set(page))
    limit = max(3, int(len(pages) * threshold))
    common = {l for l, n in counts.items() if n >= limit}
    common |= {
        l for page in pages for l in page
        if digitless[re.sub(r"[\divxlc/]+", "#", l)] >= limit and len(l) < 120
    }
    return common


def parse_pdf(path: Path) -> list[Block]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        raw = page.extract_text() or ""
        pages.append([_normalise_line(l) for l in raw.splitlines() if _normalise_line(l)])

    drop = _boilerplate_lines(pages)
    blocks: list[Block] = []
    heading = ""
    for page_no, lines in enumerate(pages, start=1):
        para: list[str] = []

        def flush():
            if para:
                text = " ".join(para)
                text = re.sub(r"(\w)- (\w)", r"\1\2", text)  # de-hyphenate line breaks
                if len(text) > 25 and len(text.split()) >= 5:
                    blocks.append(Block(text=text, page=page_no, heading=heading))
                para.clear()

        for line in lines:
            if line in drop or _PAGE_NUMBER.match(line) or re.fullmatch(r"[.\s]{5,}\d*", line):
                continue
            if len(line) < 140 and _MARKING.search(line):
                continue
            if re.search(r"\.{6,}\s*\d+$", line):  # table-of-contents leader line
                continue
            if _looks_like_heading(line):
                flush()
                heading = line[:120]
                continue
            para.append(line)
            # pypdf loses blank lines; a line ending a sentence that is much
            # shorter than its neighbours is a reasonable paragraph break.
            if line.endswith((".", ":")) and len(line) < 60:
                flush()
        flush()
    return blocks


# -------------------------------------------------------------------------- HTML

def parse_html(path: Path) -> list[Block]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(Path(path).read_text(encoding="utf-8", errors="replace"), "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "form", "noscript"]):
        tag.decompose()
    # canada.ca boilerplate: page-details box, archive banner, help widgets.
    # (Not <aside>: older canada.ca news releases put the article body in one.)
    for tag in soup.select(".pagedetails, #wb-dtmd, .gc-pg-hlpfl, #wb-info, .gc-archv, #archived"):
        tag.decompose()
    root = soup.find("main") or soup.body or soup

    blocks: list[Block] = []
    heading, anchor = "", None
    for el in root.find_all(_HEADINGS | _TEXT_BLOCKS):
        if el.name in _HEADINGS:
            heading = _normalise_line(el.get_text(" "))[:120]
            anchor = el.get("id") or (el.find(id=True) or {}).get("id") or anchor
            continue
        # Take text only from the innermost blocks: a <dd> holding a <p>, or an
        # <li> holding a nested list, would otherwise be read twice.
        if el.name != "tr" and el.find(_TEXT_BLOCKS | _HEADINGS):
            if el.name not in _CONTAINERS:
                _emit_own_text(el, heading, anchor, blocks)
            continue
        if el.name in _CONTAINERS:
            _emit_own_text(el, heading, anchor, blocks)
            continue
        if el.find_parent("tr"):
            continue  # captured as part of its table row
        if el.name == "tr":
            cells = [_normalise_line(c.get_text(" ")) for c in el.find_all(["th", "td"])]
            text = " | ".join(c for c in cells if c)
        else:
            text = _normalise_line(el.get_text(" "))
        # Definition terms are short ("available (disponible)") but carry the meaning
        # of the <dd> that follows, so keep them.
        if len(text) > 25 or (len(text) > 2 and _is_term(el)):
            prefix = "- " if el.name == "li" else ""
            blocks.append(Block(text=prefix + text, heading=heading, anchor=anchor))
    return blocks


def _is_term(el) -> bool:
    """A definition term: a <dt>, or a short paragraph led by a bold word
    (canada.ca DAODs write "<p><strong>available</strong> (disponible)</p>")."""
    if el.name == "dt":
        return True
    first = next((c for c in el.children if getattr(c, "name", None) or str(c).strip()), None)
    return getattr(first, "name", None) in ("strong", "b", "dfn")


_HEADINGS = {"h1", "h2", "h3", "h4", "h5"}
_TEXT_BLOCKS = {"p", "li", "tr", "dd", "dt", "pre", "blockquote", "div", "section", "td"}
_CONTAINERS = {"div", "section", "blockquote", "td"}
_INLINE = {"a", "strong", "em", "b", "i", "span", "abbr", "sup", "sub", "code", "time"}


def _emit_own_text(el, heading: str, anchor: str | None, blocks: list[Block]) -> None:
    """Text sitting directly in a container (e.g. a <div> using <br> instead of
    <p>) belongs to no inner block, so collect it here."""
    from bs4 import NavigableString

    parts = []
    for c in el.children:  # keep document order: text, <a>, text, <strong> ...
        if isinstance(c, NavigableString):
            parts.append(str(c))
        elif c.name in _INLINE and not c.find(_TEXT_BLOCKS):
            parts.append(c.get_text(" "))
    text = _normalise_line(" ".join(parts))
    if len(text) > 40:
        blocks.append(Block(text=text, heading=heading, anchor=anchor))


def parse_document(path: Path) -> list[Block]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix in (".html", ".htm"):
        return parse_html(path)
    if suffix in (".txt", ".md"):
        paras = re.split(r"\n\s*\n", path.read_text(encoding="utf-8"))
        return [Block(text=_normalise_line(p)) for p in paras if len(p.strip()) > 25]
    raise ValueError(f"unsupported format: {path}")
