# paperradar/bot/commands_jobs.py
from telegram import ParseMode
from html import escape

def jobs(update, context):
    cid = update.effective_chat.id
    try:
        all_jobs = getattr(context.job_queue, "jobs", lambda: [])()
    except Exception:
        all_jobs = []
    lines = [f"<b>Jobs activos: {len(all_jobs)}</b>"]
    mode = context.bot_data.get("_pr_tick_mode") if hasattr(context, "bot_data") else None
    tod  = context.bot_data.get("_pr_tick_time") if hasattr(context, "bot_data") else None
    for i, j in enumerate(all_jobs, 1):
        name = getattr(j, "name", None)
        cb   = getattr(j, "callback", None)
        iv   = getattr(j, "interval", None)
        try:
            iv_sec = int(iv.total_seconds()) if hasattr(iv, "total_seconds") else int(iv)
        except Exception:
            # Fallback: prefer bot_data (authoritative), then legacy attr if present
            try:
                iv_sec = context.bot_data.get("_pr_tick_interval_sec")
            except Exception:
                iv_sec = None
            if not iv_sec:
                iv_sec = getattr(j, "_pr_interval_sec", None)
        cb_name = getattr(cb, "__name__", str(cb))
        extra = ""
        if mode == "daily" and tod:
            extra = f" mode=daily@{escape(tod)}"
        lines.append(
            f"{i}. name=<code>{escape(str(name))}</code>  "
            f"cb=<code>{escape(cb_name)}</code>  "
            f"interval={'{} s'.format(iv_sec) if iv_sec else 'N/A'}{extra}"
        )
    context.bot.send_message(cid, "\n".join(lines), parse_mode=ParseMode.HTML)
