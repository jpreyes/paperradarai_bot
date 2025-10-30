import os
from paperradar.config import DATA_ROOT
os.makedirs(DATA_ROOT, exist_ok=True)

def user_dir(chat_id:int)->str:
    d = os.path.join(DATA_ROOT, str(chat_id))
    os.makedirs(d, exist_ok=True)
    return d

def user_path(chat_id:int, name:str)->str:
    return os.path.join(user_dir(chat_id), name)

KNOWN_CHATS_PATH = os.path.join(DATA_ROOT, "known_chats.json")
LLM_CACHE_PATH   = os.path.join(DATA_ROOT, "llm_cache.json")
