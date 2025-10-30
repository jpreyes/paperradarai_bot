import json, logging, os
from typing import Set
from .paths import KNOWN_CHATS_PATH
from .list_users import list_all_user_ids

KNOWN_CHATS: Set[int] = set()

def load_known_chats():
    global KNOWN_CHATS
    if os.path.exists(KNOWN_CHATS_PATH):
        try:
            with open(KNOWN_CHATS_PATH,"r",encoding="utf-8") as f:
                KNOWN_CHATS = set(json.load(f))
            logging.info(f"[boot] known_chats loaded: {len(KNOWN_CHATS)}")
        except Exception as ex:
            logging.warning(f"[boot] known_chats load failed: {ex}")

def save_known_chats():
    try:
        with open(KNOWN_CHATS_PATH,"w",encoding="utf-8") as f:
            json.dump(sorted(list(KNOWN_CHATS)), f, ensure_ascii=False, indent=2)
    except Exception as ex:
        logging.warning(f"[boot] known_chats save failed: {ex}")

def register_chat(chat_id:int):
    KNOWN_CHATS.add(chat_id); save_known_chats()

def bootstrap_from_disk():
    """Merge KNOWN_CHATS with chat IDs found on disk and persist.
    Use this at startup so restarts don't require /start from users.
    """
    try:
        ids = set(int(x) for x in list_all_user_ids())
    except Exception as ex:
        logging.warning(f"[boot] list_all_user_ids failed: {ex}")
        ids = set()
    if ids:
        before = len(KNOWN_CHATS)
        KNOWN_CHATS.update(ids)
        if len(KNOWN_CHATS) != before:
            save_known_chats()
        logging.info(f"[boot] known_chats bootstrapped from disk: +{len(KNOWN_CHATS)-before} (total {len(KNOWN_CHATS)})")
