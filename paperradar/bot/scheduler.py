# paperradar/bot/scheduler.py
import logging
import datetime
from telegram import ChatAction

from paperradar.services.pipeline import build_ranked, make_bullets
from paperradar.storage.users import (
    get_user,
    save_user,
    get_active_sent_ids,
    add_sent_id,
    clear_sent_ids_for_active_profile,
)
from paperradar.storage.known_chats import KNOWN_CHATS
from paperradar.storage.history import upsert_history_record
from paperradar.storage.list_users import list_all_user_ids

# --- Parámetros del tick ---
AUTO_FLUSH_AFTER_IDLE = 3    # ticks seguidos sin enviar -> limpiar enviados del perfil activo
MIN_SIM_FLOOR         = 0.35 # piso al relajar umbral temporalmente en este ciclo
ALLOW_FALLBACK_DIGEST = True # si no hay "nuevos", enviar topN ignorando enviados

def _target_chat_ids():
    """
    Devuelve los chat_ids a procesar en cada tick combinando:
      - los registrados en memoria (KNOWN_CHATS)
      - los encontrados en disco (carpetas users/<chat_id>)
    """
    from_ids = set(int(x) for x in KNOWN_CHATS) if KNOWN_CHATS else set()
    from_disk = set(list_all_user_ids())
    tgt = sorted(from_ids | from_disk)
    if not tgt:
        logging.info("[tick] no target chats found (KNOWN_CHATS empty and no users in disk)")
    return tgt

def tick(context):
    """
    Job del scheduler (PTB v13): ejecuta ranking y envíos por cada chat conocido.
    - Respeta enviados por perfil activo (sent_ids_by_profile)
    - Auto-flush tras N ticks vacíos
    - Soft-relax del umbral en el ciclo si está muy alto
    - Fallback digest para no quedar en silencio absoluto
    - Marca last_lucky_ts para que /status muestre actividad del tick
    """
    try:
        for cid in _target_chat_ids():
            try:
                u = get_user(cid)

                # Marca que este chat fue procesado por el tick (aunque luego no envíe)
                u["last_lucky_ts"] = datetime.datetime.now().isoformat(timespec="seconds")

                if not u.get("profile"):
                    logging.info(f"[tick] cid={cid} skip: empty profile")
                    save_user(cid)  # guarda la marca de tiempo
                    continue

                active_profile = u.get("active_profile", "default")
                ranked_full = build_ranked(u)
                llm_budget  = int(u.get("llm_max_per_tick", 2))
                used_llm    = 0
                sent        = 0
                topN        = int(u.get("topn", 12))
                thr         = float(u.get("sim_threshold", 0.55))

                # Enviados del PERFIL ACTIVO
                already = get_active_sent_ids(u)

                # Candidatos "nuevos" por encima del umbral
                abovethr_new = [
                    (it, sc) for it, sc in ranked_full
                    if sc >= thr and ((it.get("id") or it.get("url") or "")[:200]) not in already
                ]

                logging.info(
                    f"[tick] cid={cid} topN={topN} thr={thr:.2f} "
                    f"ranked={len(ranked_full)} abovethr_new={len(abovethr_new)} "
                    f"sent_ids={len(already)} idle_ticks={u.get('idle_ticks', 0)}"
                )

                # --- Recuperación si no hay nada que enviar ---
                if not abovethr_new:
                    u["idle_ticks"] = int(u.get("idle_ticks", 0)) + 1

                    # 1) Auto-flush por perfil activo
                    if u["idle_ticks"] >= AUTO_FLUSH_AFTER_IDLE:
                        logging.warning(
                            f"[tick] cid={cid} auto-flush sent_ids (perfil activo) after {u['idle_ticks']} idle ticks"
                        )
                        clear_sent_ids_for_active_profile(u)
                        u["idle_ticks"] = 0
                        save_user(cid)

                        # Recalcula con enviados limpios del perfil activo
                        already = get_active_sent_ids(u)
                        abovethr_new = [
                            (it, sc) for it, sc in ranked_full
                            if sc >= thr and ((it.get("id") or it.get("url") or "")[:200]) not in already
                        ]

                    # 2) Soft-relax del umbral solo para este ciclo
                    if not abovethr_new and thr > MIN_SIM_FLOOR:
                        soft_thr = max(MIN_SIM_FLOOR, thr - 0.05)
                        logging.info(f"[tick] cid={cid} soft-relax thr {thr:.2f} → {soft_thr:.2f}")
                        abovethr_new = [
                            (it, sc) for it, sc in ranked_full
                            if sc >= soft_thr and ((it.get("id") or it.get("url") or "")[:200]) not in already
                        ]
                        thr = soft_thr  # solo efecto en este ciclo (no se persiste)

                # 3) Fallback digest: si sigue vacío, enviar topN ignorando enviados
                in_fallback_digest = False
                if not abovethr_new and ALLOW_FALLBACK_DIGEST and ranked_full:
                    logging.info(f"[tick] cid={cid} fallback digest: enviar topN ignorando sent_ids")
                    abovethr_new = [(it, sc) for it, sc in ranked_full if sc >= thr][:topN]
                    in_fallback_digest = True

                # --- Envío ---
                for it, sc in abovethr_new:
                    if sent >= topN:
                        break

                    pk = (it.get("id") or it.get("url") or "")[:200]

                    # Evita repetidos solo en modo normal (no en digest)
                    if pk in already and not in_fallback_digest:
                        continue

                    use_llm = (
                        u.get("llm_enabled", False)
                        and used_llm < llm_budget
                        and sc >= u.get("llm_threshold", 0.70)
                    )
                    bullets = make_bullets(u, it, use_llm=use_llm)
                    if bullets.get("tag") in ("llm", "llm_cache"):
                        used_llm += 1

                    try:
                        context.bot.send_chat_action(chat_id=cid, action=ChatAction.TYPING)
                    except Exception:
                        pass

                    from .handlers import send_paper
                    send_paper(context.bot, cid, it, sc, bullets)

                    # Marca como enviado SOLO si no es digest (para no bloquear)
                    if not in_fallback_digest:
                        add_sent_id(u, pk)

                    upsert_history_record(cid, it, sc, bullets, note="tick", profile=active_profile)
                    sent += 1

                # Si hubo envíos, resetea contador idle
                if sent > 0:
                    u["idle_ticks"] = 0

                save_user(cid)

            except Exception as per_chat_exc:
                # No dejes que un error por chat frene todo el ciclo
                logging.exception(f"[tick] cid={cid} error: {per_chat_exc}")

        logging.info("[tick] done.")
    except Exception as e:
        logging.exception(f"[tick] {e}")
