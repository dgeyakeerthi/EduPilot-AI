"""Persistent local Nomic embeddings with FAISS acceleration and safe fallback.

The vector space is identified by model name + corpus fingerprint. Index files are
written atomically and never reused across model versions or changed corpora.
No document text is sent to a cloud embedding provider.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Sequence

DEFAULT_MODEL = "nomic-embed-text-v2-moe"


class EmbeddingUnavailable(RuntimeError):
    """Raised when the configured local embedding model cannot be reached."""


class LocalNomicIndex:
    def __init__(self, model: str | None = None, base_url: str | None = None,
                 index_dir: str | None = None):
        self.model = model or os.getenv("EMBED_MODEL", DEFAULT_MODEL)
        self.base_url = (base_url or os.getenv("OLLAMA_URL", "http://localhost:11434")).rstrip("/")
        self.index_dir = Path(index_dir or os.getenv("EMBED_INDEX_DIR", "data/semantic_index"))
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index = None
        self.vectors: list[list[float]] = []
        self.texts: list[str] = []
        self.fingerprint: str | None = None
        self.backend = "not_initialized"
        self.dimension: int | None = None

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        payload = json.dumps({"model": self.model, "input": list(texts)}).encode("utf-8")
        req = urllib.request.Request(self.base_url + "/api/embed", payload,
                                     {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                data = json.load(response)
            vectors = data.get("embeddings")
            if not isinstance(vectors, list) or len(vectors) != len(texts):
                raise ValueError("Ollama returned an incomplete embedding response")
            clean = [[float(x) for x in row] for row in vectors]
            dims = {len(row) for row in clean}
            if len(dims) != 1 or not clean[0] or any(not math.isfinite(x) for row in clean for x in row):
                raise ValueError("Ollama returned invalid or inconsistent vectors")
            return clean
        except Exception as exc:
            raise EmbeddingUnavailable(f"Local Nomic embedding unavailable: {exc}") from exc

    @staticmethod
    def _fingerprint(texts: Sequence[str], model: str) -> str:
        digest = hashlib.sha256(model.encode("utf-8"))
        for text in texts:
            digest.update(b"\0")
            digest.update(text.encode("utf-8", "replace"))
        return digest.hexdigest()

    @staticmethod
    def _atomic_write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def build(self, texts: Sequence[str]) -> dict:
        clean_texts = [str(t) for t in texts]
        if not clean_texts:
            raise ValueError("Cannot build a semantic index from an empty corpus")
        fp = self._fingerprint(clean_texts, self.model)
        vectors = self.embed(clean_texts)
        dimension = len(vectors[0])
        if any(len(v) != dimension for v in vectors):
            raise ValueError("Embedding dimensions differ within the corpus")

        backend = "numpy_cosine"
        try:
            import numpy as np
            matrix = np.asarray(vectors, dtype="float32")
            norms = np.linalg.norm(matrix, axis=1, keepdims=True)
            matrix = matrix / np.maximum(norms, 1e-12)
            try:
                import faiss
                faiss.normalize_L2(matrix)
                index = faiss.IndexFlatIP(dimension)
                index.add(matrix)
                faiss.write_index(index, str(self.index_dir / "scholarships.faiss.tmp"))
                os.replace(self.index_dir / "scholarships.faiss.tmp", self.index_dir / "scholarships.faiss")
                backend = "faiss"
            except ImportError:
                index = matrix
        except ImportError:
            matrix = None
            index = vectors
            backend = "python_cosine"

        self.index, self.vectors, self.texts = index, vectors, clean_texts
        self.fingerprint, self.backend, self.dimension = fp, backend, dimension
        metadata = {"model": self.model, "fingerprint": fp, "count": len(clean_texts),
                    "dimension": dimension, "backend": backend, "format_version": 2}
        self._atomic_write(self.index_dir / "texts.json", json.dumps(clean_texts, ensure_ascii=False).encode())
        self._atomic_write(self.index_dir / "vectors.json", json.dumps(vectors).encode())
        self._atomic_write(self.index_dir / "metadata.json", json.dumps(metadata, indent=2).encode())
        return {"count": len(clean_texts), "model": self.model, "backend": backend,
                "fingerprint": fp, "rebuilt": True}

    def load(self, texts: Sequence[str]) -> bool:
        """Load a saved index only if model, corpus and dimensions still match."""
        clean_texts = [str(t) for t in texts]
        if not clean_texts:
            return False
        try:
            metadata = json.loads((self.index_dir / "metadata.json").read_text("utf-8"))
            saved_texts = json.loads((self.index_dir / "texts.json").read_text("utf-8"))
            vectors = json.loads((self.index_dir / "vectors.json").read_text("utf-8"))
            fp = self._fingerprint(clean_texts, self.model)
            if metadata.get("format_version") != 2 or metadata.get("model") != self.model:
                return False
            if metadata.get("fingerprint") != fp or saved_texts != clean_texts or len(vectors) != len(clean_texts):
                return False
            dimension = int(metadata["dimension"])
            if not vectors or any(len(v) != dimension for v in vectors):
                return False
            backend = "python_cosine"
            index = vectors
            try:
                import faiss
                index_path = self.index_dir / "scholarships.faiss"
                if index_path.exists():
                    index = faiss.read_index(str(index_path))
                    if index.ntotal != len(clean_texts) or index.d != dimension:
                        return False
                    backend = "faiss"
            except ImportError:
                pass
            self.index, self.vectors, self.texts = index, vectors, clean_texts
            self.fingerprint, self.backend, self.dimension = fp, backend, dimension
            return True
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False

    def ensure(self, texts: Sequence[str]) -> dict:
        clean_texts = [str(t) for t in texts]
        fp = self._fingerprint(clean_texts, self.model)
        if self.fingerprint == fp and self.texts == clean_texts and self.index is not None:
            return {"count": len(clean_texts), "model": self.model, "backend": self.backend,
                    "fingerprint": fp, "rebuilt": False}
        if self.load(clean_texts):
            return {"count": len(clean_texts), "model": self.model, "backend": self.backend,
                    "fingerprint": fp, "rebuilt": False}
        return self.build(clean_texts)

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        if self.index is None or not self.texts or k <= 0:
            return []
        query_vector = self.embed([query])[0]
        if len(query_vector) != self.dimension:
            raise EmbeddingUnavailable("Query embedding dimension does not match the saved index")
        try:
            import numpy as np
            qv = np.asarray([query_vector], dtype="float32")
            qv /= np.maximum(np.linalg.norm(qv, axis=1, keepdims=True), 1e-12)
            if self.backend == "faiss":
                scores, ids = self.index.search(qv, min(k, len(self.texts)))
                return [(int(i), float(s)) for i, s in zip(ids[0], scores[0]) if i >= 0]
        except ImportError:
            pass
        qnorm = math.sqrt(sum(x*x for x in query_vector)) or 1.0
        ranked = []
        for i, vector in enumerate(self.vectors):
            denom = qnorm * (math.sqrt(sum(x*x for x in vector)) or 1.0)
            score = sum(a*b for a, b in zip(query_vector, vector)) / denom
            ranked.append((i, float(score)))
        return sorted(ranked, key=lambda pair: pair[1], reverse=True)[:min(k, len(ranked))]
