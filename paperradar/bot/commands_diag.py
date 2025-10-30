# paperradar/bot/commands_diag.py
from telegram import ParseMode
from html import escape
from paperradar.storage.users import get_user
from paperradar.services.pipeline import build_ranked
try:
    # si existe utilitario para fecha, úsalo, si no, ignoramos este detalle
    from paperradar.core.filters import is_recent
except Exception:
    def is_recent(*args, **kwargs):
        return True

def diag(update, context):
    """Diagnóstico del ranking actual y por qué no se envía en tick."""
    cid = update.effective_chat.id
    u = get_user(cid)

    thr   = float(u.get("sim_threshold", 0.55))
    topN  = int(u.get("topn", 12))
    max_h = int(u.get("max_age_hours", 0))
    sent_ids = u.get("sent_ids", set())

    ranked = build_ranked(u)
    total  = len(ranked)

    below_thr = [(it, sc) for it, sc in ranked if sc < thr]
    above_thr = [(it, sc) for it, sc in ranked if sc >= thr]

    if max_h:
        recent = [x for x in above_thr if is_recent(x[0].get("published",""), max_h)]
        nonrec = [x for x in above_thr if not is_recent(x[0].get("published",""), max_h)]
    else:
        recent = above_thr
        nonrec = []

    blocked_sent = [(it, sc) for it, sc in recent if ((it.get("id") or it.get("url") or "")[:200]) in sent_ids]
    candidates   = [(it, sc) for it, sc in recent if ((it.get("id") or it.get("url") or "")[:200]) not in sent_ids]

    def fmt(pair):
        it, sc = pair
        t = escape(it.get("title", ""))[:120]
        return f"{sc:.3f} · {t}"
    tops = "\n".join(fmt(x) for x in ranked[:5]) or "(vacío)"

    msg = (
        f"<b>Diag</b>\n"
        f"thr=<code>{thr:.2f}</code>  topN=<code>{topN}</code>  max_age_hours=<code>{max_h}</code>\n"
        f"total_ranked=<code>{total}</code>\n\n"
        f"≥ thr (antes de sent_ids): <code>{len(above_thr)}</code>\n"
        + (f"  └ recientes (aplica filtro max_age): <code>{len(recent)}</code>\n" if max_h else "")
        + (f"  └ no recientes: <code>{len(nonrec)}</code>\n" if max_h else "")
        + f"bloqueados por sent_ids: <code>{len(blocked_sent)}</code>\n"
        f"candidatos a enviar ahora: <code>{len(candidates)}</code>\n\n"
        f"<b>Top 5 (score · título):</b>\n{tops}"
    )
    context.bot.send_message(chat_id=cid, text=msg, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

