import requests
import logging

from paperradar.core.filters import english_only, sanitize_text, year_from_date
from paperradar.config import CROSSREF_MAILTO


def pass_hard_filters(blob: str) -> bool:
    bad = ["retraction notice", "erratum"]
    lb = blob.lower()
    return not any(b in lb for b in bad)


TERMS = [
    '"operational modal analysis"', "stochastic subspace", "system identification", "structural health monitoring",
    '"damage detection" bridge', '"damage detection" building',
    '"soil-structure interaction" bridge', '"soil-structure interaction" building',
    '"modal parameters" bridge', '"modal parameters" building',
    '"seismic" bridge modal', '"seismic" building modal'
]

BASE_URL = "https://api.crossref.org/works"
USER_AGENT = f"paperradar-bot/1.0 (mailto:{CROSSREF_MAILTO})" if CROSSREF_MAILTO else "paperradar-bot/1.0"


def fetch(max_results=50):
    items = []
    headers = {"User-Agent": USER_AGENT}
    for term in TERMS:
        params = {
            "query": term,
            "rows": max_results,
            "sort": "published",
            "order": "desc",
        }
        if CROSSREF_MAILTO:
            params["mailto"] = CROSSREF_MAILTO
        try:
            r = requests.get(BASE_URL, params=params, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as ex:
            logging.warning(f"[crossref] fail {term}: {ex}")
            continue
        for it in data.get("message", {}).get("items", []):
            title = sanitize_text(" ".join(it.get("title", [])))
            abstr = sanitize_text(it.get("abstract", "") or (it.get("subtitle") or [""])[0])
            link = it.get("URL", "")
            if not title:
                continue
            if not english_only(title + " " + abstr):
                continue
            if not pass_hard_filters(title + " " + abstr):
                continue
            issued = it.get("issued", {}).get("date-parts", [[]])
            year = str(issued[0][0]) if issued and issued[0] else ""
            if not year:
                created = it.get("created", {}).get("date-time", "")
                year = str(year_from_date(created)) if created else ""
            venue_list = it.get("container-title", [])
            authors = []
            for a in it.get("author", []) or []:
                nm = (sanitize_text(a.get("given", "")) + " " + sanitize_text(a.get("family", ""))).strip() or sanitize_text(a.get("name", ""))
                if nm:
                    authors.append(nm)
            items.append({
                "id": it.get("DOI", link) or link,
                "title": title,
                "abstract": abstr,
                "url": link,
                "published": it.get("created", {}).get("date-time", "") or it.get("issued", {}).get("date-time", ""),
                "source": "crossref",
                "authors": authors,
                "venue": " ".join(venue_list) if venue_list else "",
                "year": year,
            })
    logging.info(f"[crossref] total={len(items)}")
    return items
