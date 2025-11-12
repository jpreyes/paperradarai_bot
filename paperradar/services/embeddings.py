from __future__ import annotations

import hashlib
import json
import logging
from typing import Dict, List, Optional

import requests

from paperradar.config import OPENAI_API_KEY, OPENAI_EMBEDDING_MODEL

EMBED_CACHE: Dict[str, List[float]] = {}


class EmbeddingError(RuntimeError):
    pass


def _fingerprint(text: str, model: str) -> str:
    h = hashlib.sha256()
    h.update((model or OPENAI_EMBEDDING_MODEL).encode("utf-8"))
    h.update(b"\0")
    h.update((text or "").encode("utf-8"))
    return h.hexdigest()


def embed_text(
    text: str,
    *,
    model: Optional[str] = None,
    timeout: int = 30,
) -> List[float]:
    """Generate an embedding vector for the provided text."""
    if not OPENAI_API_KEY:
        raise EmbeddingError("OPENAI_API_KEY no configurada para embeddings.")
    cleaned = (text or "").strip()
    if not cleaned:
        raise EmbeddingError("No hay texto para generar el embedding.")
    target_model = model or OPENAI_EMBEDDING_MODEL
    snippet = cleaned if len(cleaned) <= 8000 else cleaned[:8000]
    key = _fingerprint(snippet, target_model)
    if key in EMBED_CACHE:
        return EMBED_CACHE[key]
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {"input": snippet, "model": target_model}
    try:
        resp = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers=headers,
            data=json.dumps(body),
            timeout=timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        vector = payload["data"][0]["embedding"]
        if not isinstance(vector, list):
            raise EmbeddingError("Respuesta de embedding invalida.")
        EMBED_CACHE[key] = vector
        return vector
    except Exception as exc:
        logging.warning("[embeddings] fallo al generar embedding: %s", exc)
        raise EmbeddingError(str(exc)) from exc

