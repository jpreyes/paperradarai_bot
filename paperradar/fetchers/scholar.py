import requests, logging
from paperradar.core.filters import english_only, sanitize_text
from paperradar.core.model import Item
from paperradar.config import SERPAPI_API_KEY

# Google Scholar no tiene API oficial. Usamos SerpAPI si se provee SERPAPI_API_KEY.

TERMS = [
    '"operational modal analysis"', 'stochastic subspace', 'system identification', 'structural health monitoring',
    'damage detection bridge', 'damage detection building', 'soil-structure interaction bridge', 'soil-structure interaction building',
]

BASE_URL = "https://serpapi.com/search.json"


def fetch(max_results=50):
    if not SERPAPI_API_KEY:
        return []
    out = []
    for term in TERMS:
        params = {
            "engine": "google_scholar",
            "q": term,
            "num": max_results,
            "hl": "en",
            "api_key": SERPAPI_API_KEY,
        }
        try:
            r = requests.get(BASE_URL, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as ex:
            logging.warning(f"[scholar] fail {term}: {ex}")
            continue
        for it in data.get("organic_results", []) or []:
            title = sanitize_text(it.get("title", ""))
            link  = sanitize_text(it.get("link", ""))
            snippet = sanitize_text(it.get("snippet", ""))
            if not title:
                continue
            if not english_only(f"{title} {snippet}"):
                continue
            year = sanitize_text(str(it.get("publication_info", {}).get("year") or ""))
            authors = []
            # scholar no expone autores limpios vía SerpAPI; dejamos vacío
            out.append(Item(
                id=link or title, title=title, abstract=snippet, url=link,
                published="", source="scholar", authors=authors, venue="", year=year
            ).__dict__)
    logging.info(f"[scholar] total={len(out)}")
    return out

