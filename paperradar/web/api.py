from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import os
from fastapi import FastAPI, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import tempfile

from paperradar.config import POLL_DAILY_TIME
from paperradar.services.pipeline import build_ranked, make_bullets
from paperradar.services.profile_builder import build_profile_from_pdf, analyze_text
from paperradar.fetchers.search_terms import set_custom_terms
from paperradar.storage.history import load_history, upsert_history_record, user_history_json, user_history_csv, now_iso
from paperradar.storage.list_users import list_all_user_ids
from paperradar.storage.users import (
    get_user,
    save_user,
    clear_sent_ids_for_active_profile,
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
    return get_user(chat_id)


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


@app.get("/profiles", response_class=HTMLResponse)
def profiles_page(request: Request):
    chat_ids = list_all_user_ids()
    initial = {
        "chatIds": chat_ids,
        "defaultChatId": chat_ids[0] if chat_ids else None,
    }
    return templates.TemplateResponse(
        "profiles.html",
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


class ProfileCreatePayload(BaseModel):
    name: str
    text: str | None = None
    set_active: bool = True


class ProfileSwitchPayload(BaseModel):
    profile: str


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
    set_custom_terms(user_state.get("profile_topics", []))
    clear_sent_ids_for_active_profile(user_state)
    set_custom_terms(user_state.get("profile_topics", []))
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
