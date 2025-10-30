# paperradar/bot/commands_poll.py
import math
import datetime
from telegram import ParseMode
from html import escape
from paperradar.bot.scheduler import tick

TICK_JOB_NAME = "tick"
MIN_INTERVAL_SEC = 15


def _current_tick_job(job_queue):
    """Return the most relevant active 'tick' job.
    Prefer a job that looks enabled/not marked for removal.
    """
    try:
        jobs = job_queue.get_jobs_by_name(TICK_JOB_NAME) or []
    except Exception:
        jobs = []
    if not jobs:
        return None
    for j in jobs:
        try:
            if getattr(j, "enabled", True) and not getattr(j, "remove", False):
                return j
        except Exception:
            pass
    return jobs[-1]


def _remove_all_tick_jobs(job_queue):
    """Disable and schedule removal of all existing 'tick' jobs to avoid duplicates."""
    try:
        for j in job_queue.get_jobs_by_name(TICK_JOB_NAME) or []:
            try:
                if hasattr(j, "enabled"):
                    j.enabled = False
            except Exception:
                pass
            try:
                j.schedule_removal()
            except Exception:
                pass
    except Exception:
        pass


def poll_cmd(update, context):
    cid = update.effective_chat.id
    args = context.args or []

    # Query current schedule
    if not args:
        job = _current_tick_job(context.job_queue)
        if job:
            try:
                iv = getattr(job, "interval", None)
                iv_sec = int(iv.total_seconds()) if hasattr(iv, "total_seconds") else int(iv)
            except Exception:
                iv_sec = None
        else:
            iv_sec = None
        # Read mode/time hints from bot_data
        mode = context.bot_data.get("_pr_tick_mode") if hasattr(context, "bot_data") else None
        tod  = context.bot_data.get("_pr_tick_time") if hasattr(context, "bot_data") else None
        if mode == "daily" and tod:
            txt = f"Current poll schedule: <b>daily at {tod}</b>"
            context.bot.send_message(cid, txt, parse_mode=ParseMode.HTML)
            return
        else:
            if not iv_sec:
                try:
                    iv_sec = context.bot_data.get("_pr_tick_interval_sec")
                except Exception:
                    pass
            txt = (
                f"Current poll interval: <b>{iv_sec/60:.2f} min</b> ({iv_sec} s)"
                if iv_sec else "Current poll interval: <b>not scheduled</b>"
            )
        context.bot.send_message(cid, txt, parse_mode=ParseMode.HTML)
        return

    # Set new schedule
    # Accept formats: '<minutes>' or 'HHh' / 'HH:MMh'
    arg = args[0].strip()
    # Daily time-of-day?
    if arg.lower().endswith("h"):
        hhmm = arg[:-1].strip()
        try:
            parts = hhmm.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            now = datetime.datetime.now()
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target = target + datetime.timedelta(days=1)
            first = max(5, int((target - now).total_seconds()))
            seconds = 24 * 60 * 60
        except Exception:
            context.bot.send_message(cid, "Usage: /poll <minutes> OR /poll HHh OR /poll HH:MMh", parse_mode=ParseMode.HTML)
            return

        # Remove old and schedule daily
        _remove_all_tick_jobs(context.job_queue)
        context.job_queue.run_repeating(tick, interval=seconds, first=first, name=TICK_JOB_NAME)
        try:
            context.bot_data["_pr_tick_mode"] = "daily"
            context.bot_data["_pr_tick_time"] = f"{hh:02d}:{mm:02d}"
            context.bot_data["_pr_tick_interval_sec"] = seconds
            context.bot_data["_pr_tick_first_sec"] = first
        except Exception:
            pass
        context.bot.send_message(
            cid,
            f"Ok. Poll scheduled <b>daily at {hh:02d}:{mm:02d}</b>.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Otherwise assume minutes interval
    try:
        minutes = float(arg.replace(",", "."))
    except Exception:
        context.bot.send_message(cid, "Usage: /poll <minutes> OR /poll HHh OR /poll HH:MMh", parse_mode=ParseMode.HTML)
        return

    seconds = max(MIN_INTERVAL_SEC, int(math.ceil(minutes * 60)))

    # Remove all existing 'tick' jobs and schedule a fresh one
    _remove_all_tick_jobs(context.job_queue)
    job = context.job_queue.run_repeating(tick, interval=seconds, first=5, name=TICK_JOB_NAME)
    try:
        context.bot_data["_pr_tick_interval_sec"] = seconds
    except Exception:
        pass

    try:
        context.bot_data["_pr_tick_mode"] = "interval"
        context.bot_data["_pr_tick_interval_sec"] = seconds
        context.bot_data["_pr_tick_time"] = None
        context.bot_data["_pr_tick_first_sec"] = None
    except Exception:
        pass

    context.bot.send_message(
        cid,
        f"Ok. Poll interval set to <b>{minutes:.2f} min</b> ({seconds} s).",
        parse_mode=ParseMode.HTML,
    )
