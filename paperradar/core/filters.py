import re, html
from datetime import datetime, timezone
def sanitize_text(s:str)->str:
    s = html.unescape(s or "")
    return re.sub(r"\s+"," ", s).strip()

def english_only(s:str)->bool:
    if not s: return False
    ascii_ratio = sum(1 for ch in s if ord(ch)<128)/max(1,len(s))
    has_en_stop = any(w in s.lower() for w in [" the "," and "," of "," to "," with "," for "," in "])
    return ascii_ratio>0.9 and has_en_stop

def parse_iso(dt:str):
    if not dt: return None
    try:
        s = dt.strip()
        if s.endswith("Z"): s = s[:-1] + "+00:00"
        if len(s)==10 and s[4]=="-" and s[7]=="-": s += "T00:00:00+00:00"
        if len(s)==19 and s[4]=="-" and s[7]=="-" and s[10]=="T": s += "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None

def year_from_date(dt:str):
    d = parse_iso(dt); return d.year if d else ""

def is_recent(published:str, max_hours:int)->bool:
    if not max_hours: return True
    dt = parse_iso(published)
    if dt is None: return True
    return (datetime.now(timezone.utc)-dt).total_seconds() <= max_hours*3600
