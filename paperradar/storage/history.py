import csv, json, logging, os, re
from datetime import datetime, timezone
from paperradar.storage.paths import user_path

MAX_JSON_RECORDS = 5000

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def _profile_slug(profile: str | None) -> str:
    base = (profile or "default").strip() or "default"
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", base.lower())
    slug = slug.strip("_") or "default"
    return slug[:60]

def _history_filename(profile: str | None, ext: str) -> str:
    slug = _profile_slug(profile)
    if slug == "default":
        return f"history.{ext}"
    return f"history_{slug}.{ext}"

def user_history_json(chat_id: int, profile: str | None = None) -> str:
    return user_path(chat_id, _history_filename(profile, "json"))

def user_history_csv(chat_id: int, profile: str | None = None) -> str:
    return user_path(chat_id, _history_filename(profile, "csv"))

def load_history(chat_id: int, profile: str | None = None) -> list[dict]:
    path = user_history_json(chat_id, profile)
    if os.path.exists(path):
        try:
            data = json.load(open(path, "r", encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as ex:
            logging.warning(f"[history] read failed {chat_id} ({profile}): {ex}")
    if profile:
        fallback = user_history_json(chat_id)
        if os.path.exists(fallback):
            try:
                data = json.load(open(fallback, "r", encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
    return []

def upsert_history_record(chat_id: int, item: dict, score: float, bullets: dict, note: str = "", profile: str | None = None):
    rec_profile = profile or "default"
    rec = {
        "ts": now_iso(),
        "profile": rec_profile,
        "id": item.get("id", ""),
        "source": item.get("source", ""),
        "title": item.get("title", ""),
        "abstract": item.get("abstract", ""),
        "url": item.get("url", ""),
        "published": item.get("published", ""),
        "score": round(score, 4),
        "similarities": bullets.get("similarities", []),
        "ideas": bullets.get("ideas", []),
        "venue": item.get("venue", ""),
        "year": item.get("year", ""),
        "authors": item.get("authors", []),
        "note": note,
        "tag": bullets.get("tag", ""),
    }
    jpath = user_history_json(chat_id, profile)
    data = load_history(chat_id, profile)
    pid = rec["id"]
    idx = next((i for i, x in enumerate(reversed(data)) if x.get("id", "") == pid), None)
    if idx is None:
        data.append(rec)
    else:
        data[-(idx + 1)] = rec
    if len(data) > MAX_JSON_RECORDS:
        data = data[-MAX_JSON_RECORDS:]
    json.dump(data, open(jpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    csv_path = user_history_csv(chat_id, profile)
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts", "profile", "id", "source", "title", "url", "published", "score", "venue", "year", "authors", "similarities", "ideas", "note", "tag"])
        for r in data:
            w.writerow([
                r.get("ts", ""),
                r.get("profile", rec_profile),
                r.get("id", ""),
                r.get("source", ""),
                r.get("title", ""),
                r.get("url", ""),
                r.get("published", ""),
                r.get("score", ""),
                r.get("venue", ""),
                r.get("year", ""),
                "; ".join(r.get("authors", [])),
                "; ".join(r.get("similarities", [])),
                "; ".join(r.get("ideas", [])),
                r.get("note", ""),
                r.get("tag", ""),
            ])
