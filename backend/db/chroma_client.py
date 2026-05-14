"""
ChromaDB client (primary) with in-process FAISS fallback.

Why ChromaDB?
-------------
* Open-source, local-first, no SaaS lock-in.
* Built-in persistence & collection abstraction.
* HTTP client lets us scale the vector store as a separate container.
* Native support for metadata filters — critical for "find similar incidents
  but only those seen in the last 30 days with severity >= HIGH".

Embeddings are created with sentence-transformers (all-MiniLM-L6-v2, 384-dim)
— small enough for CPU, good enough for IR tasks.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.core.config import settings
from backend.core.logging import logger

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    _CHROMA_OK = True
except Exception as e:  # pragma: no cover
    logger.warning(f"Chroma import failed ({e}); will rely on FAISS fallback.")
    _CHROMA_OK = False

try:
    import faiss  # type: ignore
    import numpy as np
    _FAISS_OK = True
except Exception:
    _FAISS_OK = False


class VectorStore:
    """Unified interface over Chroma (preferred) and FAISS (fallback)."""

    def __init__(self) -> None:
        self._backend: str = "none"
        self._collection = None
        self._faiss_index = None
        self._faiss_meta: List[Dict[str, Any]] = []
        self._faiss_ids: List[str] = []

    # ---------- init ----------
    def connect(self) -> None:
        if _CHROMA_OK:
            try:
                client = chromadb.HttpClient(
                    host=settings.chroma_host,
                    port=settings.chroma_port,
                    settings=ChromaSettings(anonymized_telemetry=False),
                )
                # heartbeat to ensure the server is reachable
                client.heartbeat()
                self._collection = client.get_or_create_collection(
                    name=settings.chroma_collection,
                    metadata={"hnsw:space": "cosine"},
                )
                self._backend = "chroma"
                logger.info("VectorStore using ChromaDB")
                return
            except Exception as e:
                logger.warning(f"Chroma unreachable ({e}); falling back to FAISS")

        if _FAISS_OK:
            self._faiss_index = faiss.IndexFlatIP(384)  # inner-product on L2-norm vecs
            self._backend = "faiss"
            logger.info("VectorStore using FAISS in-memory fallback")
        else:
            logger.error("No vector backend available")
            self._backend = "none"

    # ---------- ops ----------
    def add(
        self,
        ids: List[str],
        embeddings: List[List[float]],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
    ) -> None:
        if self._backend == "chroma":
            assert self._collection is not None
            self._collection.upsert(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
        elif self._backend == "faiss":
            import numpy as np

            vecs = np.asarray(embeddings, dtype="float32")
            # L2 normalise for cosine via IP
            faiss.normalize_L2(vecs)
            assert self._faiss_index is not None
            self._faiss_index.add(vecs)
            for i, _id in enumerate(ids):
                self._faiss_ids.append(_id)
                self._faiss_meta.append(
                    {"document": documents[i], "metadata": metadatas[i]}
                )

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if self._backend == "chroma":
            assert self._collection is not None
            res = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
            )
            out = []
            for i in range(len(res["ids"][0])):
                out.append(
                    {
                        "id": res["ids"][0][i],
                        "document": res["documents"][0][i],
                        "metadata": res["metadatas"][0][i],
                        "distance": res["distances"][0][i] if res.get("distances") else None,
                    }
                )
            return out

        elif self._backend == "faiss":
            import numpy as np

            assert self._faiss_index is not None
            if self._faiss_index.ntotal == 0:
                return []
            q = np.asarray([query_embedding], dtype="float32")
            faiss.normalize_L2(q)
            D, I = self._faiss_index.search(q, min(n_results, self._faiss_index.ntotal))
            out = []
            for rank, idx in enumerate(I[0]):
                if idx < 0:
                    continue
                out.append(
                    {
                        "id": self._faiss_ids[idx],
                        "document": self._faiss_meta[idx]["document"],
                        "metadata": self._faiss_meta[idx]["metadata"],
                        "distance": float(1 - D[0][rank]),
                    }
                )
            return out

        return []

    def count(self) -> int:
        if self._backend == "chroma" and self._collection is not None:
            return self._collection.count()
        if self._backend == "faiss" and self._faiss_index is not None:
            return self._faiss_index.ntotal
        return 0


vector_store = VectorStore()
