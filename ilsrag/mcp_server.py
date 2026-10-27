"""MCP server: exposes the naval maintenance corpus as tools any MCP client
(Claude Desktop, Claude Code, ...) can call.

The tools are the same ones the built-in agent uses (ilsrag/agent.py ToolBox),
so behaviour is identical whether Claude reaches the corpus through this server
or through `python -m ilsrag ask`. The server is read-only.

Run:            python -m ilsrag.mcp_server
Claude Code:    claude mcp add naval-ils -- <venv python> -m ilsrag.mcp_server
                (run from the project folder, or set ILSRAG_HOME to it)
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from .agent import ToolBox
from .index import HybridIndex

HOME = Path(os.environ.get("ILSRAG_HOME", Path(__file__).resolve().parent.parent))

INSTRUCTIONS = """\
Search tools over public naval maintenance and in-service support documents \
(DND/CAF DAODs, ADM(RS) naval evaluations, the CF preventive maintenance \
instruction spec, the USN RCM standard MIL-STD-3034A, NATO material and ASD S4000P). Every passage \
carries a chunk_id, its issuer and a page or section. When answering from these \
passages, cite the chunk_id, keep issuers distinct (never present USN or NATO \
practice as RCN policy), and say plainly when the corpus does not cover a question."""

server = _Server("naval-ils-rag", instructions=INSTRUCTIONS)


@lru_cache(maxsize=1)
def _toolbox() -> ToolBox:
    index_dir = HOME / "data" / "index"
    if not (index_dir / "index_info.json").exists():
        raise RuntimeError(f"No index at {index_dir}. Run `python -m ilsrag fetch` and `ingest` first.")
    dense = os.environ.get("ILSRAG_DENSE", "1") != "0"
    from .cli import _rerank_setting
    return ToolBox(HybridIndex.load(index_dir, dense=dense, rerank=_rerank_setting()))


def _run(name: str, args: dict) -> dict:
    return json.loads(_toolbox().run(name, args))


@server.tool()
def search_corpus(query: str, k: int = 6, issuers: list[str] | None = None,
                  doc_ids: list[str] | None = None) -> dict:
    """Hybrid keyword + semantic search over the naval maintenance corpus.

    Returns passages with chunk_id, document, issuer (DND/CAF, USN, NATO, ASD),
    page or section, and text. Acronyms such as EDWP, RCM, CBM+, ISSC, FMF and
    PMI are expanded automatically. Use `issuers` to restrict to Canadian policy
    (["DND/CAF"]) or a foreign source; use `doc_ids` from list_documents to
    search inside one document.
    """
    args = {"query": query, "k": max(1, min(int(k), 10))}
    if issuers:
        args["issuers"] = issuers
    if doc_ids:
        args["doc_ids"] = doc_ids
    return _run("search_corpus", args)


@server.tool()
def read_passage(chunk_id: str, radius: int = 1) -> dict:
    """Return a passage plus up to `radius` neighbouring passages on each side,
    for when a search hit is cut off mid-list or mid-definition."""
    return _run("read_passage", {"chunk_id": chunk_id, "radius": max(0, min(int(radius), 2))})


@server.tool()
def list_documents() -> dict:
    """List the documents in the corpus with id, title, issuer, kind and size."""
    return _run("list_documents", {})


def main() -> None:
    server.run()  # stdio transport


if __name__ == "__main__":
    main()
