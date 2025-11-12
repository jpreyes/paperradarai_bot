from __future__ import annotations

from typing import Dict, Sequence

from paperradar.fetchers.journals_crossref import fetch_journal_candidates_from_crossref
from paperradar.storage import journals as journal_store


def refresh_journals_from_crossref(
    user_state: Dict[str, object],
    *,
    limit: int = 25,
) -> Dict[str, object]:
    topics: Sequence[str] = user_state.get("profile_topics") or []
    summary = user_state.get("profile_summary") or user_state.get("profile") or ""
    entries = fetch_journal_candidates_from_crossref(topics, summary, max_entries=limit)
    if not entries:
        return {"updated": 0, "entries": [], "catalog_size": len(journal_store.load_catalog())}
    catalog, updated = journal_store.upsert_entries(entries)
    return {
        "updated": updated,
        "entries": entries,
        "catalog_size": len(catalog),
    }

