# paperradar/bot/commands_profiles.py
from telegram import ParseMode
from html import escape
from paperradar.storage.users import (
    get_user,
    save_user,
    clear_sent_ids_for_active_profile,
)
from .utils import split_once, argstr
from paperradar.services.profile_builder import analyze_text


def _apply_profile_analysis(u: dict, text: str, *, summary_override: str = None) -> str:
    analysis = analyze_text(text, summary_override=summary_override)
    fallback = (summary_override if summary_override is not None else text or "").strip()
    if analysis:
        u["profile_summary"] = analysis["summary"]
        u["profile_topics"] = analysis["topics"]
        u["profile_topic_weights"] = analysis["topic_weights"]
        return analysis["profile_text"]
    u["profile_summary"] = fallback
    u["profile_topics"] = []
    u["profile_topic_weights"] = {}
    return fallback

def profile(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u.setdefault("profiles", {})
    txt = argstr(update)
    if not txt:
        context.bot.send_message(cid, "Usage: /profile <abstract or keywords>")
        return
    active = u.get("active_profile", "default")
    profile_text = _apply_profile_analysis(u, txt, summary_override=txt)
    u["profiles"][active] = profile_text
    u["profile"] = profile_text
    save_user(cid)
    # HTML + escape para evitar problemas con underscores, *, etc.
    context.bot.send_message(
        cid,
        f"✅ Profile updated for <b>{escape(active)}</b>.",
        parse_mode=ParseMode.HTML,
    )

def pnew(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u.setdefault("profiles", {})
    raw = argstr(update)
    name, text = split_once(raw, " ", default_right="")
    if not name:
        context.bot.send_message(cid, "Usage: /pnew <name> <abstract>")
        return
    if name in u["profiles"]:
        context.bot.send_message(cid, f"Profile '{escape(name)}' already exists. Use /puse {name}.", parse_mode=ParseMode.HTML)
        return
    profile_text = _apply_profile_analysis(u, text or "", summary_override=(text or ""))
    u["profiles"][name] = profile_text
    u["active_profile"] = name
    u["profile"] = profile_text
    # Reinicia historial de enviados para el nuevo perfil
    from paperradar.storage.users import get_active_sent_ids
    _ = get_active_sent_ids(u)  # solo asegura la estructura, sin limpiar
    save_user(cid)
    context.bot.send_message(
        cid,
        f"✅ Created profile <b>{escape(name)}</b> and set active.",
        parse_mode=ParseMode.HTML,
    )

def puse(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u.setdefault("profiles", {})
    name = argstr(update)
    if not name:
        context.bot.send_message(cid, "Usage: /puse <name>")
        return
    if name not in u["profiles"]:
        context.bot.send_message(cid, f"Profile '{escape(name)}' not found. Use /plist.", parse_mode=ParseMode.HTML)
        return
    u["active_profile"] = name
    stored = u["profiles"].get(name, "")
    u["profile"] = _apply_profile_analysis(u, stored, summary_override=stored)
    # Reinicia historial de enviados al cambiar de perfil (como pediste)
    from paperradar.storage.users import get_active_sent_ids
    _ = get_active_sent_ids(u)  # solo asegura la estructura, sin limpiar
    save_user(cid)
    context.bot.send_message(
        cid,
        f"✅ Active profile is now <b>{escape(name)}</b>.",
        parse_mode=ParseMode.HTML,
    )

def pdel(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u.setdefault("profiles", {})
    name = argstr(update)
    if not name:
        context.bot.send_message(cid, "Usage: /pdel <name>")
        return
    if name not in u["profiles"]:
        context.bot.send_message(cid, f"Profile '{escape(name)}' not found.", parse_mode=ParseMode.HTML)
        return
    if len(u["profiles"]) == 1:
        context.bot.send_message(cid, "Cannot delete the only profile.")
        return

    # Borra el perfil y su historial de enviados por perfil (si existe)
    del u["profiles"][name]
    try:
        # limpia rastros en sent_ids_by_profile si existe
        u.get("sent_ids_by_profile", {}).pop(name, None)
    except Exception:
        pass

    # Si el eliminado estaba activo, elige otro como activo
    if u.get("active_profile") == name:
        new_active = next(iter(u["profiles"].keys()))
        u["active_profile"] = new_active
        stored = u["profiles"].get(new_active, "")
        u["profile"] = _apply_profile_analysis(u, stored, summary_override=stored)
        # Nota: NO limpiamos aquí el historial del nuevo activo (ya existía antes).
        # Si prefieres arrancar "en limpio", puedes llamar:
        # clear_sent_ids_for_active_profile(u)

    save_user(cid)
    context.bot.send_message(
        cid,
        f"🗑️ Deleted profile '<b>{escape(name)}</b>'. Active: <b>{escape(u['active_profile'])}</b>.",
        parse_mode=ParseMode.HTML,
    )

def plist(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u.setdefault("profiles", {})
    lines = []
    act = u.get("active_profile", "default")
    for k, v in u["profiles"].items():
        mark = "⭐" if k == act else "•"
        lines.append(f"{mark} {k}: {('('+str(len(v))+' chars)') if v else '(empty)'}")
    context.bot.send_message(cid, "Profiles:\n" + "\n".join(lines))

def pview(update, context):
    cid = update.effective_chat.id
    u = get_user(cid)
    u.setdefault("profiles", {})
    name = argstr(update) or u.get("active_profile", "default")
    txt = u["profiles"].get(name)
    if txt is None:
        context.bot.send_message(cid, f"Profile '{escape(name)}' not found.", parse_mode=ParseMode.HTML)
        return
    # HTML seguro con <pre><code> para mostrar texto completo sin romper el parseo
    context.bot.send_message(
        cid,
        f"<b>{escape(name)}</b>\n<pre><code>{escape(txt)}</code></pre>",
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
