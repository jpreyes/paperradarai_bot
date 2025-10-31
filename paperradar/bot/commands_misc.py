# paperradar/bot/commands_misc.py
import os
from paperradar.fetchers.search_terms import reset_terms
from paperradar.storage.users import (
    forgetme as _forget,
    get_user,
    save_user,
    clear_sent_ids_for_active_profile,
    default_user_state,
)
from paperradar.storage.paths import user_path


def _clear_history_files(chat_id: int) -> None:
    for fn in ("history.json", "history.csv"):
        p = user_path(chat_id, fn)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass


def _reset_user_defaults(chat_id: int, u: dict) -> None:
    defaults = default_user_state(chat_id)
    for key in (
        "sim_threshold",
        "topn",
        "max_age_hours",
        "poll_min",
        "llm_enabled",
        "llm_threshold",
        "llm_max_per_tick",
        "llm_ondemand_max_per_hour",
        "llm_ondemand_times",
        "idle_ticks",
        "profile_summary",
        "profile_topics",
        "profile_topic_weights",
    ):
        u[key] = defaults.get(key)

def forgetme(update, context):
    cid = update.effective_chat.id
    _forget(cid)
    update.message.reply_text("🗑️ All your data for this chat has been deleted.")

def flush(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    clear_sent_ids_for_active_profile(u)
    _reset_user_defaults(cid, u)
    _clear_history_files(cid)
    reset_terms()
    save_user(cid)
    update.message.reply_text("🔄 Perfil activo reiniciado, historial borrado y valores restablecidos.")
    
def flushall(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    for k in list(u.get("sent_ids_by_profile", {}).keys()):
        u["sent_ids_by_profile"][k] = set()
    u["sent_ids"] = set()  # legacy
    _reset_user_defaults(cid, u)
    _clear_history_files(cid)
    reset_terms()
    save_user(cid)
    update.message.reply_text("🧹 Reiniciados todos los perfiles, historial borrado y valores restablecidos.")
