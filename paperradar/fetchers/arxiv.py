import urllib.parse, xml.etree.ElementTree as ET, requests, logging
from paperradar.core.model import Item
from paperradar.core.filters import english_only, sanitize_text, year_from_date
from paperradar.fetchers.search_terms import get_search_terms, DEFAULT_TERMS


def pass_hard_filters(blob: str) -> bool:
    bad = ["call for papers"]
    lb = blob.lower()
    return not any(b in lb for b in bad)


NS = {"a": "http://www.w3.org/2005/Atom", "ar": "http://arxiv.org/schemas/atom"}

_BASE_QUERIES = [
    '("operational modal analysis" OR OMA OR "stochastic subspace" OR SSI-Data OR FDD OR EFDD OR "Bayesian OMA") AND (bridge OR building OR "reinforced concrete" OR masonry OR "steel girder" OR "cable-stayed")',
    '(SHM OR "structural health monitoring" OR "damage detection") AND (bridge OR building OR "reinforced concrete" OR masonry) AND (OMA OR modal)',
    '("system identification" OR SSI OR "subspace identification" OR "random decrement" OR "ARX" OR "ARMA") AND (bridge OR building OR "reinforced concrete" OR masonry)',
    '("soil-structure interaction" OR SSI OR "foundation flexibility") AND (modal OR dynamic OR OMA) AND (bridge OR building)',
    '(earthquake OR seismic OR "ground motion") AND (bridge OR building OR "reinforced concrete" OR masonry) AND (OMA OR modal OR SHM)',
]

_MAX_DYNAMIC_TERMS = 20


def _iter_queries():
    seen = set()
    for base in _BASE_QUERIES:
        q = base.strip()
        if not q:
            continue
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        yield q
    dynamic = (get_search_terms() or list(DEFAULT_TERMS))[:_MAX_DYNAMIC_TERMS]
    for term in dynamic:
        expr = str(term or "").strip()
        if not expr:
            continue
        if not (expr.startswith("(") and expr.endswith(")")):
            expr = f"({expr})"
        key = expr.lower()
        if key in seen:
            continue
        seen.add(key)
        yield expr


def fetch(max_results=100):
    items = []
    queries = list(_iter_queries())
    logging.debug(f"[arXiv] using {len(queries)} search terms")
    for q in queries:
        url = (
            "https://export.arxiv.org/api/query?"
            f"search_query=all:{urllib.parse.quote(q)}&start=0&max_results={max_results}"
            "&sortBy=submittedDate&sortOrder=descending"
        )
        try:
            r = requests.get(url, timeout=20)
            r.raise_for_status()
            root = ET.fromstring(r.text)
        except Exception as ex:
            logging.warning(f"[arXiv] fail {q[:40]}... -> {ex}")
            continue
        for entry in root.findall("a:entry", NS):
            title = sanitize_text(entry.findtext("a:title", default="", namespaces=NS))
            summary = sanitize_text(entry.findtext("a:summary", default="", namespaces=NS))
            blob = f"{title} {summary}"
            if not english_only(blob):
                continue
            if not pass_hard_filters(blob):
                continue
            link = ""
            for l in entry.findall("a:link", NS):
                if l.get("type") == "text/html":
                    link = l.get("href")
                    break
            published = sanitize_text(entry.findtext("a:published", default="", namespaces=NS))
            authors = [
                sanitize_text(a.findtext("a:name", default="", namespaces=NS))
                for a in entry.findall("a:author", NS)
            ]
            journal_ref = sanitize_text(entry.findtext("ar:journal_ref", default="", namespaces=NS))
            items.append(Item(
                id=sanitize_text(entry.findtext("a:id", default="", namespaces=NS)) or link,
                title=title,
                abstract=summary,
                url=link or sanitize_text(entry.findtext("a:id", default="", namespaces=NS)),
                published=published,
                source="arxiv",
                authors=[x for x in authors if x],
                venue=journal_ref,
                year=str(year_from_date(published)) if published else "",
            ).__dict__)
    logging.info(f"[arXiv] total_filtered={len(items)}")
    return items
