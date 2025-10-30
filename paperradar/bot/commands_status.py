# paperradar/bot/commands_status.py
import datetime
from html import escape
from telegram import ParseMode

from paperradar.storage.users import get_user, get_active_sent_ids

def _yesno(v):
    return "✅ ON" if v else "❌ OFF"

def _pick_tick_job(job_queue):
    """
    Intenta encontrar el job del tick:
    1) por nombre "tick"
    2) por callback == scheduler.tick (por si el nombre no está disponible)
    """
    # 1) por nombre
    try:
        jobs = job_queue.get_jobs_by_name("tick") or []
        if jobs:
            return jobs[0]
    except Exception:
        pass

    # 2) por callback
    try:
        from paperradar.bot.scheduler import tick as tick_cb
        all_jobs = getattr(job_queue, "jobs", lambda: [])()
        for j in all_jobs:
            cb = getattr(j, "callback", None)
            if cb is tick_cb:
                return j
    except Exception:
        pass
    return None

def status(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)

    act = u.get("active_profile", "default")
    profiles = u.get("profiles", {})
    prof_txt = u.get("profile", "") or "(empty)"
    prof_txt_safe = escape(prof_txt[:180]) + ("..." if len(prof_txt) > 180 else "")
    thr = float(u.get("sim_threshold", 0.55))
    topn = int(u.get("topn", 12))
    max_age = int(u.get("max_age_hours", 0))
    llm_enabled = bool(u.get("llm_enabled", False))
    llm_thr = float(u.get("llm_threshold", 0.70))
    llm_budget = int(u.get("llm_max_per_tick", 2))
    likes_g = len(u.get("likes_global", []))
    dislikes_g = len(u.get("dislikes_global", []))

    # Historial por perfil activo
    sent_cnt = len(get_active_sent_ids(u))

    # Info del scheduler (poll actual)
    job = _pick_tick_job(context.job_queue)
    if job:
        try:
            iv = getattr(job, "interval", None)
            iv_sec = int(iv.total_seconds()) if hasattr(iv, "total_seconds") else int(iv)
        except Exception:
            iv_sec = None
    else:
        iv_sec = None
    # Prefer explicit schedule mode/time from bot_data
    mode = context.bot_data.get("_pr_tick_mode") if hasattr(context, "bot_data") else None
    tod  = context.bot_data.get("_pr_tick_time") if hasattr(context, "bot_data") else None
    if mode == "daily" and tod:
        poll_txt = f"daily at {tod}"
    else:
        if not iv_sec:
            try:
                iv_sec = context.bot_data.get("_pr_tick_interval_sec")
            except Exception:
                pass
        poll_txt = f"{iv_sec/60:.2f} min ({iv_sec} s)" if iv_sec else "not scheduled"

    # Último tick
    last_lucky = u.get("last_lucky_ts", "")
    try:
        if last_lucky:
            last_txt = datetime.datetime.fromisoformat(last_lucky).strftime("%Y-%m-%d %H:%M")
        else:
            last_txt = "(never)"
    except Exception:
        last_txt = "(invalid)"

    idle_ticks = int(u.get("idle_ticks", 0))

    msg = (
        f"<b>📊 PaperRadar · Status</b>\n"
        f"<b>Chat ID:</b> <code>{cid}</code>\n\n"
        f"<b>Perfil activo</b>\n"
        f"  • Nombre: <code>{escape(act)}</code>\n"
        f"  • Texto: <code>{prof_txt_safe}</code>\n"
        f"  • Nº perfiles: {len(profiles)}\n\n"
        f"<b>Ranking & Filtros</b>\n"
        f"  • topN: {topn}\n"
        f"  • sim_threshold: {thr:.2f}\n"
        f"  • max_age_hours: {max_age} (0 = sin filtro)\n"
        f"  • poll (global): {poll_txt}\n"
        f"  • idle_ticks: {idle_ticks}\n\n"
        f"<b>LLM</b>\n"
        f"  • Estado: {_yesno(llm_enabled)}\n"
        f"  • llm_threshold: {llm_thr:.2f}\n"
        f"  • llm_max_per_tick: {llm_budget}\n\n"
        f"<b>Feedback</b>\n"
        f"  • Likes: {likes_g}\n"
        f"  • Dislikes: {dislikes_g}\n\n"
        f"<b>Historial</b>\n"
        f"  • Items enviados (perfil activo): {sent_cnt}\n"
        f"  • Último tick: {last_txt}\n\n"
        f"<i>Comandos útiles:</i>\n"
        f"  • /sample — ranking heurístico\n"
        f"  • /ticknow — forzar ciclo manual\n"
        f"  • /poll &lt;min&gt; — cambiar intervalo global\n"
        f"  • /flush — limpiar historial del perfil activo\n"
        f"  • /flushall — limpiar todos los historiales\n"
    )

    context.bot.send_message(
        chat_id=cid,
        text=msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
