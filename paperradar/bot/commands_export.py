# paperradar/bot/commands_export.py
import os, io, zipfile, time
from paperradar.storage.users import get_user, save_user
from paperradar.storage.paths import user_path
from paperradar.storage.history import user_history_json, user_history_csv
from paperradar.core.llm import save_llm_cache

def export(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    active = u.get("active_profile", "default")
    jpath = user_history_json(cid, active)
    if not os.path.exists(jpath):
        legacy = user_history_json(cid)
        if not os.path.exists(legacy):
            update.message.reply_text("No history to export yet."); return
        jpath = legacy
    filename = os.path.basename(jpath)
    with open(jpath, "rb") as f:
        context.bot.send_document(
            chat_id=cid,
            document=f,
            filename=filename,
            disable_content_type_detection=True,
        )

def backup(update, context):
    cid = update.effective_chat.id
    base = user_path(cid, "")
    if not os.path.exists(base):
        update.message.reply_text("No data folder yet."); return
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, files in os.walk(base):
            for fn in files:
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, base))
    buf.seek(0)
    ts = time.strftime("%Y%m%d_%H%M%S")
    context.bot.send_document(chat_id=cid, document=buf, filename=f"backup_{ts}.zip")

def clear_history(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    active = u.get("active_profile", "default")
    targets = {
        user_history_json(cid, active),
        user_history_csv(cid, active),
        user_history_json(cid),
        user_history_csv(cid),
    }
    for p in targets:
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    update.message.reply_text("🧹 Cleared history files.")

def clear_llmcache(update, context):
    save_llm_cache()  # ensure file exists at least once
    from paperradar.storage.paths import LLM_CACHE_PATH
    try:
        if os.path.exists(LLM_CACHE_PATH):
            os.remove(LLM_CACHE_PATH)
        update.message.reply_text("🧠 LLM cache cleared.")
    except Exception as e:
        update.message.reply_text(f"Error clearing cache: {e}")

def clear_likes(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u["likes_global"] = []
    save_user(cid)
    update.message.reply_text("👍 Likes cleared.")

def clear_dislikes(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u["dislikes_global"] = []
    save_user(cid)
    update.message.reply_text("👎 Dislikes cleared.")
