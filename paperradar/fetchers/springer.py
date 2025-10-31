import requests, logging
from paperradar.core.filters import english_only, sanitize_text, year_from_date
from paperradar.core.model import Item
from paperradar.config import SPRINGER_API_KEY

TERMS = [
    '"operational modal analysis"', 'stochastic subspace', 'system identification', 'structural health monitoring',
    'damage detection bridge', 'damage detection building',
    'soil-structure interaction bridge', 'soil-structure interaction building',
]

BASE_URL = "https://api.springernature.com/metadata/json"
_disabled_for_session = False


def fetch(max_results=60):
    global _disabled_for_session
    if not SPRINGER_API_KEY or _disabled_for_session:
        return []
    out = []
    for term in TERMS:
        params = {
            "q": term,
            "p": max_results,
            "api_key": SPRINGER_API_KEY,
            "httpAccept": "application/json",
        }
        try:
            r = requests.get(BASE_URL, params=params, timeout=20)
            if r.status_code == 401:
                logging.error(
                    "[springer] API key rejected (401 Unauthorized). "
                    "Verifica SPRINGER_API_KEY o desactiva ENABLE_SPRINGER."
                )
                _disabled_for_session = True
                return []
            r.raise_for_status()
            data = r.json()
        except Exception as ex:
            logging.warning(f"[springer] fail {term}: {ex}")
            continue
        for rec in data.get("records", []) or []:
            title = sanitize_text(rec.get("title", ""))
            abstr = sanitize_text(rec.get("abstract", ""))
            if not title:
                continue
            if not english_only(f"{title} {abstr}"):
                continue
            url = ""
            for l in rec.get("url", []) or []:
                if l.get("format") == "html":
                    url = sanitize_text(l.get("value", "")); break
            pub = sanitize_text(rec.get("publicationDate", "")) or sanitize_text(rec.get("onlineDate", ""))
            venue = sanitize_text(rec.get("publicationName", ""))
            year = str(year_from_date(pub)) if pub else sanitize_text(rec.get("publicationYear", ""))
            authors = []
            for c in rec.get("creators", []) or []:
                nm = sanitize_text(c.get("creator", ""))
                if nm:
                    authors.append(nm)
            out.append(Item(
                id=url or title, title=title, abstract=abstr, url=url,
                published=pub, source="springer", authors=authors, venue=venue, year=year
            ).__dict__)
    logging.info(f"[springer] total={len(out)}")
    return out
