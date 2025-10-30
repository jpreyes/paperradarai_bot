# paperradar/bot/commands_misc.py
from paperradar.storage.users import forgetme as _forget, get_user, save_user
from paperradar.storage.users import clear_sent_ids_for_active_profile

def forgetme(update, context):
    cid = update.effective_chat.id
    _forget(cid)
    update.message.reply_text("🗑️ All your data for this chat has been deleted.")

def flush(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    clear_sent_ids_for_active_profile(u)
    save_user(cid)
    update.message.reply_text("🔄 sent_ids del perfil activo reiniciado.")
    
def flushall(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    for k in list(u.get("sent_ids_by_profile", {}).keys()):
        u["sent_ids_by_profile"][k] = set()
    u["sent_ids"] = set()  # legacy
    save_user(cid)
    update.message.reply_text("🧹 Reiniciados los sent_ids de todos los perfiles.")