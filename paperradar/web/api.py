from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import logging
import os
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File, Form, Body
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ValidationError
import tempfile

from paperradar.config import POLL_DAILY_TIME
from paperradar.services.pipeline import build_ranked, make_bullets
from paperradar.services.profile_builder import build_profile_from_pdf, analyze_text
from paperradar.services.journal_search import recommend_journals_for_user
from paperradar.services.journal_ingest import refresh_journals_from_crossref
from paperradar.services.paper_embeddings import ensure_paper_embeddings
from paperradar.fetchers.search_terms import set_custom_terms
from paperradar.storage.history import load_history, upsert_history_record, user_history_json, user_history_csv, now_iso
from paperradar.storage.list_users import list_all_user_ids
from paperradar.storage import journals as journal_store
from paperradar.storage import email_index, magic_links, journal_analysis
from paperradar.storage.users import (
    get_user,
    save_user,
    clear_sent_ids_for_active_profile,
    create_user,
    get_web_passcode,
)
from paperradar.bot.commands_profiles import _apply_profile_analysis

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="PaperRadar API")

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _ensure_user(chat_id: int):
    if chat_id not in list_all_user_ids():
        raise HTTPException(status_code=404, detail=f"chat_id {chat_id} not found")
    state = get_user(chat_id)
    state["chat_id"] = chat_id
    return state


def _history_records(chat_id: int, profile: str | None) -> List[dict]:
    records = load_history(chat_id, profile)
    if profile:
        normalized = profile or "default"
        records = [r for r in records if (r.get("profile") or "default") == normalized]
    return records


def _history_index(chat_id: int, profile: str | None) -> Dict[str, str]:
    records = _history_records(chat_id, profile)
    out: Dict[str, str] = {}
    for rec in records:
        pid = (rec.get("id") or rec.get("url") or "")[:200]
        if pid:
            out[pid] = rec.get("ts")
    return out


def _is_liked(user_state: dict, pid: str) -> bool:
    return pid in (user_state.get("likes_global") or [])


def _is_disliked(user_state: dict, pid: str) -> bool:
    return pid in (user_state.get("dislikes_global") or [])


def _remove_profile_history(chat_id: int, profile: str) -> None:
    for path in (user_history_json(chat_id, profile), user_history_csv(chat_id, profile)):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def _build_papers_payload(chat_id: int, limit: int, offset: int, *, use_live: bool):
    user_state = _ensure_user(chat_id)
    profile_name = user_state.get("active_profile", "default")
    if not use_live:
        records = _history_records(chat_id, profile_name)
        sorted_records = sorted(records, key=lambda r: r.get("ts", ""), reverse=True)
        items: List[dict] = []
        slice_records = sorted_records[offset:offset + limit]
        for rec in slice_records:
            pk = (rec.get("id") or rec.get("url") or "")[:200]
            item = {
                "id": rec.get("id"),
                "title": rec.get("title"),
                "abstract": rec.get("abstract"),
                "url": rec.get("url"),
                "source": rec.get("source"),
                "published": rec.get("published"),
                "venue": rec.get("venue"),
                "year": rec.get("year"),
                "authors": rec.get("authors", []),
            }
            bullets = {
                "ideas": rec.get("ideas", []),
                "similarities": rec.get("similarities", []),
                "tag": rec.get("tag"),
            }
            items.append(
                {
                    "score": rec.get("score"),
                    "item": item,
                    "bullets": bullets,
                    "fetched_at": rec.get("ts"),
                    "paper_key": pk,
                    "liked": _is_liked(user_state, pk),
                    "disliked": _is_disliked(user_state, pk),
                }
            )
        return {
            "chat_id": chat_id,
            "limit": limit,
            "offset": offset,
            "total_ranked": len(records),
            "has_more": offset + limit < len(records),
            "items": items,
        }

    ranked = build_ranked(user_state)
    history_map = _history_index(chat_id, profile_name)
    llm_enabled = bool(user_state.get("llm_enabled"))
    llm_threshold = float(user_state.get("llm_threshold", 0.70) or 0.70)
    llm_budget = int(user_state.get("llm_max_per_tick", 2) or 0)
    used_llm = 0
    items: List[dict] = []
    embed_candidates: List[dict] = []
    known_keys = set(history_map.keys())
    for it, score in ranked:
        pk = (it.get("id") or it.get("url") or "")[:200]
        if not pk or pk in known_keys:
            continue
        known_keys.add(pk)
        display_slot_available = len(items) < limit
        use_llm = (
            display_slot_available
            and llm_enabled
            and llm_budget > 0
            and used_llm < llm_budget
            and score >= llm_threshold
        )
        bullets = make_bullets(user_state, it, use_llm=use_llm)
        if use_llm and bullets.get("tag") in ("llm", "llm_cache"):
            used_llm += 1
        upsert_history_record(chat_id, it, score, bullets, note="web", profile=profile_name)
        if not display_slot_available:
            continue
        fetched_ts = now_iso()
        items.append(
            {
                "score": round(score, 3),
                "item": it,
                "bullets": bullets,
                "fetched_at": fetched_ts,
                "paper_key": pk,
                "liked": _is_liked(user_state, pk),
                "disliked": _is_disliked(user_state, pk),
            }
        )
        embed_candidates.append(it)
    if embed_candidates:
        try:
            ensure_paper_embeddings(embed_candidates)
        except Exception as exc:
            logging.warning("[papers] embedding preload failed: %s", exc)
    return {
        "chat_id": chat_id,
        "limit": limit,
        "offset": 0,
        "total_ranked": len(items),
        "has_more": False,
        "items": items,
    }


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    chat_ids = list_all_user_ids()
    initial = {
        "chatIds": chat_ids,
        "defaultChatId": chat_ids[0] if chat_ids else None,
    }
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "initial_data": initial},
    )


