from __future__ import annotations

import hashlib
import json
import logging
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Sequence, Tuple

import numpy as np
import requests

from paperradar.config import (
    DEFAULT_JOURNAL_LLM_TOP,
    DEFAULT_JOURNAL_TOPN,
    LLM_MODEL,
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
)
from paperradar.services.embeddings import EmbeddingError, embed_text
from paperradar.storage import journals as journal_store
from paperradar.storage import journal_analysis


LLM_MAX_RETRIES = 3
LLM_BACKOFF_BASE = 0.9
LLM_BACKOFF_JITTER = (0.0, 0.5)


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _listify(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        items = value
    else:
        if isinstance(value, str):
            items = re.split(r"[,\n;]+", value)
        else:
            items = [value]
    cleaned = []
    for item in items:
        text = str(item or "").strip()
        if text:
            cleaned.append(text)
    return cleaned


def _topic_overlap(user_topics: Sequence[str], journal_topics: Sequence[str]) -> Tuple[float, List[str]]:
    user_set = {t.lower() for t in _listify(user_topics)}
    jour_set = {t.lower() for t in _listify(journal_topics)}
    if not user_set or not jour_set:
        return 0.0, []
    overlap = sorted(user_set.intersection(jour_set))
    ratio = len(overlap) / max(1, min(len(user_set), len(jour_set)))
    return min(1.0, ratio), overlap


def _journal_text(record: Dict[str, object]) -> str:
    parts = [
        record.get("title") or record.get("name") or "",
        record.get("aims_scope") or "",
        ", ".join(_listify(record.get("topics"))) or "",
        ", ".join(_listify(record.get("categories"))) or "",
        record.get("publisher") or "",
        record.get("country") or "",
        f"Open access: {record.get('open_access')}" if "open_access" in record else "",
    ]
    metrics = record.get("metrics") or {}
    if isinstance(metrics, dict) and metrics:
        metric_str = ", ".join(f"{k}:{v}" for k, v in metrics.items())
        parts.append(f"Metrics: {metric_str}")
    return "\n".join(p for p in parts if p).strip()


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a is None or b is None:
        return 0.0
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _affinity_score(sim: float, topic_ratio: float) -> float:
    return float(sim + 0.25 * topic_ratio)


def _heuristic_analysis(
    summary: str,
    topics: Sequence[str],
    journal: Dict[str, object],
    overlap_terms: Sequence[str],
) -> Dict[str, object]:
    reasons = []
    if overlap_terms:
        reasons.append(f"Coincide con tus temas: {', '.join(overlap_terms[:3])}.")
    aims = journal.get("aims_scope") or ""
    if aims:
        reasons.append(aims[:200] + ("..." if len(aims) > 200 else ""))
    if journal.get("open_access"):
        reasons.append("Ofrece opciones de acceso abierto.")
    metrics = journal.get("metrics") or {}
    if metrics.get("impact_factor"):
        reasons.append(f"Impact factor aprox.: {metrics['impact_factor']}.")
    risks = []
    apc = journal.get("apc_usd")
    if apc:
        risks.append(f"Tiene APC estimado en USD {apc}.")
    speed = (journal.get("speed") or {}).get("avg_weeks_to_decision")
    if speed:
        risks.append(f"Tiempo promedio de decision: {speed} semanas.")
    return {
        "fit_summary": f"La revista {journal.get('title')} comparte el mismo enfoque tematico principal.",
        "reasons": reasons[:3] or ["Enfoque complementario a tus intereses declarados."],
        "risks": risks[:3],
        "fit_score": min(1.0, 0.55 + 0.1 * len(overlap_terms)),
        "tag": "heur",
    }


def _llm_analysis(summary: str, topics: Sequence[str], journal: Dict[str, object]) -> Dict[str, object]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY requerido para analisis de journals.")
    topics_str = ", ".join(_listify(topics)) or "n/a"
    context = _journal_text(journal)
    prompt = f"""Eres un asesor editorial experto en matching de journals.
Analiza el ajuste entre el siguiente perfil de investigacion y la revista indicada.
Devuelve un JSON con:
- fit_summary: 1 frase (<=280 caracteres) explicando el encaje.
- reasons: arreglo con hasta 3 bullets cortos justificando por que publicar alli.
- risks: arreglo con hasta 3 posibles obstaculos (formato, APC, cobertura, tiempos).
- fit_score: numero entre 0 y 1 (3 decimales) que mida el encaje global.

Perfil:
{summary.strip()}
Temas clave: {topics_str}

Revista (datos):
{context}
"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": LLM_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.25,
        "response_format": {"type": "json_object"},
    }
    last_error = None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                data=json.dumps(body),
                timeout=40,
            )
            if resp.status_code == 429 or resp.status_code >= 500:
                raise RuntimeError(f"{resp.status_code} {resp.text[:120]}")
            resp.raise_for_status()
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
            reasons = parsed.get("reasons") or []
            risks = parsed.get("risks") or []
            result = {
                "fit_summary": (parsed.get("fit_summary") or "").strip()[:280],
                "reasons": [str(r).strip() for r in reasons if str(r).strip()][:3],
                "risks": [str(r).strip() for r in risks if str(r).strip()][:3],
                "fit_score": float(parsed.get("fit_score") or 0.0),
                "tag": "llm",
            }
            return result
        except Exception as exc:
            last_error = exc
            delay = LLM_BACKOFF_BASE * (2**attempt) + random.uniform(*LLM_BACKOFF_JITTER)
            time.sleep(delay)
    raise RuntimeError(str(last_error))


def _analysis_dispatch(
    profile_summary: str,
    topics: Sequence[str],
    journal: Dict[str, object],
    overlap_terms: Sequence[str],
    allow_llm: bool,
) -> Dict[str, object]:
    try:
        if allow_llm:
            return _llm_analysis(profile_summary, topics, journal)
    except Exception as exc:
        logging.warning("[journals] LLM analysis failed: %s", exc)
    return _heuristic_analysis(profile_summary, topics, journal, overlap_terms)


def recommend_journals_for_user(
    user_state: Dict[str, object],
    *,
    limit: int | None = None,
    llm_limit: int | None = None,
) -> Dict[str, object]:
    catalog = journal_store.load_catalog()
    summary = (user_state.get("profile_summary") or user_state.get("profile") or "").strip()
    topics = user_state.get("profile_topics") or []
    if not catalog or not summary:
        return {
            "items": [],
            "catalog_size": len(catalog),
            "evaluated": 0,
            "limit": limit or DEFAULT_JOURNAL_TOPN,
            "generated_at": _now_iso(),
            "embedding_model": OPENAI_EMBEDDING_MODEL,
            "used_embeddings": False,
            "llm_enabled": bool(user_state.get("llm_enabled")),
        }

    limit = limit or DEFAULT_JOURNAL_TOPN
    llm_limit = llm_limit or DEFAULT_JOURNAL_LLM_TOP

    store = journal_store.load_embedding_store()
    store_items = store.setdefault("items", {})
    embedding_model = store.get("model") or OPENAI_EMBEDDING_MODEL
    profile_vector = None
    used_embeddings = False
    try:
        profile_raw = embed_text(summary, model=embedding_model)
        profile_vector = np.array(profile_raw, dtype=float)
        if np.linalg.norm(profile_vector) > 0:
            used_embeddings = True
    except EmbeddingError as exc:
        logging.warning("[journals] profile embedding skipped: %s", exc)
        profile_vector = None

    vectors: Dict[str, np.ndarray] = {}
    dirty_store = False
    for record in catalog:
        jid = journal_store.journal_identifier(record)
        payload = store_items.get(jid)
        text = _journal_text(record)
        fingerprint = hashlib.sha1((text + embedding_model).encode("utf-8")).hexdigest()
        vector_list = None
        if payload and payload.get("fingerprint") == fingerprint and payload.get("model") == embedding_model:
            vector_list = payload.get("vector")
        elif used_embeddings:
            try:
                vector_list = embed_text(text, model=embedding_model)
                store_items[jid] = {
                    "vector": vector_list,
                    "fingerprint": fingerprint,
                    "model": embedding_model,
                    "updated_at": _now_iso(),
                }
                dirty_store = True
            except EmbeddingError as exc:
                logging.warning("[journals] journal embedding failed (%s): %s", jid, exc)
        if vector_list:
            vectors[jid] = np.array(vector_list, dtype=float)

    scored = []
    for record in catalog:
        jid = journal_store.journal_identifier(record)
        journal_vector = vectors.get(jid)
        similarity = _cosine(profile_vector, journal_vector)
        overlap_ratio, overlap_terms = _topic_overlap(topics, record.get("topics") or record.get("keywords") or [])
        score = _affinity_score(similarity, overlap_ratio)
        scored.append(
            {
                "journal_id": jid,
                "journal": record,
                "vector_used": journal_vector is not None and profile_vector is not None,
                "similarity": similarity,
                "topic_overlap": overlap_ratio,
                "overlap_terms": overlap_terms,
                "score": score,
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    top_items = scored[:limit]
    llm_enabled = bool(user_state.get("llm_enabled"))
    chat_id = user_state.get("chat_id")
    results = []
    for idx, item in enumerate(top_items):
        allow_llm = llm_enabled and idx < llm_limit
        cache_hit = None
        if chat_id is not None:
            cache_hit = journal_analysis.get_analysis(chat_id, item["journal_id"])
        if cache_hit:
            analysis = cache_hit
        else:
            analysis = _analysis_dispatch(
                summary,
                topics,
                item["journal"],
                item["overlap_terms"],
                allow_llm=allow_llm,
            )
            if chat_id is not None:
                journal_analysis.set_analysis(chat_id, item["journal_id"], analysis)
        results.append(
            {
                "rank": idx + 1,
                "score": item["score"],
                "similarity": item["similarity"],
                "topic_overlap": item["topic_overlap"],
                "journal_id": item["journal_id"],
                "journal": item["journal"],
                "analysis": analysis,
                "vector_used": item["vector_used"],
            }
        )

    if dirty_store:
        journal_store.save_embedding_store(store)

    return {
        "items": results,
        "catalog_size": len(catalog),
        "evaluated": len(scored),
        "limit": limit,
        "generated_at": _now_iso(),
        "embedding_model": embedding_model,
        "used_embeddings": used_embeddings,
        "llm_enabled": llm_enabled,
    }
