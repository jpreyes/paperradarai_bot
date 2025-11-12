from __future__ import annotations

import hashlib
import json
import os
import re
from copy import deepcopy
from datetime import datetime
from typing import Dict, List, Tuple

from paperradar.config import OPENAI_EMBEDDING_MODEL, DATA_ROOT

JOURNAL_CATALOG_PATH = os.path.join(DATA_ROOT, "journals_catalog.json")
JOURNAL_EMBEDDINGS_PATH = os.path.join(DATA_ROOT, "journal_embeddings.json")

DEFAULT_JOURNALS: List[Dict[str, object]] = [
    {
        "id": "applied-ai-research",
        "title": "Journal of Applied AI Research",
        "publisher": "Open Science Alliance",
        "country": "United States",
        "languages": ["English"],
        "issn_print": "2767-9034",
        "issn_electronic": "2767-9042",
        "categories": ["Artificial Intelligence", "Data Science"],
        "topics": [
            "machine learning systems",
            "responsible AI deployment",
            "applied data science",
            "industry case studies",
        ],
        "aims_scope": (
            "Publishes applied artificial intelligence work with emphasis on "
            "deployments in engineering, education, health and government services."
        ),
        "metrics": {"impact_factor": 4.2, "sjr": 0.95},
        "speed": {"avg_weeks_to_decision": 10},
        "open_access": True,
        "apc_usd": 1200,
        "website": "https://journals.opensa.org/applied-ai",
    },
    {
        "id": "sustainability-transitions",
        "title": "Sustainability Transitions & Innovation",
        "publisher": "GreenWorks Press",
        "country": "Netherlands",
        "languages": ["English"],
        "issn_print": "2043-2815",
        "issn_electronic": "2043-2823",
        "categories": ["Sustainability", "Innovation Management"],
        "topics": [
            "circular economy",
            "policy innovation",
            "transition design",
            "systems thinking",
        ],
        "aims_scope": (
            "Focuses on multidisciplinary research about innovation pathways that accelerate "
            "environmental and social sustainability transitions."
        ),
        "metrics": {"impact_factor": 5.1, "sjr": 1.12},
        "speed": {"avg_weeks_to_decision": 14},
        "open_access": False,
        "apc_usd": None,
        "website": "https://greenworks.press/journals/sustainability-transitions",
    },
    {
        "id": "latin-american-health-tech",
        "title": "Latin American Journal of Health Tech",
        "publisher": "Consorcio Salud Digital",
        "country": "Colombia",
        "languages": ["Spanish", "English"],
        "issn_print": "2710-1189",
        "issn_electronic": "2710-1197",
        "categories": ["Digital Health", "Medical Informatics"],
        "topics": [
            "telemedicine",
            "clinical decision support",
            "public health innovation",
            "data governance",
        ],
        "aims_scope": (
            "Highlights research and deployments of digital health technologies across Latin America "
            "with emphasis on equitable and low-resource settings."
        ),
        "metrics": {"impact_factor": 3.1, "sjr": 0.65},
        "speed": {"avg_weeks_to_decision": 8},
        "open_access": True,
        "apc_usd": 680,
        "website": "https://saluddigital.lat/journal",
    },
]


