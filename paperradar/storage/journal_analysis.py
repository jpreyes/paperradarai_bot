import json
import os
from typing import Dict, Optional

from paperradar.config import DATA_ROOT

ANALYSIS_CACHE_PATH = os.path.join(DATA_ROOT, "journal_analysis_cache.json")


def _ensure_parent():
    directory = os.path.dirname(ANALYSIS_CACHE_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)


def _load_cache() -> Dict[str, Dict[str, dict]]:
    if not os.path.exists(ANALYSIS_CACHE_PATH):
        return {}
    try:
        with open(ANALYSIS_CACHE_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save_cache(cache: Dict[str, Dict[str, dict]]) -> None:
    _ensure_parent()
    with open(ANALYSIS_CACHE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cache, fh, ensure_ascii=False)


def get_analysis(chat_id: int, journal_id: str) -> Optional[dict]:
    cache = _load_cache()
    chat_key = str(chat_id)
    journal_key = (journal_id or "").strip().lower()
    if not journal_key or chat_key not in cache:
        return None
    payload = cache[chat_key].get(journal_key)
    return payload


def set_analysis(chat_id: int, journal_id: str, analysis: dict) -> None:
    cache = _load_cache()
    chat_key = str(chat_id)
    journal_key = (journal_id or "").strip().lower()
    if not journal_key:
        return
    bucket = cache.setdefault(chat_key, {})
    bucket[journal_key] = analysis
    _save_cache(cache)


def clear_for_chat(chat_id: int) -> None:
    cache = _load_cache()
    chat_key = str(chat_id)
    if chat_key in cache:
        cache.pop(chat_key, None)
        _save_cache(cache)


def clear_all() -> None:
    if os.path.exists(ANALYSIS_CACHE_PATH):
        os.remove(ANALYSIS_CACHE_PATH)
