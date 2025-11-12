import json
import os
from typing import Dict, Any

from paperradar.config import DATA_ROOT, OPENAI_EMBEDDING_MODEL

PAPER_EMB_PATH = os.path.join(DATA_ROOT, "paper_embeddings.json")


def _ensure_parent(path: str) -> None:
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)


def load_store() -> Dict[str, Any]:
    if not os.path.exists(PAPER_EMB_PATH):
        return {"model": OPENAI_EMBEDDING_MODEL, "items": {}}
    try:
        with open(PAPER_EMB_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("model", OPENAI_EMBEDDING_MODEL)
                data.setdefault("items", {})
                return data
    except Exception:
        pass
    return {"model": OPENAI_EMBEDDING_MODEL, "items": {}}


def save_store(store: Dict[str, Any]) -> None:
    payload = dict(store or {})
    payload.setdefault("model", OPENAI_EMBEDDING_MODEL)
    payload.setdefault("items", {})
    _ensure_parent(PAPER_EMB_PATH)
    with open(PAPER_EMB_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