def _ensure_parent(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _clone(records: List[Dict[str, object]]) -> List[Dict[str, object]]:
    return deepcopy(records)


def _slugify(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", text.lower())
    return cleaned.strip("-") or hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def journal_identifier(entry: Dict[str, object]) -> str:
    for key in ("id", "slug", "issn_electronic", "issn_print", "issn"):
        value = entry.get(key)
        if value:
            return str(value).strip().lower()
    title = str(entry.get("title") or entry.get("name") or "").strip()
    if title:
        return _slugify(title)
    raise ValueError("Journal entry needs at least one identifier (id, title or ISSN).")


def load_catalog() -> List[Dict[str, object]]:
    if not os.path.exists(JOURNAL_CATALOG_PATH):
        return _clone(DEFAULT_JOURNALS)
    try:
        with open(JOURNAL_CATALOG_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return _clone(DEFAULT_JOURNALS)


def _normalize_text(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _dedupe_key(entry: Dict[str, object]) -> str:
    for field in ("issn_print", "issn_electronic", "issn"):
        value = entry.get(field)
        if isinstance(value, list):
            value = value[0] if value else ""
        if value:
            return f"issn:{_normalize_text(str(value))}"
    title = entry.get("title") or entry.get("name")
    if title:
        return f"title:{_slugify(str(title))}"
    return f"id:{journal_identifier(entry)}"


def _merge_records(primary: Dict[str, object], incoming: Dict[str, object]) -> Dict[str, object]:
    merged = dict(primary)
    for key, value in incoming.items():
        if key not in merged or not merged[key]:
            merged[key] = value
    merged.setdefault("id", journal_identifier(merged))
    return merged


def _dedupe_records(records: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], int]:
    if not records:
        return [], 0
    cleaned: Dict[str, Dict[str, object]] = {}
    duplicates = 0
    for rec in records:
        key = _dedupe_key(rec)
        if key in cleaned:
            cleaned[key] = _merge_records(cleaned[key], rec)
            duplicates += 1
        else:
            cleaned[key] = rec
    ordered = sorted(cleaned.values(), key=lambda rec: rec.get("title") or rec.get("id"))
    return ordered, duplicates


def save_catalog(records: List[Dict[str, object]]) -> None:
    deduped, _ = _dedupe_records(records)
    _ensure_parent(JOURNAL_CATALOG_PATH)
    with open(JOURNAL_CATALOG_PATH, "w", encoding="utf-8") as fh:
        json.dump(deduped, fh, ensure_ascii=False, indent=2)


def upsert_entries(entries: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], int]:
    if not entries:
        return load_catalog(), 0
    catalog = {journal_identifier(rec): rec for rec in load_catalog()}
    updated = 0
    for raw_entry in entries:
        entry = dict(raw_entry or {})
        jid = journal_identifier(entry)
        entry["id"] = jid
        entry["updated_at"] = _now_iso()
        catalog[jid] = entry
        updated += 1
    ordered = sorted(catalog.values(), key=lambda rec: rec.get("title") or rec.get("id"))
    save_catalog(ordered)
    return load_catalog(), updated


def delete_entry(journal_id: str) -> bool:
    jid = (journal_id or "").strip().lower()
    if not jid:
        return False
    catalog = load_catalog()
    remaining = [rec for rec in catalog if journal_identifier(rec) != jid]
    if len(remaining) == len(catalog):
        return False
    save_catalog(remaining)
    return True


def dedupe_catalog() -> Dict[str, int]:
    catalog = load_catalog()
    deduped, duplicates = _dedupe_records(catalog)
    if duplicates:
        save_catalog(deduped)
    return {"total": len(deduped), "removed": duplicates}


def load_embedding_store() -> Dict[str, object]:
    if not os.path.exists(JOURNAL_EMBEDDINGS_PATH):
        return {"model": OPENAI_EMBEDDING_MODEL, "items": {}}
    try:
        with open(JOURNAL_EMBEDDINGS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
            if isinstance(data, dict):
                data.setdefault("model", OPENAI_EMBEDDING_MODEL)
                data.setdefault("items", {})
                return data
    except Exception:
        pass
    return {"model": OPENAI_EMBEDDING_MODEL, "items": {}}


def save_embedding_store(store: Dict[str, object]) -> None:
    payload = dict(store or {})
    payload.setdefault("model", OPENAI_EMBEDDING_MODEL)
    payload.setdefault("items", {})
    _ensure_parent(JOURNAL_EMBEDDINGS_PATH)
    with open(JOURNAL_EMBEDDINGS_PATH, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False)