@app.get("/users")
def users():
    out = []
    for cid in list_all_user_ids():
        state = get_user(cid)
        summary = state.get("profile_summary") or state.get("profile", "")
        topics = state.get("profile_topics", [])
        out.append(
            {
                "chat_id": cid,
                "active_profile": state.get("active_profile", "default"),
                "profile_summary": summary,
                "profile_topics": topics,
            }
        )
    return out


@app.get("/users/{chat_id}/config")
def user_config(chat_id: int):
    state = _ensure_user(chat_id)
    summary = state.get("profile_summary") or state.get("profile", "")
    return {
        "chat_id": chat_id,
        "active_profile": state.get("active_profile", "default"),
        "profiles": list(state.get("profiles", {}).keys()),
        "profile_summary": summary,
        "profile_text": state.get("profile", ""),
        "profile_topics": state.get("profile_topics", []),
        "profile_topic_weights": state.get("profile_topic_weights", {}),
        "profiles_data": state.get("profiles", {}),
        "profile_overrides": state.get("profile_overrides", {}),
        "sim_threshold": state.get("sim_threshold"),
        "topn": state.get("topn"),
        "max_age_hours": state.get("max_age_hours"),
        "poll_min": state.get("poll_min"),
        "poll_daily_time": POLL_DAILY_TIME,
        "llm_enabled": state.get("llm_enabled"),
        "llm_threshold": state.get("llm_threshold"),
        "llm_max_per_tick": state.get("llm_max_per_tick"),
        "llm_ondemand_max_per_hour": state.get("llm_ondemand_max_per_hour"),
        "last_lucky_ts": state.get("last_lucky_ts"),
        "likes_total": len(state.get("likes_global", [])),
        "dislikes_total": len(state.get("dislikes_global", [])),
    }


@app.post("/auth/magic/request")
def auth_magic_request(payload: MagicLinkRequestPayload = Body(...)):
    email = email_index.normalize_email(payload.email)
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Email invalido.")
    chat_id = email_index.get_chat_id(email)
    if chat_id is None:
        chat_id = create_user()
        email_index.set_chat_id(email, chat_id)
    pin = get_web_passcode(chat_id)
    token_payload = magic_links.create_token(email, chat_id)
    login_path = f"/auth/magic/consume?token={token_payload['token']}"
    return {
        "chat_id": chat_id,
        "token": token_payload["token"],
        "login_url": login_path,
        "expires_at": token_payload["expires_at"],
        "pin": pin,
    }


@app.get("/auth/magic/consume", response_class=HTMLResponse)
def auth_magic_consume(request: Request, token: str):
    payload = magic_links.consume_token(token)
    if not payload:
        return templates.TemplateResponse(
            "magic_login.html",
            {"request": request, "error": "Token invalido o expirado."},
        )
    return templates.TemplateResponse(
        "magic_login.html",
        {
            "request": request,
            "chat_id": payload.get("chat_id"),
            "email": payload.get("email"),
        },
    )


