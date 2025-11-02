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
from paperradar.storage.history import user_history_json, user_history_csv


def _clear_history_files(chat_id: int, profiles: list[str] | None = None) -> None:
    targets = set()
    if profiles:
        for name in profiles:
            targets.add(user_history_json(chat_id, name))
            targets.add(user_history_csv(chat_id, name))
    # Always remove legacy/default files as well
    targets.add(user_history_json(chat_id))
    targets.add(user_history_csv(chat_id))
    for path in targets:
        if os.path.exists(path):
            try:
                os.remove(path)
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
    update.message.reply_text("All your data for this chat has been deleted.")


def flush(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    clear_sent_ids_for_active_profile(u)
    _reset_user_defaults(cid, u)
    _clear_history_files(cid, [u.get("active_profile", "default")])
    reset_terms()
    save_user(cid)
    update.message.reply_text("Perfil activo reiniciado. Historial y ajustes restablecidos.")


def flushall(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    for k in list(u.get("sent_ids_by_profile", {}).keys()):
        u["sent_ids_by_profile"][k] = set()
    u["sent_ids"] = set()  # legado
    _reset_user_defaults(cid, u)
    _clear_history_files(cid, list(u.get("profiles", {}).keys()))
    reset_terms()
    save_user(cid)
    update.message.reply_text("Todos los perfiles han sido reiniciados. Historial y ajustes restablecidos.")
