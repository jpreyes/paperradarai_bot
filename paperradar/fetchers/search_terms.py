"""
Utilities to manage dynamic search terms used by fetchers.

The default engineering terms remain the baseline. When a user uploads a new
profile (for example via PDF), we extract the key topics and persist them so the
fetchers can query domain-specific keywords on the next run.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Iterable, List

from paperradar.config import DATA_ROOT

os.makedirs(DATA_ROOT, exist_ok=True)

DEFAULT_TERMS: List[str] = [
    '"operational modal analysis"',
    "stochastic subspace",
    "system identification",
    "structural health monitoring",
    '"damage detection" bridge',
    '"damage detection" building',
    '"soil-structure interaction" bridge',
    '"soil-structure interaction" building',
    '"modal parameters" bridge',
    '"modal parameters" building',
    '"seismic" bridge modal',
    '"seismic" building modal',
]

_TERMS_PATH = os.path.join(DATA_ROOT, "search_terms.json")
_cache: List[str] | None = None


def _normalize(raw_terms: Iterable[str]) -> List[str]:
    """Strip, deduplicate (case-insensitive) and keep short phrases."""
    out: List[str] = []
    seen = set()
    for term in raw_terms:
        try:
            cleaned = str(term).strip()
        except Exception:
            continue
        if not cleaned:
            continue
        key = cleaned.lower().replace('"', "")
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _quote_if_needed(term: str) -> str:
    """Wrap multi-word terms with double quotes for better API matching."""
    if " " in term and not (term.startswith('"') and term.endswith('"')):
        return f'"{term}"'
    return term


def _load_terms() -> List[str]:
    if not os.path.exists(_TERMS_PATH):
        return list(DEFAULT_TERMS)
    try:
        with open(_TERMS_PATH, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            raw = payload.get("terms", [])
        else:
            raw = payload
        terms: List[str] = []
        index = {}

        def add_term(value: object, *, prefer: bool = False) -> None:
            cleaned = str(value or "").strip()
            if not cleaned:
                return
            key = cleaned.lower().replace('"', "")
            pos = index.get(key)
            if pos is not None:
                if prefer:
                    terms[pos] = cleaned
                return
            index[key] = len(terms)
            terms.append(cleaned)

        for entry in raw:
            add_term(entry)
        for base in DEFAULT_TERMS:
            add_term(base, prefer=True)
        if terms:
            return terms
    except Exception as exc:
        logging.warning(f"[terms] failed to load dynamic terms: {exc}")
    return list(DEFAULT_TERMS)


def _save_terms(terms: List[str]) -> None:
    os.makedirs(DATA_ROOT, exist_ok=True)
    payload = {
        "terms": terms,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with open(_TERMS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def get_search_terms() -> List[str]:
    """
    Return the active search terms for fetchers.

    Falls back to DEFAULT_TERMS if no custom terms are stored.
    """
    global _cache
    if _cache is None:
        _cache = _load_terms()
    return list(_cache)


def set_custom_terms(topics: Iterable[str], *, include_defaults: bool = True, max_terms: int = 20) -> List[str]:
    """
    Persist normalized search terms derived from profile topics and return them.

    Parameters
    ----------
    topics:
        Iterable of topics/keywords extracted from the user's profile.
    include_defaults:
        Whether to append the default engineering terms after the custom ones.
        This keeps a reliable fallback while prioritizing new interests.
    max_terms:
        Cap for how many custom terms we persist (after normalization).
    """
    custom = [_quote_if_needed(t) for t in _normalize(topics)][:max_terms]
    if include_defaults:
        baseline = _normalize(DEFAULT_TERMS)
        combined = custom + [t for t in baseline if t.lower() not in {c.lower() for c in custom}]
    else:
        combined = custom or list(DEFAULT_TERMS)
    if not combined:
        combined = list(DEFAULT_TERMS)
    global _cache
    if _cache is None:
        _cache = _load_terms()
    if _cache == combined:
        return list(_cache)
    _cache = combined
    _save_terms(combined)
    return list(_cache)


def reset_terms() -> None:
    """Remove any persisted custom terms and revert to defaults."""
    global _cache
    _cache = list(DEFAULT_TERMS)
    try:
        if os.path.exists(_TERMS_PATH):
            os.remove(_TERMS_PATH)
    except Exception as exc:
        logging.warning(f"[terms] failed to remove {_TERMS_PATH}: {exc}")
        # Keep going so callers still see defaults cached.


def prepare_term(term: str) -> str:
    """Public helper to sanitize and quote terms when needed."""
    return _quote_if_needed(str(term or "").strip())