@app.post("/auth/pin/verify")
def auth_pin_verify(raw: dict = Body(...)):
    try:
        payload = PinVerifyPayload(**raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    chat_id = payload.chat_id
    user_state = _ensure_user(chat_id)
    expected = user_state.get("web_passcode") or get_web_passcode(chat_id)
    provided = (payload.pin or "").strip()
    if provided != expected:
        raise HTTPException(status_code=401, detail="PIN incorrecto.")
    return {"chat_id": chat_id, "status": "ok"}


class ProfileCreatePayload(BaseModel):
    name: str
    text: str | None = None
    set_active: bool = True


class ProfileSwitchPayload(BaseModel):
    profile: str


class ProfileUpdatePayload(BaseModel):
    summary: str | None = None
    topics: List[str] | None = None
    topic_weights: Dict[str, float] | None = None


class ProfileIngestPayload(BaseModel):
    profile: str | None = None
    text: str


class JournalEntryPayload(BaseModel):
    id: str | None = None
    title: str
    aims_scope: str | None = None
    publisher: str | None = None
    website: str | None = None
    country: str | None = None
    languages: List[str] | None = None
    categories: List[str] | None = None
    topics: List[str] | None = None
    keywords: List[str] | None = None
    metrics: Dict[str, float] | None = None
    speed: Dict[str, float] | None = None
    open_access: bool | None = None
    apc_usd: float | None = None
    issn_print: str | None = None
    issn_electronic: str | None = None


class JournalCatalogPayload(BaseModel):
    items: List[JournalEntryPayload]


class JournalIngestPayload(BaseModel):
    limit: int | None = None


class MagicLinkRequestPayload(BaseModel):
    email: str


class PinVerifyPayload(BaseModel):
    chat_id: int
    pin: str

PinVerifyPayload.model_rebuild()


@app.post("/users/{chat_id}/profiles")
def profile_create(chat_id: int, payload: ProfileCreatePayload):
    user_state = _ensure_user(chat_id)
    name = (payload.name or "").strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="El nombre del perfil es obligatorio.")
    if name.lower() == "default":
        raise HTTPException(status_code=400, detail="No puedes crear un perfil con ese nombre.")
    profiles = user_state.setdefault("profiles", {})
    if name in profiles:
        raise HTTPException(status_code=409, detail=f"El perfil '{name}' ya existe.")
    text = (payload.text or "").strip()
    analysis = analyze_text(text, summary_override=text) if text else None
    if analysis:
        profile_text = analysis.get("profile_text", "")
        summary = analysis.get("summary", profile_text)
        topics = analysis.get("topics", [])
        weights = analysis.get("topic_weights", {})
    else:
        profile_text = text
        summary = text
        topics = []
        weights = {}
    profiles[name] = profile_text
    user_state.setdefault("profile_overrides", {}).pop(name, None)
    if payload.set_active:
        user_state["active_profile"] = name
        user_state["profile"] = profile_text
        user_state["profile_summary"] = summary
        user_state["profile_topics"] = topics
        user_state["profile_topic_weights"] = weights
        clear_sent_ids_for_active_profile(user_state)
        set_custom_terms(topics)
    save_user(chat_id)
    return user_config(chat_id)


@app.post("/users/{chat_id}/profiles/use")
def profile_use(chat_id: int, payload: ProfileSwitchPayload):
    user_state = _ensure_user(chat_id)
    name = (payload.profile or "").strip()
    profiles = user_state.setdefault("profiles", {})
    if name not in profiles:
        raise HTTPException(status_code=404, detail=f"Perfil '{name}' no encontrado")
    user_state["active_profile"] = name
    stored = profiles.get(name, "")
    applied = _apply_profile_analysis(user_state, stored, summary_override=stored)
    profiles[name] = applied
    user_state["profile"] = applied
    clear_sent_ids_for_active_profile(user_state)
    set_custom_terms(user_state.get("profile_topics", []))
    save_user(chat_id)
    return user_config(chat_id)


