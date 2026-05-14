"""
Embedding pipeline — turns an incident's natural-language description into a
384-dim vector using sentence-transformers (all-MiniLM-L6-v2).

Why sentence-transformers?
 * Works offline after the model is downloaded.
 * CPU-friendly.
 * Good enough for semantic retrieval tasks (the research benchmark MTEB
   ranks MiniLM-L6-v2 competitively for its size).

The vectors are stored in ChromaDB (see backend/db/chroma_client.py).
"""
from __future__ import annotations

from functools import lru_cache
from typing import List

from backend.core.config import settings
from backend.core.logging import logger


@lru_cache(maxsize=1)
def _model():
    from sentence_transformers import SentenceTransformer

    logger.info(f"Loading sentence-transformer: {settings.embedding_model}")
    return SentenceTransformer(settings.embedding_model)


def embed(text: str) -> List[float]:
    vec = _model().encode(text, normalize_embeddings=True)
    return vec.tolist()


def embed_batch(texts: List[str]) -> List[List[float]]:
    vecs = _model().encode(texts, normalize_embeddings=True, batch_size=32)
    return [v.tolist() for v in vecs]


def incident_text(incident: dict) -> str:
    """Flatten an incident dict into a string suitable for embedding."""
    parts: list[str] = []
    parts.append(incident.get("title", ""))
    for ev in incident.get("events", []):
        parts.append(
            f"[{ev.get('event_type','')}] "
            f"{ev.get('src_ip','')}→{ev.get('dst_ip','')} "
            f"sev={ev.get('severity',0)} {ev.get('description','')}"
        )
    return " ".join(p for p in parts if p).strip()
