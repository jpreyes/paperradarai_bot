import csv, json, logging, os
from datetime import datetime, timezone
from paperradar.storage.paths import user_path
MAX_JSON_RECORDS = 5000

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def user_history_json(chat_id): return user_path(chat_id,"history.json")
def user_history_csv(chat_id):  return user_path(chat_id,"history.csv")

def upsert_history_record(chat_id:int, item:dict, score:float, bullets:dict, note:str=""):
    rec = {
        "ts": now_iso(), "id": item.get("id",""), "source": item.get("source",""),
        "title": item.get("title",""), "abstract": item.get("abstract",""),
        "url": item.get("url",""), "published": item.get("published",""),
        "score": round(score,4), "similarities": bullets.get("similarities",[]),
        "ideas": bullets.get("ideas",[]), "venue": item.get("venue",""), "year": item.get("year",""),
        "authors": item.get("authors",[]), "note": note, "tag": bullets.get("tag",""),
    }
    jpath = user_history_json(chat_id)
    data = []
    if os.path.exists(jpath):
        try: data = json.load(open(jpath,"r",encoding="utf-8"))
        except Exception as ex:
            logging.warning(f"[history] read failed {chat_id}: {ex}")
            data = []
    pid = rec["id"]
    idx = next((i for i,x in enumerate(reversed(data)) if x.get("id","")==pid), None)
    if idx is None: data.append(rec)
    else: data[-(idx+1)] = rec
    if len(data) > MAX_JSON_RECORDS: data = data[-MAX_JSON_RECORDS:]
    json.dump(data, open(jpath,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    with open(user_history_csv(chat_id), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ts","id","source","title","url","published","score","venue","year","authors","similarities","ideas","note","tag"])
        for r in data:
            w.writerow([r.get("ts",""), r.get("id",""), r.get("source",""), r.get("title",""),
                        r.get("url",""), r.get("published",""), r.get("score",""),
                        r.get("venue",""), r.get("year",""), "; ".join(r.get("authors",[])),
                        "; ".join(r.get("similarities",[])), "; ".join(r.get("ideas",[])),
                        r.get("note",""), r.get("tag","")])