@app.patch("/users/{chat_id}/profiles/{profile_name}")
def profile_update(chat_id: int, profile_name: str, payload: ProfileUpdatePayload):
    user_state = _ensure_user(chat_id)
    name = (profile_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Nombre de perfil invalido.")
    profiles = user_state.setdefault("profiles", {})
    if name not in profiles:
        raise HTTPException(status_code=404, detail=f"Perfil '{name}' no encontrado")
    if payload.summary is None and payload.topics is None and payload.topic_weights is None:
        raise HTTPException(status_code=400, detail="No se proporcionaron cambios.")

    overrides = user_state.setdefault("profile_overrides", {})
    entry = overrides.get(name, {}).copy()

    is_active = user_state.get("active_profile") == name

    if payload.summary is not None:
        summary = (payload.summary or "").strip()
        entry["summary"] = summary
        profiles[name] = summary
        if is_active:
            user_state["profile"] = summary
            user_state["profile_summary"] = summary

    topics_changed = payload.topics is not None or payload.topic_weights is not None

    if topics_changed:
        existing_topics = entry.get("topics") or []
        if not existing_topics and is_active:
            existing_topics = user_state.get("profile_topics", [])

        if payload.topics is not None:
            topics = [t.strip() for t in (payload.topics or []) if t and t.strip()]
        else:
            topics = [t for t in existing_topics if t]

        weights_payload = payload.topic_weights or {}
        existing_weights = entry.get("topic_weights") or {}
        if not existing_weights and is_active:
            existing_weights = user_state.get("profile_topic_weights", {})

        weights: Dict[str, float] = {}
        for topic in topics:
            value = weights_payload.get(topic)
            if value is None:
                value = existing_weights.get(topic)
            try:
                num = float(value)
            except (TypeError, ValueError):
                num = None
            if num is not None:
                weights[topic] = max(0.0, min(1.0, round(num, 3)))

        if not weights and topics:
            if len(topics) == 1:
                weights = {topics[0]: 1.0}
            else:
                span = max(len(topics) - 1, 1)
                weights = {
                    topic: round(1.0 - (idx / span), 3)
                    for idx, topic in enumerate(topics)
                }

        entry["topics"] = topics
        entry["topic_weights"] = weights
        if is_active:
            user_state["profile_topics"] = topics
            user_state["profile_topic_weights"] = weights
            set_custom_terms(topics)

    overrides[name] = entry

    if is_active:
        clear_sent_ids_for_active_profile(user_state)

    save_user(chat_id)
    return user_config(chat_id)


@app.delete("/users/{chat_id}/profiles/{profile_name}")
def profile_delete(chat_id: int, profile_name: str):
    user_state = _ensure_user(chat_id)
    name = (profile_name or "").strip()
    profiles = user_state.setdefault("profiles", {})
    if name not in profiles:
        raise HTTPException(status_code=404, detail=f"Perfil '{name}' no encontrado")
    if len(profiles) <= 1:
        raise HTTPException(status_code=400, detail="No puedes eliminar el unico perfil disponible.")
    del profiles[name]
    user_state.setdefault("sent_ids_by_profile", {}).pop(name, None)
    user_state.setdefault("profile_overrides", {}).pop(name, None)
    _remove_profile_history(chat_id, name)
    if user_state.get("active_profile") == name:
        new_active = next(iter(profiles.keys()))
        user_state["active_profile"] = new_active
        stored = profiles.get(new_active, "")
        applied = _apply_profile_analysis(user_state, stored, summary_override=stored)
        profiles[new_active] = applied
        user_state["profile"] = applied
        clear_sent_ids_for_active_profile(user_state)
        set_custom_terms(user_state.get("profile_topics", []))
    save_user(chat_id)
    return user_config(chat_id)


@app.post("/users/{chat_id}/profiles/ingest")
def profile_ingest_text(chat_id: int, payload: ProfileIngestPayload):
    user_state = _ensure_user(chat_id)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="El abstract es obligatorio.")
    target = (payload.profile or user_state.get("active_profile") or "default").strip() or "default"
    profiles = user_state.setdefault("profiles", {})
    if target not in profiles:
        profiles[target] = ""
    user_state["active_profile"] = target
    user_state.setdefault("profile_overrides", {}).pop(target, None)
    applied = _apply_profile_analysis(user_state, text, summary_override=text)
    profiles[target] = applied
    user_state["profile"] = applied
    clear_sent_ids_for_active_profile(user_state)
    set_custom_terms(user_state.get("profile_topics", []))
    save_user(chat_id)
    return user_config(chat_id)


class FeedbackPayload(BaseModel):
    paper_id: str
    action: str


def _toggle_feedback(user_state: dict, pid: str, action: str) -> Dict[str, bool]:
    likes = user_state.setdefault("likes_global", [])
    dislikes = user_state.setdefault("dislikes_global", [])
    liked = pid in likes
    disliked = pid in dislikes

    if action == "like":
        if liked:
            likes.remove(pid)
            liked = False
        else:
            if pid not in likes:
                likes.append(pid)
            if pid in dislikes:
                dislikes.remove(pid)
            liked = True
            disliked = False
    elif action == "dislike":
        if disliked:
            dislikes.remove(pid)
            disliked = False
        else:
            if pid not in dislikes:
                dislikes.append(pid)
            if pid in likes:
                likes.remove(pid)
            disliked = True
            liked = False
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'like' or 'dislike'.")

    return {"liked": liked, "disliked": disliked}


