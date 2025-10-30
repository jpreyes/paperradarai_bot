# paperradar/storage/list_users.py
import os, re
from .paths import DATA_ROOT

CHAT_DIR_RE = re.compile(r"^\d+$")  # carpetas tipo chat_id (solo dígitos)

def list_all_user_ids():
    # Scan numeric chat_id directories directly under DATA_ROOT
    base = DATA_ROOT
    if not os.path.isdir(base):
        return []
    out = []
    for name in os.listdir(base):
        p = os.path.join(base, name)
        if os.path.isdir(p) and CHAT_DIR_RE.match(name):
            try:
                out.append(int(name))
            except Exception:
                pass
    return out
