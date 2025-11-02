# paperradar/bot/commands_llm.py
from paperradar.storage.users import get_user, save_user, add_sent_id
from paperradar.storage.history import upsert_history_record
from paperradar.services.pipeline import build_ranked, make_bullets
from .utils import argstr

def llm(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    active_profile = u.get("active_profile", "default")
    pid = (argstr(update) or "").strip()
    if not pid:
        update.message.reply_text("Usage: /llm <id> (use the ID shown under each item)"); return

    ranked = build_ranked(u)
    target = None
    for it, sc in ranked:
        key = (it.get("id") or it.get("url") or "")[:200]
        if pid in key or key in pid:
            target = (it, sc); break
    if not target:
        update.message.reply_text("ID not found in current ranking. Try /sample or ensure it has not expired."); return

    it, sc = target
    bullets = make_bullets(u, it, use_llm=True)
    from .handlers import send_paper
    send_paper(context.bot, cid, it, sc, bullets)
    upsert_history_record(cid, it, sc, bullets, note="llm_ondemand", profile=active_profile)
    add_sent_id(u, (it.get("id") or it.get("url") or "")[:200])
    save_user(cid)
