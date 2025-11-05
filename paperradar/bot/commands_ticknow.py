from paperradar.storage.users import get_user, save_user, get_active_sent_ids, add_sent_id
from paperradar.storage.known_chats import register_chat
from paperradar.services.pipeline import build_ranked, make_bullets
from paperradar.storage.history import upsert_history_record

def ticknow(update, context):
    cid = update.effective_chat.id
    register_chat(cid)
    u = get_user(cid)

    active_profile = u.get("active_profile", "default")
    ranked_full = build_ranked(u)
    llm_budget = int(u.get("llm_max_per_tick", 2))
    used_llm = 0
    sent = 0
    topN = int(u.get("topn", 12))
    thr  = float(u.get("sim_threshold", 0.55))

    already = get_active_sent_ids(u)
    for it, sc in ranked_full:
        if sent >= topN or sc < thr:
            continue
        pk = (it.get("id") or it.get("url") or "")[:200]
        if pk in already:  # evita duplicar
            continue

        use_llm = u.get("llm_enabled", False) and used_llm < llm_budget and sc >= u.get("llm_threshold", 0.70)
        bullets = make_bullets(u, it, use_llm=use_llm)
        if bullets.get("tag") in ("llm", "llm_cache"):
            used_llm += 1

        # Reutiliza el render del paper
        from .handlers import send_paper
        send_paper(context.bot, cid, it, sc, bullets)

        add_sent_id(u, pk)
        already.add(pk)
        upsert_history_record(cid, it, sc, bullets, note="ticknow", profile=active_profile)
        sent += 1

    save_user(cid)
    if sent == 0:
        context.bot.send_message(chat_id=cid, text="ticknow: no hay items ≥ umbral. Ajusta /tune o /topn, o usa /flush.")
