from __future__ import annotations

import logging
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

import requests

from paperradar.config import CROSSREF_MAILTO, ENABLE_CROSSREF

BASE_URL = "https://api.crossref.org"
USER_AGENT = (
    f"paperradar-bot/1.0 (mailto:{CROSSREF_MAILTO})"
    if CROSSREF_MAILTO
    else "paperradar-bot/1.0"
)
MAX_TOPICS = 6
ROWS_PER_TOPIC = 75
MAX_JOURNALS = 40
MAX_JOURNAL_DETAIL = 30


def _select_topics(topics: Sequence[str], fallback_summary: str) -> List[str]:
    if topics:
        cleaned = [t.strip() for t in topics if t and t.strip()]
        if cleaned:
            return cleaned[:MAX_TOPICS]
    if fallback_summary:
        words = [
            token.strip(",.;: ").lower()
            for token in fallback_summary.split()
            if len(token) > 3
        ]
        uniq = []
        for token in words:
            if token not in uniq:
                uniq.append(token)
            if len(uniq) >= MAX_TOPICS:
                break
        if uniq:
            return uniq
    return ["research", "innovation", "engineering"]


def _request(path: str, params: Dict[str, object] | None = None) -> Dict:
    if not ENABLE_CROSSREF:
        raise RuntimeError("Crossref disabled via config.")
    params = dict(params or {})
    if CROSSREF_MAILTO:
        params.setdefault("mailto", CROSSREF_MAILTO)
    headers = {"User-Agent": USER_AGENT}
    url = f"{BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    resp = requests.get(url, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", data)


def _discover_issn_candidates(topics: Sequence[str], summary: str) -> Tuple[List[str], Dict[str, Dict[str, object]]]:
    selected_topics = _select_topics(topics, summary)
    counter: Counter[str] = Counter()
    journal_meta: Dict[str, Dict[str, object]] = defaultdict(
        lambda: {"sample_titles": set(), "subjects": set(), "topics": set()}
    )
    for topic in selected_topics:
        try:
            message = _request(
                "/works",
                {
                    "filter": "type:journal-article",
                    "rows": ROWS_PER_TOPIC,
                    "select": "ISSN,container-title,subject",
                    "sort": "is-referenced-by-count",
                    "order": "desc",
                    "query.bibliographic": topic,
                },
            )
        except Exception as exc:
            logging.warning("[journals-crossref] works query failed (%s): %s", topic, exc)
            continue
        items = message.get("items", [])
        for item in items:
            issns = item.get("ISSN") or []
            if not issns:
                continue
            container = ""
            container_titles = item.get("container-title") or []
            if container_titles:
                container = container_titles[0]
            subjects = item.get("subject") or []
            for issn in issns:
                slug = issn.strip().lower()
                if not slug:
                    continue
                counter[slug] += 1
                meta = journal_meta[slug]
                if container:
                    meta["sample_titles"].add(container)
                for subj in subjects:
                    if isinstance(subj, dict):
                        name = subj.get("name")
                    else:
                        name = str(subj)
                    if name:
                        meta["subjects"].add(name)
                meta["topics"].add(topic)
    top_issns = [issn for issn, _ in counter.most_common(MAX_JOURNALS)]
    return top_issns, journal_meta


def _subjects_from_payload(payload: Dict[str, object]) -> List[str]:
    subjects = payload.get("subjects") or []
    values = []
    for subj in subjects:
        name = subj.get("name") if isinstance(subj, dict) else subj
        if name:
            name_str = str(name).strip()
            if name_str:
                values.append(name_str)
    return values


def _extract_issn_pair(detail: Dict[str, object]) -> Tuple[str | None, str | None]:
    issn_print = None
    issn_electronic = None
    for item in detail.get("issn-type") or []:
        itype = (item.get("type") or "").lower()
        value = item.get("value")
        if not value:
            continue
        if itype == "print" and not issn_print:
            issn_print = value
        elif itype in ("electronic", "online") and not issn_electronic:
            issn_electronic = value
    if not issn_print:
        issn_print = detail.get("ISSN") or None
        if isinstance(issn_print, list):
            issn_print = issn_print[0] if issn_print else None
    if not issn_electronic:
        issn_electronic = detail.get("ISSN") or None
        if isinstance(issn_electronic, list):
            issn_electronic = issn_electronic[-1] if issn_electronic else None
    return issn_print, issn_electronic


def fetch_journal_candidates_from_crossref(
    topics: Sequence[str],
    summary: str = "",
    *,
    max_entries: int | None = None,
) -> List[Dict[str, object]]:
    """
    Discover journal metadata from Crossref using profile topics/summary.
    Returns entries ready for storage.upsert_entries.
    """
    issns, meta = _discover_issn_candidates(topics, summary)
    if not issns:
        return []
    entries = []
    limit = max_entries or MAX_JOURNAL_DETAIL
    for issn in issns[:limit]:
        try:
            detail = _request(f"/journals/{issn}")
        except Exception as exc:
            logging.debug("[journals-crossref] detail failed (%s): %s", issn, exc)
            continue
        title = detail.get("title") or detail.get("short-title") or ""
        publisher = detail.get("publisher") or ""
        subjects = _subjects_from_payload(detail)
        combined_topics = set(meta[issn]["topics"])
        combined_topics.update(meta[issn]["subjects"])
        combined_topics.update(subjects)
        aim_bits = []
        if subjects:
            aim_bits.append(f"Subjects: {', '.join(subjects[:5])}")
        samples = list(meta[issn]["sample_titles"])
        if samples:
            aim_bits.append(f"Example scope: {samples[0]}")
        if not aim_bits and combined_topics:
            aim_bits.append(f"Frequent topics: {', '.join(list(combined_topics)[:5])}")
        aims_scope = ". ".join(aim_bits)
        counts = detail.get("counts") or {}
        flags = detail.get("flags") or {}
        issn_print, issn_elec = _extract_issn_pair(detail)
        entry = {
            "id": issn,
            "title": title or samples[0] if samples else issn.upper(),
            "publisher": publisher,
            "issn_print": issn_print or issn,
            "issn_electronic": issn_elec,
            "categories": subjects[:8],
            "topics": list(combined_topics)[:12],
            "aims_scope": aims_scope,
            "website": detail.get("URL"),
            "open_access": flags.get("is_oa"),
            "metrics": {
                "total_dois": counts.get("total-dois"),
                "current_dois": counts.get("current-dois"),
                "backfile_dois": counts.get("backfile-dois"),
            },
            "speed": {},
        }
        entries.append(entry)
    return entries
