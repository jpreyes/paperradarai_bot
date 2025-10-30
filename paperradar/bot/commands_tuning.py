# paperradar/bot/commands_tuning.py
from paperradar.storage.users import get_user, save_user
from .utils import argstr

def tune(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    try:
        thr = float(argstr(update))
    except Exception:
        update.message.reply_text("Usage: /tune <similarity_threshold 0..1>"); return
    u["sim_threshold"] = max(0.0, min(1.0, thr))
    save_user(cid)
    update.message.reply_text(f"✅ sim_threshold = {u['sim_threshold']:.2f}")

def age(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    s = argstr(update)
    try:
        hours = int(s)
    except Exception:
        update.message.reply_text("Usage: /age <max_age_hours (0 = no filter)>"); return
    u["max_age_hours"] = max(0, hours)
    save_user(cid)
    update.message.reply_text(f"✅ max_age_hours = {u['max_age_hours']}")

def poll(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    s = argstr(update)
    try:
        mins = float(s)
    except Exception:
        update.message.reply_text("Usage: /poll <minutes>"); return
    u["poll_min"] = max(0.5, mins)
    save_user(cid)
    update.message.reply_text(f"✅ poll_min = {u['poll_min']}")

def topn(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    s = argstr(update)
    try:
        n = int(s)
    except Exception:
        update.message.reply_text("Usage: /topn <int>"); return
    u["topn"] = max(1, min(50, n))
    save_user(cid)
    update.message.reply_text(f"✅ topn = {u['topn']}")

def llmbudget(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    s = argstr(update)
    try:
        n = int(s)
    except Exception:
        update.message.reply_text("Usage: /llmbudget <max_per_tick>"); return
    u["llm_max_per_tick"] = max(0, min(20, n))
    save_user(cid)
    update.message.reply_text(f"✅ llm_max_per_tick = {u['llm_max_per_tick']}")

def llmlimit(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    s = argstr(update)
    try:
        thr = float(s)
    except Exception:
        update.message.reply_text("Usage: /llmlimit <score_threshold 0..1>"); return
    u["llm_threshold"] = max(0.0, min(1.0, thr))
    save_user(cid)
    update.message.reply_text(f"✅ llm_threshold = {u['llm_threshold']:.2f}")
