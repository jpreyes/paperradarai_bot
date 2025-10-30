from .arxiv import fetch as fetch_arxiv
from .crossref import fetch as fetch_crossref
from .semantic_scholar import fetch as fetch_semantic
from .springer import fetch as fetch_springer
from .scholar import fetch as fetch_scholar
from paperradar.config import (
    MAX_ARXIV_RESULTS,
    MAX_CROSSREF_RESULTS,
    MAX_SEMANTIC_SCHOLAR_RESULTS,
    MAX_SPRINGER_RESULTS,
    MAX_SCHOLAR_RESULTS,
    ENABLE_ARXIV,
    ENABLE_CROSSREF,
    ENABLE_SEMANTIC,
    ENABLE_SPRINGER,
    ENABLE_SCHOLAR,
)


def fetch_entries():
    sources = []
    if ENABLE_ARXIV:
        sources.append(("arxiv", lambda: fetch_arxiv(MAX_ARXIV_RESULTS)))
    if ENABLE_CROSSREF:
        sources.append(("crossref", lambda: fetch_crossref(MAX_CROSSREF_RESULTS)))
    if ENABLE_SEMANTIC:
        sources.append(("semantic", lambda: fetch_semantic(MAX_SEMANTIC_SCHOLAR_RESULTS)))
    if ENABLE_SPRINGER:
        sources.append(("springer", lambda: fetch_springer(MAX_SPRINGER_RESULTS)))
    if ENABLE_SCHOLAR:
        sources.append(("scholar", lambda: fetch_scholar(MAX_SCHOLAR_RESULTS)))

    items = []
    for name, fn in sources:
        try:
            cur = fn() or []
        except Exception:
            cur = []
        items.extend(cur)
    return _merge_multi(items)


def _merge_multi(items):
    def key(it):
        pid = (it.get("id") or it.get("url") or "")
        if not pid:
            base = (it.get("title", "") + it.get("abstract", ""))[:400]
            import hashlib
            pid = hashlib.sha1(base.encode("utf-8", "ignore")).hexdigest()
        return pid[:200]

    seen = set()
    out = []
    for it in items:
        k = key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out
