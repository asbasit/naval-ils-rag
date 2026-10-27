"""Hybrid retrieval: BM25 keyword search + dense embeddings, fused with RRF.

BM25 catches exact identifiers ("MIL-STD-3034A", "D-01-100-204") that
embeddings blur. Embeddings catch paraphrase ("how often do subs go into deep
maintenance" vs "EDWP ... six years of effective operation"). Reciprocal rank
fusion combines the two without having to calibrate their scores.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .chunk import Chunk
from .glossary import expand_query

STOPWORDS = set(
    "a an and are as at be by for from has have in is it its of on or that the this to was "
    "were will with which what who how when where why does do should shall may can".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:[-.&/+][a-z0-9]+)*\+?")

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_RERANK_MODEL = "Xenova/ms-marco-MiniLM-L-6-v2"  # 80 MB cross-encoder


def tokenize(text: str) -> list[str]:
    out: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in STOPWORDS:
            continue
        out.append(tok)
        # "mil-std-3034a" also indexes "mil", "std", "3034a"
        if re.search(r"[-./&]", tok):
            out.extend(p for p in re.split(r"[-./&]", tok) if p and p not in STOPWORDS)
    return out


class BM25:
    def __init__(self, docs_tokens: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs_tokens)
        self.lengths = np.array([len(d) for d in docs_tokens], dtype=np.float32)
        self.avgdl = float(self.lengths.mean()) if self.n else 0.0
        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for i, toks in enumerate(docs_tokens):
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.idf = {
            t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()
        }

    def scores(self, query_tokens: list[str]) -> np.ndarray:
        scores = np.zeros(self.n, dtype=np.float32)
        for term in set(query_tokens):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self.idf[term]
            for i, tf in postings:
                denom = tf + self.k1 * (1 - self.b + self.b * self.lengths[i] / self.avgdl)
                scores[i] += idf * tf * (self.k1 + 1) / denom
        return scores


class Embedder:
    """Thin wrapper so the rest of the code doesn't care which backend is used."""

    def __init__(self, model_name: str = DEFAULT_EMBED_MODEL):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.model = TextEmbedding(model_name)

    def passages(self, texts: list[str]) -> np.ndarray:
        vecs = np.array(list(self.model.passage_embed(texts, batch_size=32)), dtype=np.float32)
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    def query(self, text: str) -> np.ndarray:
        vec = np.array(next(iter(self.model.query_embed([text]))), dtype=np.float32)
        return vec / np.linalg.norm(vec)


class Reranker:
    """Cross-encoder: reads the query and a passage together and scores the
    pair. Slower than embeddings (one model pass per candidate) but much better
    at telling a precise answer from a passage that is merely on-topic."""

    def __init__(self, model_name: str = DEFAULT_RERANK_MODEL):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.model_name = model_name
        self.model = TextCrossEncoder(model_name)

    def scores(self, query: str, texts: list[str]) -> np.ndarray:
        return np.array(list(self.model.rerank(query, texts)), dtype=np.float32)


def _embed_cached(embedder: "Embedder", texts: list[str], cache_path: Path | None,
                  batch: int, progress) -> np.ndarray:
    """Embed texts, reusing vectors for passages already embedded with the same
    model. The cache is saved after every batch, so an interrupted ingest
    resumes where it stopped, and adding one document doesn't re-embed the rest."""
    import hashlib

    def key(t: str) -> str:
        return hashlib.sha1(f"{embedder.model_name}\n{t}".encode("utf-8")).hexdigest()

    cache: dict[str, np.ndarray] = {}
    if cache_path is not None and cache_path.exists():
        with np.load(cache_path) as z:
            cache = {k: z[k] for k in z.files}
    keys = [key(t) for t in texts]
    todo = [i for i, k in enumerate(keys) if k not in cache]
    for start in range(0, len(todo), batch):
        idx = todo[start:start + batch]
        for i, v in zip(idx, embedder.passages([texts[i] for i in idx])):
            cache[keys[i]] = v
        if cache_path is not None:
            tmp = cache_path.with_name(cache_path.stem + ".tmp.npz")
            np.savez(tmp, **cache)
            tmp.replace(cache_path)  # atomic: a kill mid-write can't corrupt the cache
        if progress:
            progress(min(start + batch, len(todo)), len(todo))
    return np.stack([cache[k] for k in keys]).astype(np.float32)


@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25_rank: int | None
    dense_rank: int | None


