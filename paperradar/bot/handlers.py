from telegram import ParseMode
from paperradar.storage.users import get_user, save_user
from paperradar.storage.known_chats import register_chat
from paperradar.services.pipeline import build_ranked, make_bullets
from paperradar.storage.history import upsert_history_record

def send_text(bot, cid, text): bot.send_message(chat_id=cid, text=text)

def send_paper(bot, cid:int, it:dict, score:float, bullets:dict):
    def short_id(full_id:str)->str:
        import re
        if not full_id: return ""
        s = re.sub(r"^https?://","", full_id)
        return s[:48]+"…" if len(s)>48 else s
    title, url = it["title"], it["url"]
    venue  = it.get("venue","") or ""
    year   = it.get("year","")
    authors = ", ".join(it.get("authors",[])[:6]) + (" et al." if len(it.get("authors",[]))>6 else "")
    pid = short_id(it.get("id","") or it.get("url",""))
    tag_raw = bullets.get("tag","")
    tag = "[LLM]" if tag_raw in ("llm","llm_cache") else ("[LLM-FAIL]" if tag_raw=="llm_fail" else "[HEUR]")
    meta=[]
    if venue or year: meta.append(f"_Venue:_ {venue} ({year})" if venue and year else f"_Venue:_ {venue}" if venue else f"_Year:_ {year}")
    if authors: meta.append(f"_Authors:_ {authors}")
    sim_bul = "\n".join(f"• {b}" for b in bullets.get("similarities",[]) or ["—"])
    idea_bul= "\n".join(f"• {b}" for b in bullets.get("ideas",[]) or ["—"])
    msg = (f"{tag} *{title}*\nSimilarity: *{score:.2f}*\n{url}\n\n"
           f"_ID:_ `{pid}`\n" + ("\n".join(meta)+"\n\n" if meta else "") +
           f"*Similarities*\n{sim_bul}\n\n*Ideas*\n{idea_bul}\n\n"
           f"_Tip:_ /like <id>  ·  /dislike <id>  ·  /llm <id>")
    bot.send_message(chat_id=cid, text=msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=False)

def sample(update, context):
    cid = update.effective_chat.id
    register_chat(cid)
    u = get_user(cid)
    ranked = build_ranked(u)[:u.get("topn",12)]
    sent=0
    for it, sc in ranked:
        if sc < u.get("sim_threshold",0.55): continue
        bullets = make_bullets(u, it, use_llm=False)
        send_paper(context.bot, cid, it, sc, bullets)
        upsert_history_record(cid, it, sc, bullets, note="sample")
        u["sent_ids"].add((it.get("id") or it.get("url") or "")[:200]); sent+=1
    save_user(cid)
    if sent==0: send_text(context.bot, cid, "No sample above threshold. Try lowering /tune or /topn.")
