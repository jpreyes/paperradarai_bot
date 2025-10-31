# paperradar/bot/handlers_docs.py
import os
import tempfile

from telegram import ParseMode

from paperradar.services.profile_builder import build_profile_from_pdf
from paperradar.storage.known_chats import register_chat
from paperradar.storage.users import (
    clear_sent_ids_for_active_profile,
    get_user,
    save_user,
)


def handle_profile_pdf(update, context):
    message = update.message
    document = message.document if message else None
    if not document:
        return
    if document.mime_type not in ("application/pdf", "application/x-pdf"):
        message.reply_text("Solo puedo procesar archivos PDF para generar tu perfil.")
        return

    cid = message.chat_id
    register_chat(cid)
    u = get_user(cid)
    u.setdefault("profiles", {})
    active = u.get("active_profile", "default")

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
        file_obj = document.get_file()
        file_obj.download(custom_path=tmp_path)
        analysis = build_profile_from_pdf(tmp_path)
    except Exception:
        analysis = None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    if not analysis:
        message.reply_text("No pude extraer texto útil del PDF. ¿Podrías verificar el archivo o intentar con otro?")
        return

    profile_text = analysis.get("profile_text", "") or ""
    u["profiles"][active] = profile_text
    u["profile"] = profile_text
    u["profile_summary"] = analysis.get("summary", profile_text)
    u["profile_topics"] = analysis.get("topics", [])
    u["profile_topic_weights"] = analysis.get("topic_weights", {})

    clear_sent_ids_for_active_profile(u)
    save_user(cid)

    topics = ", ".join(u["profile_topics"][:8]) if u["profile_topics"] else "—"
    summary_preview = u["profile_summary"][:600]
    file_name = document.file_name or "archivo.pdf"
    message.reply_text(
        (
            f"✅ Perfil actualizado desde <b>{file_name}</b>.\n"
            f"<b>Resumen:</b> {summary_preview}\n"
            f"<b>Temas clave:</b> {topics}\n\n"
            "El historial de enviados del perfil activo se reinició para reflejar los nuevos intereses."
        ),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
