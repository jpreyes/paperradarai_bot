# paperradar/bot/utils.py
from typing import Tuple

def split_once(s: str, sep: str = " ", default_left: str = "", default_right: str = "") -> Tuple[str,str]:
    if not s:
        return default_left, default_right
    i = s.find(sep)
    if i == -1:
        return s.strip(), default_right
    return s[:i].strip(), s[i+1:].strip()

def argstr(update) -> str:
    t = update.message.text or ""
    parts = t.split(" ", 1)
    return parts[1].strip() if len(parts) > 1 else ""
