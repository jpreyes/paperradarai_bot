from fastapi import FastAPI
from paperradar.storage.users import get_user
from paperradar.services.pipeline import build_ranked, make_bullets

app = FastAPI(title="PaperRadar API")

@app.get("/health")
def health(): return {"ok": True}

@app.get("/sample/{chat_id}")
def sample(chat_id:int, top:int=5):
    u = get_user(chat_id)
    ranked = build_ranked(u)[:top]
    out=[]
    for it, sc in ranked:
        b = make_bullets(u, it, use_llm=False)
        out.append({"score": round(sc,3), "item": it, "bullets": b})
    return out
