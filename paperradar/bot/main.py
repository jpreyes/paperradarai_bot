# paperradar/bot/main.py
import logging
import math
import datetime
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters

from paperradar.config import TELEGRAM_BOT_TOKEN, DEFAULT_POLL_INTERVAL_MIN, POLL_DAILY_TIME
from paperradar.logging_setup import setup as setup_logging
from paperradar.storage.known_chats import load_known_chats, bootstrap_from_disk
from paperradar.storage.users import get_user, save_user, forgetme
from .commands_status import status
from .handlers import sample
from .scheduler import tick  # callback del job

TICK_JOB_NAME = "tick"

def start(update, context):
    cid = update.effective_chat.id
    from paperradar.storage.known_chats import register_chat
    register_chat(cid)
    context.bot.send_message(
        chat_id=cid,
        text=(
            "PaperRadar ready.\n"
            "Usa /profile <abstract> o /pnew <topic> <abstract>.\n"
            "Comandos: /status /pnew /puse /pdel /plist /pview /like /dislike /likes /dislikes "
            "/llm /tune /age /poll /topn /llmbudget /llmlimit /export /backup "
            "/clear_history /clear_llmcache /clear_likes /clear_dislikes /forgetme /sample /flush"
        ),
    )

def _schedule_tick(updater, minutes: float):
    """Programa (o reprograma) el job global 'tick'.
    Si POLL_DAILY_TIME está definido ("HH[:MM]"), programa diario a la hora local indicada.
    En caso contrario, usa un intervalo en minutos.
    """
    # Elimina cualquier job previo con ese nombre
    try:
        for j in updater.job_queue.get_jobs_by_name(TICK_JOB_NAME):
            j.schedule_removal()
    except Exception:
        pass

    daily = POLL_DAILY_TIME or ""
    if daily:
        try:
            parts = daily.split(":")
            hh = int(parts[0])
            mm = int(parts[1]) if len(parts) > 1 else 0
            now = datetime.datetime.now()
            target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if target <= now:
                target = target + datetime.timedelta(days=1)
            first = max(5, int((target - now).total_seconds()))
            seconds = 24 * 60 * 60
            updater.job_queue.run_repeating(tick, interval=seconds, first=first, name=TICK_JOB_NAME)
            # Guarda metadatos para comandos
            try:
                updater.dispatcher.bot_data["_pr_tick_mode"] = "daily"
                updater.dispatcher.bot_data["_pr_tick_time"] = f"{hh:02d}:{mm:02d}"
                updater.dispatcher.bot_data["_pr_tick_interval_sec"] = seconds
                updater.dispatcher.bot_data["_pr_tick_first_sec"] = first
            except Exception:
                pass
            logging.info(f"[sched] scheduled '{TICK_JOB_NAME}' daily at {hh:02d}:{mm:02d} (first in {first}s)")
            return
        except Exception as ex:
            logging.warning(f"[sched] POLL_DAILY_TIME invalid '{daily}': {ex}")

    # Fallback a intervalo en minutos
    try:
        seconds = max(15, int(math.ceil(float(minutes) * 60)))
    except Exception:
        seconds = 60  # fallback seguro

    updater.job_queue.run_repeating(tick, interval=seconds, first=5, name=TICK_JOB_NAME)
    try:
        updater.dispatcher.bot_data["_pr_tick_mode"] = "interval"
        updater.dispatcher.bot_data["_pr_tick_interval_sec"] = seconds
        updater.dispatcher.bot_data["_pr_tick_time"] = None
        updater.dispatcher.bot_data["_pr_tick_first_sec"] = None
    except Exception:
        pass
    logging.info(f"[sched] scheduled '{TICK_JOB_NAME}' every {seconds}s")

def main():
    setup_logging()
    load_known_chats()
    # Ensure previously seen users are registered without requiring /start after restarts
    bootstrap_from_disk()

    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env")

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # --- Commands principales ---
    from .commands_profiles import profile, pnew, puse, pdel, plist, pview
    from .commands_feedback import like, dislike, likes, dislikes
    from .commands_tuning import tune, age, topn, llmbudget, llmlimit  # (sin poll aquí)
    from .commands_llm import llm
    from .commands_export import export, backup, clear_history, clear_llmcache, clear_likes, clear_dislikes
    from .commands_misc import forgetme as cmd_forgetme, flush, flushall
    from .commands_ticknow import ticknow
    from .commands_diag import diag
    from .commands_poll import poll_cmd  # /poll que reprograma el job global
    from .commands_jobs import jobs       # /jobs para depurar la JobQueue

    dp.add_handler(CommandHandler("diag", diag))

    dp.add_handler(CommandHandler("profile", profile))
    dp.add_handler(CommandHandler("pnew", pnew))
    dp.add_handler(CommandHandler("puse", puse))
    dp.add_handler(CommandHandler("pdel", pdel))
    dp.add_handler(CommandHandler("plist", plist))
    dp.add_handler(CommandHandler("pview", pview))

    dp.add_handler(CommandHandler("like", like))
    dp.add_handler(CommandHandler("dislike", dislike))
    dp.add_handler(CommandHandler("likes", likes))
    dp.add_handler(CommandHandler("dislikes", dislikes))

    # /poll NUEVO (reprograma 'tick')
    dp.add_handler(CommandHandler("poll", poll_cmd, pass_args=True))

    dp.add_handler(CommandHandler("tune", tune))
    dp.add_handler(CommandHandler("age", age))
    dp.add_handler(CommandHandler("topn", topn))
    dp.add_handler(CommandHandler("llmbudget", llmbudget))
    dp.add_handler(CommandHandler("llmlimit", llmlimit))

    dp.add_handler(CommandHandler("llm", llm))

    dp.add_handler(CommandHandler("export", export))
    dp.add_handler(CommandHandler("backup", backup))
    dp.add_handler(CommandHandler("clear_history", clear_history))
    dp.add_handler(CommandHandler("clear_llmcache", clear_llmcache))
    dp.add_handler(CommandHandler("clear_likes", clear_likes))
    dp.add_handler(CommandHandler("clear_dislikes", clear_dislikes))

    dp.add_handler(CommandHandler("forgetme", cmd_forgetme))
    dp.add_handler(CommandHandler("flush", flush))
    dp.add_handler(CommandHandler("flushall", flushall))
    dp.add_handler(CommandHandler("status", status))
    dp.add_handler(CommandHandler("ticknow", ticknow))
    dp.add_handler(CommandHandler("jobs", jobs))  # depuración

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("sample", sample))
    def _auto_register(update, context):
        try:
            from paperradar.storage.known_chats import register_chat
            if update and update.effective_chat:
                register_chat(update.effective_chat.id)
        except Exception:
            pass
        # no-op for content
        return None

    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, _auto_register))

    # --- Scheduler: programa 'tick' según .env al iniciar ---
    _schedule_tick(updater, DEFAULT_POLL_INTERVAL_MIN)

    # Arranca explícitamente el JobQueue (belt & suspenders en PTB v13)
    try:
        updater.job_queue.start()
    except Exception:
        pass

    # Verificación: log del estado del job
    try:
        jobs_now = updater.job_queue.get_jobs_by_name(TICK_JOB_NAME)
        logging.info(f"[sched] jobs with name '{TICK_JOB_NAME}': {len(jobs_now)}")
    except Exception:
        logging.info("[sched] could not list jobs by name")

    updater.start_polling(drop_pending_updates=True)
    logging.info("Bot running. Ctrl+C to exit.")
    updater.idle()

if __name__ == "__main__":
    main()