@app.post("/users/{chat_id}/feedback")
def user_feedback(chat_id: int, payload: FeedbackPayload):
    pid = (payload.paper_id or "").strip()[:200]
    if not pid:
        raise HTTPException(status_code=400, detail="paper_id is required")
    action = (payload.action or "").strip().lower()
    user_state = _ensure_user(chat_id)
    result = _toggle_feedback(user_state, pid, action)
    save_user(chat_id)
    return {
        "paper_id": pid,
        "liked": result["liked"],
        "disliked": result["disliked"],
        "likes_total": len(user_state.get("likes_global", [])),
        "dislikes_total": len(user_state.get("dislikes_global", [])),
    }


@app.post("/users/{chat_id}/profiles/upload")
async def profile_upload_pdf(
    chat_id: int,
    profile: str = Form(""),
    file: UploadFile = File(...),
):
    user_state = _ensure_user(chat_id)
    if not profile:
        profile = user_state.get("active_profile", "default")
    user_state.setdefault("profiles", {})
    if profile not in user_state["profiles"]:
        user_state["profiles"][profile] = ""
    user_state["active_profile"] = profile
    user_state.setdefault("profile_overrides", {}).pop(profile, None)

    if file.content_type not in ("application/pdf", "application/x-pdf"):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos PDF.")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)
        analysis = build_profile_from_pdf(tmp_path)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo procesar el PDF: {exc}") from exc
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    if not analysis:
        raise HTTPException(status_code=400, detail="No se pudo extraer texto util del PDF.")

    profile_text = analysis.get("profile_text", "") or ""
    user_state["profiles"][profile] = profile_text
    user_state["profile"] = profile_text
    user_state["profile_summary"] = analysis.get("summary", profile_text)
    user_state["profile_topics"] = analysis.get("topics", [])
    user_state["profile_topic_weights"] = analysis.get("topic_weights", {})

    clear_sent_ids_for_active_profile(user_state)
    set_custom_terms(user_state.get("profile_topics", []))
    save_user(chat_id)

    return user_config(chat_id)


@app.get("/users/{chat_id}/journals")
def user_journals(
    chat_id: int,
    limit: int = Query(9, ge=1, le=30),
    llm_top: int | None = Query(None, ge=1, le=30),
):
    user_state = _ensure_user(chat_id)
    payload = recommend_journals_for_user(user_state, limit=limit, llm_limit=llm_top)
    payload["chat_id"] = chat_id
    return payload


@app.post("/users/{chat_id}/journals/ingest")
def user_journals_ingest(chat_id: int, payload: JournalIngestPayload | None = None):
    user_state = _ensure_user(chat_id)
    limit = 25
    if payload and payload.limit:
        limit = max(5, min(60, int(payload.limit)))
    try:
        result = refresh_journals_from_crossref(user_state, limit=limit)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dedupe_stats = journal_store.dedupe_catalog()
    journal_analysis.clear_for_chat(chat_id)
    result["dedupe"] = dedupe_stats
    result["chat_id"] = chat_id
    return result


@app.get("/journals/catalog")
def journals_catalog():
    items = journal_store.load_catalog()
    return {"count": len(items), "items": items}


@app.post("/journals/catalog")
def journals_catalog_upsert(payload: JournalCatalogPayload):
    entries = [item.dict(exclude_none=True) for item in payload.items]
    catalog, updated = journal_store.upsert_entries(entries)
    return {"count": len(catalog), "updated": updated, "items": catalog}


@app.delete("/journals/catalog/{journal_id}")
def journals_catalog_delete(journal_id: str):
    if not journal_store.delete_entry(journal_id):
        raise HTTPException(status_code=404, detail="Journal no encontrado")
    return {"deleted": journal_id}


@app.post("/journals/catalog/dedupe")
def journals_catalog_dedupe():
    stats = journal_store.dedupe_catalog()
    return {"status": "ok", "removed": stats["removed"], "total": stats["total"]}


@app.get("/users/{chat_id}/papers")
def user_papers(
    chat_id: int,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    mode: str = Query("history", pattern="^(history|live)$"),
):
    use_live = mode == "live"
    return _build_papers_payload(chat_id, limit, offset, use_live=use_live)


@app.get("/sample/{chat_id}")
def sample(chat_id: int, top: int = Query(5, ge=1, le=200)):
    payload = _build_papers_payload(chat_id, top, 0, use_live=True)
    return payload["items"]
