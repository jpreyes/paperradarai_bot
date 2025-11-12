import json
import os
from typing import Optional

from paperradar.config import DATA_ROOT

EMAIL_INDEX_PATH = os.path.join(DATA_ROOT, "email_index.json")


def _ensure_parent():
    directory = os.path.dirname(EMAIL_INDEX_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _load_index() -> dict:
    if not os.path.exists(EMAIL_INDEX_PATH):
        return {}
    try:
        with open(EMAIL_INDEX_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_index(data: dict) -> None:
    _ensure_parent()
    with open(EMAIL_INDEX_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def get_chat_id(email: str) -> Optional[int]:
    normalized = normalize_email(email)
    if not normalized:
        return None
    data = _load_index()
    value = data.get(normalized)
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def set_chat_id(email: str, chat_id: int) -> None:
    normalized = normalize_email(email)
    if not normalized:
        return
    data = _load_index()
    data[normalized] = chat_id
    _save_index(data)