class HybridIndex:
    def __init__(self, chunks: list[Chunk], vectors: np.ndarray | None = None,
                 embedder: Embedder | None = None, reranker: Reranker | None = None):
        self.chunks = chunks
        self.reranker = reranker
        self.by_id = {c.chunk_id: c for c in chunks}
        self.bm25 = BM25([tokenize(f"{c.title} {c.heading} {c.text}") for c in chunks])
        self.vectors = vectors
        self.embedder = embedder

    # ------------------------------------------------------------- building
    @classmethod
    def build(cls, chunks: list[Chunk], dense: bool = True,
              model_name: str = DEFAULT_EMBED_MODEL, cache_path: Path | None = None,
              batch: int = 128, progress=None) -> "HybridIndex":
        vectors = embedder = None
        if dense and chunks:
            embedder = Embedder(model_name)
            # Title + heading give the embedding context the bare paragraph lacks.
            texts = [f"{c.title}. {c.heading}. {c.text}" for c in chunks]
            vectors = _embed_cached(embedder, texts, cache_path, batch, progress)
        return cls(chunks, vectors, embedder)

    def save(self, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "chunks.jsonl").open("w", encoding="utf-8") as f:
            for c in self.chunks:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
        info = {"n_chunks": len(self.chunks), "dense": self.vectors is not None}
        if self.vectors is not None:
            np.save(out_dir / "vectors.npy", self.vectors)
            info["embed_model"] = self.embedder.model_name
        (out_dir / "index_info.json").write_text(json.dumps(info, indent=2))

    @classmethod
    def load(cls, out_dir: Path, dense: bool = True, rerank: str | bool | None = None) -> "HybridIndex":
        """rerank: None/False = off, True = default cross-encoder, str = model name."""
        info = json.loads((out_dir / "index_info.json").read_text())
        chunks = [Chunk(**json.loads(line)) for line in
                  (out_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
        vectors = embedder = None
        if dense and info.get("dense"):
            vectors = np.load(out_dir / "vectors.npy")
            embedder = Embedder(info["embed_model"])
        reranker = None
        if rerank:
            reranker = Reranker(DEFAULT_RERANK_MODEL if rerank is True else rerank)
        return cls(chunks, vectors, embedder, reranker)

    # ------------------------------------------------------------ searching
    def search(self, query: str, k: int = 6, issuers: list[str] | None = None,
               doc_ids: list[str] | None = None, pool: int = 50, rrf_k: int = 60,
               rerank_pool: int = 30) -> list[Hit]:
        if not self.chunks:
            return []
        mask = np.ones(len(self.chunks), dtype=bool)
        if issuers:
            wanted = {i.lower() for i in issuers}
            mask &= np.array([c.issuer.lower() in wanted for c in self.chunks])
        if doc_ids:
            mask &= np.array([c.doc_id in set(doc_ids) for c in self.chunks])
        if not mask.any():
            return []

        expanded = expand_query(query)
        bm = self.bm25.scores(tokenize(expanded))
        bm[~mask] = -np.inf
        bm_order = [i for i in np.argsort(-bm)[:pool] if bm[i] > 0]

        dense_order: list[int] = []
        if self.vectors is not None:
            sims = self.vectors @ self.embedder.query(expanded)
            sims[~mask] = -np.inf
            dense_order = [int(i) for i in np.argsort(-sims)[:pool]]

        fused: dict[int, float] = defaultdict(float)
        bm_rank = {int(i): r for r, i in enumerate(bm_order)}
        de_rank = {i: r for r, i in enumerate(dense_order)}
        for i, r in bm_rank.items():
            fused[i] += 1.0 / (rrf_k + r + 1)
        for i, r in de_rank.items():
            fused[i] += 1.0 / (rrf_k + r + 1)

        ranked = sorted(fused.items(), key=lambda kv: -kv[1])
        if self.reranker is not None and ranked:
            # Rerank the fused shortlist with the cross-encoder. The original
            # question goes in (not the acronym-expanded one): the cross-encoder
            # reads language, it doesn't need keyword padding.
            short = [i for i, _ in ranked[:rerank_pool]]
            texts = [f"{self.chunks[i].title}. {self.chunks[i].heading}. {self.chunks[i].text}" for i in short]
            rs = self.reranker.scores(query, texts)
            ranked = [(short[j], float(rs[j])) for j in np.argsort(-rs)]
        hits, per_doc = [], Counter()
        for i, score in ranked:
            c = self.chunks[i]
            # Diversity cap: one long document shouldn't fill every slot.
            if per_doc[c.doc_id] >= max(2, k // 2):
                continue
            per_doc[c.doc_id] += 1
            hits.append(Hit(c, score, bm_rank.get(i), de_rank.get(i)))
            if len(hits) == k:
                break
        return hits

    def neighbours(self, chunk_id: str, radius: int = 1) -> list[Chunk]:
        c = self.by_id[chunk_id]
        out = []
        for s in range(c.seq - radius, c.seq + radius + 1):
            n = self.by_id.get(f"{c.doc_id}#{s:04d}")
            if n:
                out.append(n)
        return out
