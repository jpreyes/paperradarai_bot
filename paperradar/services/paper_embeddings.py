from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from paperradar.config import DEFAULT_PAPER_EMBED_MAX, OPENAI_EMBEDDING_MODEL
from paperradar.services.embeddings import embed_text, EmbeddingError
from paperradar.storage import paper_embeddings as store_mod


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _paper_key(item: Dict[str, object]) -> str | None:
    key = (item.get("id") or item.get("url") or item.get("title") or "") if item else ""
    key = str(key).strip()
    if not key:
        return None
    return key[:200]


def _paper_text(item: Dict[str, object]) -> str:
    if not item:
        return ""
    parts = [
        item.get("title") or "",
        item.get("abstract") or "",
        item.get("venue") or "",
        " ".join(item.get("authors") or []),
        item.get("source") or "",
        item.get("url") or "",
    ]
    return "\n".join(part for part in parts if part).strip()


def ensure_paper_embeddings(
    papers: Iterable[Dict[str, object]],
    *,
    max_new: int | None = None,
) -> Dict[str, int]:
    """Ensure embeddings exist for the provided papers."""
    papers = list(papers or [])
    if not papers:
        return {"processed": 0, "created": 0}
    max_budget = max_new or DEFAULT_PAPER_EMBED_MAX
    store = store_mod.load_store()
    store_items = store.setdefault("items", {})
    embedding_model = store.get("model") or OPENAI_EMBEDDING_MODEL
    created = 0
    processed = 0
    dirty = False
    for paper in papers:
        key = _paper_key(paper)
        if not key:
            continue
        processed += 1
        text = _paper_text(paper)
        if not text:
            continue
        fingerprint = hashlib.sha1((text + embedding_model).encode("utf-8")).hexdigest()
        payload = store_items.get(key)
        if payload and payload.get("fingerprint") == fingerprint:
            continue
        if created >= max_budget:
            continue
        try:
            vector = embed_text(text, model=embedding_model)
        except EmbeddingError as exc:
            logging.warning("[papers-emb] skip %s: %s", key, exc)
            continue
        store_items[key] = {
            "vector": vector,
            "fingerprint": fingerprint,
            "model": embedding_model,
            "title": paper.get("title"),
            "source": paper.get("source"),
            "updated_at": _now_iso(),
        }
        created += 1
        dirty = True
    if dirty:
        store_mod.save_store(store)
    return {"processed": processed, "created": created}
