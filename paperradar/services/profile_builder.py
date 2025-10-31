# paperradar/services/profile_builder.py
import json
import logging
import os
import re
from typing import Dict, List, Optional

import numpy as np
import requests
from pypdf import PdfReader
from sklearn.feature_extraction.text import TfidfVectorizer
from paperradar.config import OPENAI_API_KEY, LLM_MODEL


_STOPWORDS = {
    # English
    "the", "and", "for", "with", "that", "this", "from", "your", "about", "such",
    "have", "their", "which", "will", "into", "within", "using", "across", "more",
    "through", "these", "those", "they", "between", "among", "based", "also",
    "other", "than", "each", "been", "being", "over", "most", "many", "some",
    "where", "when", "s", "t", "we", "our", "has", "had", "can", "could", "may",
    "might", "should", "would", "using", "used", "use", "via", "while", "such",
    # Spanish
    "los", "las", "una", "uno", "del", "por", "para", "con", "como", "sobre",
    "entre", "esta", "este", "estas", "estos", "muy", "mas", "más", "sin",
    "tras", "pero", "tambien", "también", "donde", "cuando", "asi", "así",
    "segun", "según", "cada", "todo", "toda", "todos", "todas", "desde",
    "porque", "puede", "pueden", "puede", "pueden", "según",
}


def _clean_text(text: str, max_chars: int = 20000) -> str:
    base = (text or "").strip()
    if not base:
        return ""
    base = re.sub(r"\s+", " ", base)
    if len(base) > max_chars:
        base = base[:max_chars]
    return base


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p and len(p.strip()) > 0]


def _summarize(text: str, max_sentences: int = 3, max_chars: int = 600) -> str:
    sentences = _split_sentences(text)
    if not sentences:
        return text[:max_chars]
    chosen = []
    for s in sentences:
        if len(chosen) >= max_sentences:
            break
        if len(s) < 40 and len(sentences) > 1:
            continue
        chosen.append(s)
    if not chosen:
        chosen = sentences[:max_sentences]
    summary = " ".join(chosen)
    if len(summary) > max_chars:
        summary = summary[:max_chars]
        if "." in summary:
            summary = summary.rsplit(".", 1)[0] + "."
    return summary


def _extract_keywords(text: str, max_terms: int = 15) -> (List[str], Dict[str, float]):
    if not text:
        return [], {}
    try:
        vectorizer = TfidfVectorizer(
            stop_words=list(_STOPWORDS),
            lowercase=True,
            ngram_range=(1, 2),
            max_features=1000,
            min_df=1,
        )
        X = vectorizer.fit_transform([text])
        if X.nnz == 0:
            return [], {}
        scores = X.toarray()[0]
        features = vectorizer.get_feature_names_out()
        order = np.argsort(scores)[::-1]
        keywords = []
        weights: Dict[str, float] = {}
        for idx in order:
            term = features[idx]
            if len(term) < 4:
                continue
            if any(ch.isdigit() for ch in term):
                continue
            weight = float(scores[idx])
            keywords.append(term)
            weights[term] = round(weight, 6)
            if len(keywords) >= max_terms:
                break
        return keywords, weights
    except Exception as ex:
        logging.warning(f"[profile] keyword extraction failed: {ex}")
        return [], {}


def _llm_profile_analysis(text: str, max_terms: int = 15) -> Optional[Dict[str, object]]:
    if not OPENAI_API_KEY:
        return None
    snippet = text.strip()
    if not snippet:
        return None
    if len(snippet) > 20000:
        snippet = snippet[:20000]
    prompt = f"""You analyze research documents to build user profiles for recommendation systems.
Read the following text and produce a JSON object with:
- summary: 2-3 sentences summarizing the document (keep under 550 characters).
- topics: an array (max {max_terms}) of short keyword phrases (2-5 words) capturing the main themes.
- topic_weights: an object mapping each topic to a relevance score between 0.0 and 1.0 (at most 3 decimals, higher means more relevant).
Use the same language as the input text. If the text is too short or noisy, still return a best-effort summary and topics.

TEXT:
\"\"\"{snippet}\"\"\""""
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.15,
        "response_format": {"type": "json_object"},
    }
    try:
        resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, data=json.dumps(body), timeout=45)
        resp.raise_for_status()
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        summary = (parsed.get("summary") or "").strip()
        topics = parsed.get("topics") or []
        topic_weights = parsed.get("topic_weights") or {}
        if isinstance(topics, list):
            topics = [str(t).strip() for t in topics if str(t).strip()]
        else:
            topics = []
        if isinstance(topic_weights, dict):
            cleaned_weights = {}
            for key, val in topic_weights.items():
                try:
                    cleaned_weights[str(key).strip()] = float(val)
                except Exception:
                    continue
            topic_weights = cleaned_weights
        else:
            topic_weights = {}
        if not summary and snippet:
            summary = snippet[:550]
        return {
            "summary": summary,
            "topics": topics[:max_terms],
            "topic_weights": {k: round(min(max(v, 0.0), 1.0), 3) for k, v in topic_weights.items() if k},
        }
    except Exception as ex:
        logging.warning(f"[profile] LLM analysis failed: {ex}")
        return None


def analyze_text(
    text: str,
    *,
    summary_override: Optional[str] = None,
    max_terms: int = 15,
) -> Optional[Dict[str, object]]:
    cleaned = _clean_text(text)
    if not cleaned:
        return None
    llm = _llm_profile_analysis(cleaned, max_terms=max_terms)
    if llm:
        summary = llm.get("summary", "")
        topics = llm.get("topics", [])
        weights = llm.get("topic_weights", {})
        if not weights and topics:
            weights = {t: round(1.0 - (idx / max(len(topics), 1)), 3) for idx, t in enumerate(topics[:max_terms])}
    else:
        summary = _summarize(cleaned)
        topics, weights = _extract_keywords(cleaned, max_terms=max_terms)
    chosen_summary = summary_override.strip() if summary_override else summary
    summary_lower = chosen_summary.lower()
    profile_text = chosen_summary
    if topics and "key topics:" not in summary_lower:
        profile_text = f"{chosen_summary}\n\nKey topics: {', '.join(topics[:10])}"
    return {
        "raw_text": cleaned,
        "summary": chosen_summary,
        "topics": topics,
        "topic_weights": weights,
        "profile_text": profile_text,
    }


def build_profile_from_pdf(path: str, *, max_terms: int = 15) -> Optional[Dict[str, object]]:
    if not path or not os.path.exists(path):
        return None
    try:
        reader = PdfReader(path)
        pages = []
        for page in reader.pages:
            try:
                txt = page.extract_text() or ""
            except Exception:
                txt = ""
            if txt:
                pages.append(txt)
        text = "\n".join(pages)
    except Exception as ex:
        logging.warning(f"[profile] failed to read PDF {path}: {ex}")
        return None
    return analyze_text(text, max_terms=max_terms)
