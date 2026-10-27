"""Manifest loading and document downloads."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


@dataclass
class DocMeta:
    id: str
    title: str
    issuer: str
    kind: str
    format: str
    url: str
    fetch: str = "auto"
    note: str = ""
    optional: bool = False
    expect: str = ""  # text that must appear near the start of the file (identity check)
    extra: dict = field(default_factory=dict)

    def raw_path(self, raw_dir: Path) -> Path:
        return raw_dir / f"{self.id}.{self.format}"

    def cite_url(self, page: int | None = None, anchor: str | None = None) -> str:
        """Deep link a reader can click: #page=N for PDFs, #anchor for HTML."""
        if self.fetch == "manual" and not self.url.lower().endswith(".pdf"):
            return self.url  # landing page; we have no stable direct PDF link
        if self.format == "pdf" and page:
            return f"{self.url}#page={page}"
        if self.format == "html" and anchor:
            return f"{self.url}#{anchor}"
        return self.url


def load_manifest(path: Path) -> dict[str, DocMeta]:
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    docs: dict[str, DocMeta] = {}
    known = set(DocMeta.__dataclass_fields__) - {"extra"}
    for row in data.get("doc", []):
        extra = {k: v for k, v in row.items() if k not in known}
        meta = DocMeta(**{k: v for k, v in row.items() if k in known}, extra=extra)
        if meta.id in docs:
            raise ValueError(f"duplicate doc id in manifest: {meta.id}")
        docs[meta.id] = meta
    return docs


def _download(url: str, timeout: int = 60) -> bytes:
    """curl first: some government servers (canada.ca behind Akamai) stall
    Python's urllib at the TLS read but serve curl normally. curl ships with
    macOS, Linux and Windows 10+. urllib is the fallback."""
    curl = shutil.which("curl")
    if curl:
        proc = subprocess.run(
            [curl, "-sSL", "--fail", "--max-time", str(timeout), "-A", USER_AGENT, url],
            capture_output=True,
        )
        if proc.returncode == 0 and proc.stdout:
            return proc.stdout
        err = proc.stderr.decode(errors="replace").strip()
        if "403" in err:
            raise PermissionError("HTTP 403: site refuses scripted downloads; download it in a browser")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_all(docs: dict[str, DocMeta], raw_dir: Path, force: bool = False) -> list[str]:
    """Download every auto-fetch document. Returns human-readable status lines."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    report: list[str] = []

    def say(line: str) -> None:
        report.append(line)
        print(line, flush=True)  # stream progress; a full fetch takes a few minutes

    ledger_path = raw_dir / "fetch_ledger.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {}

    for meta in docs.values():
        target = meta.raw_path(raw_dir)
        if meta.fetch == "manual":
            state = "present" if target.exists() else "MISSING"
            prefix = "optional, " if meta.optional else ""
            say(f"[manual:{state}] {meta.id} ({prefix}{meta.note or meta.url})")
            continue
        if target.exists() and not force:
            say(f"[cached]  {meta.id}")
            continue
        try:
            body = _download(meta.url)
            if meta.format == "pdf" and not body.startswith(b"%PDF"):
                raise ValueError("response is not a PDF (blocked or redirected?)")
            target.write_bytes(body)
            ledger[meta.id] = {
                "url": meta.url,
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            ledger_path.write_text(json.dumps(ledger, indent=2))  # save as we go
            say(f"[ok]      {meta.id} ({len(body) // 1024} KB)")
        except Exception as exc:  # network errors should not stop the batch
            say(f"[failed]  {meta.id}: {exc}\n           -> download {meta.url}\n              and save it as data/raw/{target.name}")
        time.sleep(0.5)  # be polite to government web servers

    return report
