import json, logging, os, shutil
from collections import deque
from paperradar.config import (
    DEFAULT_SIM_THRESHOLD, DEFAULT_TOP_N,
    DEFAULT_MAX_AGE_HOURS, DEFAULT_POLL_INTERVAL_MIN,
    DEFAULT_LLM_THRESHOLD, DEFAULT_LLM_MAX_PER_TICK, DEFAULT_LLM_ONDEMAND_MAX_PER_HOUR,
    OPENAI_API_KEY
)
from .paths import user_path, user_dir

USERS = {}

def default_user_state(chat_id:int)->dict:
    return {
        "profiles": {"default": ""}, "active_profile": "default", "profile": "",
        "likes_global": [], "dislikes_global": [],
        "likes_by_profile": {}, "dislikes_by_profile": {},
        "sent_ids": set(),                      # legacy global
        "sent_ids_by_profile": {},              # nuevo: enviados por perfil
        "recents": deque(maxlen=500),           # solo memoria (no se serializa)
        "sim_threshold": DEFAULT_SIM_THRESHOLD,
        "last_lucky_ts": "", "topn": DEFAULT_TOP_N,
        "max_age_hours": DEFAULT_MAX_AGE_HOURS, "poll_min": DEFAULT_POLL_INTERVAL_MIN,
        "llm_enabled": True if OPENAI_API_KEY else False,
        "llm_threshold": DEFAULT_LLM_THRESHOLD, "llm_max_per_tick": DEFAULT_LLM_MAX_PER_TICK,
        "llm_ondemand_max_per_hour": DEFAULT_LLM_ONDEMAND_MAX_PER_HOUR,
        "llm_ondemand_times": [],
        "idle_ticks": 0,
    }

def _sync_active_profile_text(u:dict):
    act = u.get("active_profile","default")
    u["profile"] = u.get("profiles",{}).get(act, "")

def load_user(chat_id:int)->dict:
    meta_path = user_path(chat_id, "meta.json")
    state = default_user_state(chat_id)

    # --- meta.json ---
    if os.path.exists(meta_path):
        try:
            obj = json.load(open(meta_path,"r",encoding="utf-8"))
            state.update({
                "profiles": obj.get("profiles") or {"default": obj.get("profile","")},
                "active_profile": obj.get("active_profile","default"),
                "likes_global": obj.get("likes_global", obj.get("likes", [])),
                "dislikes_global": obj.get("dislikes_global", obj.get("dislikes", [])),
                "likes_by_profile": obj.get("likes_by_profile", {}),
                "dislikes_by_profile": obj.get("dislikes_by_profile", {}),
                "sim_threshold": obj.get("sim_threshold", state["sim_threshold"]),
                "last_lucky_ts": obj.get("last_lucky_ts",""),
                "topn": obj.get("topn", state["topn"]),
                "max_age_hours": obj.get("max_age_hours", state["max_age_hours"]),
                "poll_min": obj.get("poll_min", state["poll_min"]),
                "llm_enabled": obj.get("llm_enabled", state["llm_enabled"]),
                "llm_threshold": obj.get("llm_threshold", state["llm_threshold"]),
                "llm_max_per_tick": obj.get("llm_max_per_tick", state["llm_max_per_tick"]),
                "llm_ondemand_max_per_hour": obj.get("llm_ondemand_max_per_hour", state["llm_ondemand_max_per_hour"]),
                "llm_ondemand_times": obj.get("llm_ondemand_times", []),
                "idle_ticks": obj.get("idle_ticks", 0),
            })
            # NEW: cargar enviados por perfil (listas -> sets)
            sidp = obj.get("sent_ids_by_profile", {})
            if isinstance(sidp, dict):
                state["sent_ids_by_profile"] = {
                    k: set(v) if isinstance(v, list) else set(v or [])
                    for k, v in sidp.items()
                }
        except Exception as ex:
            logging.warning(f"[user] load {chat_id} failed: {ex}")

    # --- legacy sent_ids.json ---
    sp = user_path(chat_id,"sent_ids.json")
    if os.path.exists(sp):
        try:
            state["sent_ids"] = set(json.load(open(sp,"r",encoding="utf-8")))
        except Exception as ex:
            logging.warning(f"[user] load sent_ids {chat_id} failed: {ex}")

    _sync_active_profile_text(state)
    return state

def get_user(chat_id:int)->dict:
    if chat_id not in USERS:
        USERS[chat_id] = load_user(chat_id)
    return USERS[chat_id]

def save_user(chat_id:int):
    u = USERS.get(chat_id)
    if not u:
        return
    _sync_active_profile_text(u)

    # Serializar sent_ids_by_profile (sets -> listas)
    sidp_serializable = {
        k: sorted(list(v)) if isinstance(v, set) else (v or [])
        for k, v in u.get("sent_ids_by_profile", {}).items()
    }

    meta = {
        "profiles": u.get("profiles", {"default": ""}),
        "active_profile": u.get("active_profile","default"),
        "likes_global": u.get("likes_global",[]),
        "dislikes_global": u.get("dislikes_global",[]),
        "likes_by_profile": u.get("likes_by_profile",{}),
        "dislikes_by_profile": u.get("dislikes_by_profile",{}),
        "sim_threshold": u.get("sim_threshold"),
        "last_lucky_ts": u.get("last_lucky_ts",""),
        "topn": u.get("topn"),
        "max_age_hours": u.get("max_age_hours"),
        "poll_min": u.get("poll_min"),
        "llm_enabled": u.get("llm_enabled", True),
        "llm_threshold": u.get("llm_threshold"),
        "llm_max_per_tick": u.get("llm_max_per_tick"),
        "profile": u.get("profile",""),
        "llm_ondemand_max_per_hour": u.get("llm_ondemand_max_per_hour", DEFAULT_LLM_ONDEMAND_MAX_PER_HOUR),
        "llm_ondemand_times": u.get("llm_ondemand_times", []),
        "idle_ticks": u.get("idle_ticks", 0),
        # NEW: guardar enviados por perfil dentro de meta.json
        "sent_ids_by_profile": sidp_serializable,
    }

    # Guardar meta.json
    with open(user_path(chat_id,"meta.json"),"w",encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # Legacy: mantener sent_ids.json (por compatibilidad)
    with open(user_path(chat_id,"sent_ids.json"),"w",encoding="utf-8") as f:
        json.dump(sorted(list(u.get("sent_ids", set()))), f, ensure_ascii=False)

def forgetme(chat_id:int):
    try:
        shutil.rmtree(user_dir(chat_id))
    except Exception:
        pass
    USERS.pop(chat_id, None)

# --- Helpers para manejar sent_ids por perfil activo ----------------------------

def get_active_sent_ids(u: dict) -> set:
    prof = u.get("active_profile", "default")
    sidp = u.setdefault("sent_ids_by_profile", {})
    cur = sidp.get(prof)
    if cur is None:
        # inicializa desde legacy si existe (solo primera vez)
        legacy = u.get("sent_ids", set())
        cur = set(legacy) if isinstance(legacy, set) else set(legacy or [])
        sidp[prof] = cur
    elif not isinstance(cur, set):
        cur = set(cur)
        sidp[prof] = cur
    return cur

def add_sent_id(u: dict, item_key: str) -> None:
    get_active_sent_ids(u).add(item_key)

def clear_sent_ids_for_active_profile(u: dict) -> None:
    prof = u.get("active_profile", "default")
    u.setdefault("sent_ids_by_profile", {})[prof] = set()
