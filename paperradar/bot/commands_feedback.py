# paperradar/bot/commands_feedback.py
from paperradar.storage.users import get_user, save_user
from .utils import argstr

def like(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    pid = (argstr(update) or "")[:200]
    if not pid:
        context.bot.send_message(cid, "Usage: /like <id>"); return
    if pid not in u["likes_global"]:
        u["likes_global"].append(pid)
    if pid in u["dislikes_global"]:
        u["dislikes_global"].remove(pid)
    save_user(cid)
    context.bot.send_message(cid, f"👍 Liked {pid}")

def dislike(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    pid = (argstr(update) or "")[:200]
    if not pid:
        context.bot.send_message(cid, "Usage: /dislike <id>"); return
    if pid not in u["dislikes_global"]:
        u["dislikes_global"].append(pid)
    if pid in u["likes_global"]:
        u["likes_global"].remove(pid)
    save_user(cid)
    context.bot.send_message(cid, f"👎 Disliked {pid}")

def likes(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    arr = u.get("likes_global",[])
    if not arr: context.bot.send_message(cid, "No likes yet."); return
    context.bot.send_message(cid, "Likes:\n" + "\n".join(arr[:100]))

def dislikes(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    arr = u.get("dislikes_global",[])
    if not arr: context.bot.send_message(cid, "No dislikes yet."); return
    context.bot.send_message(cid, "Dislikes:\n" + "\n".join(arr[:100]))
