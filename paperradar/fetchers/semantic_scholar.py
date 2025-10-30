import requests, logging
from paperradar.core.filters import english_only, sanitize_text, year_from_date
from paperradar.core.model import Item
from paperradar.config import SEMANTIC_SCHOLAR_API_KEY

TERMS = [
    '"operational modal analysis"', 'stochastic subspace', 'system identification', 'structural health monitoring',
    'damage detection bridge', 'damage detection building', 'soil-structure interaction bridge', 'soil-structure interaction building',
    'seismic bridge modal', 'seismic building modal'
]

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"


def fetch(max_results=60):
    if not SEMANTIC_SCHOLAR_API_KEY:
        return []
    headers = {"x-api-key": SEMANTIC_SCHOLAR_API_KEY}
    fields = "title,abstract,year,publicationDate,venue,url,authors"
    out = []
    for term in TERMS:
        params = {"query": term, "limit": max_results, "fields": fields, "offset": 0}
        try:
            r = requests.get(BASE_URL, headers=headers, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as ex:
            logging.warning(f"[semantic] fail {term}: {ex}")
            continue
        for it in data.get("data", []) or []:
            title = sanitize_text(it.get("title", ""))
            abstr = sanitize_text(it.get("abstract", ""))
            if not title:
                continue
            if not english_only(f"{title} {abstr}"):
                continue
            url = sanitize_text(it.get("url", ""))
            year = str(it.get("year") or "")
            published = sanitize_text(it.get("publicationDate", ""))
            if not year and published:
                year = str(year_from_date(published))
            authors = []
            for a in it.get("authors", []) or []:
                nm = sanitize_text(a.get("name", ""))
                if nm:
                    authors.append(nm)
            out.append(Item(
                id=url or title, title=title, abstract=abstr, url=url,
                published=published, source="semantic", authors=authors,
                venue=sanitize_text(it.get("venue", "")), year=year
            ).__dict__)
    logging.info(f"[semantic] total={len(out)}")
    return out

