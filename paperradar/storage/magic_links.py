import json
import os
import secrets
import time
from typing import Dict, Optional

from paperradar.config import DATA_ROOT

MAGIC_LINKS_PATH = os.path.join(DATA_ROOT, "magic_links.json")
DEFAULT_TTL_SECONDS = 1800  # 30 minutes


def _ensure_parent():
    directory = os.path.dirname(MAGIC_LINKS_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _load_store() -> Dict[str, dict]:
    if not os.path.exists(MAGIC_LINKS_PATH):
        return {}
    try:
        with open(MAGIC_LINKS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_store(store: Dict[str, dict]) -> None:
    _ensure_parent()
    with open(MAGIC_LINKS_PATH, "w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)


def create_token(email: str, chat_id: int, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> dict:
    store = _load_store()
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    payload = {
        "email": email,
        "chat_id": chat_id,
        "created_at": now,
        "expires_at": now + max(60, ttl_seconds),
    }
    store[token] = payload
    _save_store(store)
    return {"token": token, **payload}


def consume_token(token: str) -> Optional[dict]:
    if not token:
        return None
    store = _load_store()
    payload = store.pop(token, None)
    if payload is None:
        return None
    _save_store(store)
    now = int(time.time())
    if payload.get("expires_at", 0) < now:
        return None
    return payload
