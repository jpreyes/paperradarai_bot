import hashlib, json, logging, random, time, requests
from paperradar.config import OPENAI_API_KEY, LLM_MODEL
from paperradar.storage.paths import LLM_CACHE_PATH

LLM_CACHE = {}
LLM_MAX_RETRIES=3; LLM_BACKOFF_BASE=0.8; LLM_BACKOFF_JITTER=(0.0,0.6)

def load_llm_cache():
    global LLM_CACHE
    try:
        import os
        if os.path.exists(LLM_CACHE_PATH):
            LLM_CACHE = json.load(open(LLM_CACHE_PATH,"r",encoding="utf-8"))
            logging.info(f"[llm] cache loaded: {len(LLM_CACHE)}")
    except Exception as ex:
        logging.warning(f"[llm] cache load failed: {ex}")

def save_llm_cache():
    json.dump(LLM_CACHE, open(LLM_CACHE_PATH,"w",encoding="utf-8"), ensure_ascii=False)

def _key(profile,title,abstract):
    h = hashlib.sha256()
    for s in (profile or "", title or "", abstract or ""): h.update(s.encode("utf-8"))
    return h.hexdigest()

def heuristics(profile,title,abstract):
    import re
    pf = re.findall(r"[a-zA-Z]{4,}", (profile or "").lower())
    ab = re.findall(r"[a-zA-Z]{4,}", (abstract or "").lower())
    overlap = sorted(set(pf).intersection(set(ab)))[:6]
    sims=[]
    if overlap: sims.append("Overlaps on: " + ", ".join(overlap[:4]))
    if "gmpe" in (abstract or "").lower():
        sims.append("Shared focus on GMPE performance and local adjustments.")
    if "modal" in (abstract or "").lower() or "oma" in (abstract or "").lower():
        sims.append("Common interest in operational/modal analysis for validation.")
    if not sims: sims=["Methodological overlap in modeling/validation approaches."]
    ideas=[]
    if "gmpe" in (abstract or "").lower(): ideas.append("Test a semi-non-ergodic correction with Chilean subduction data.")
    if "oma" in (abstract or "").lower() or "modal" in (abstract or "").lower(): ideas.append("Add OMA-based validation to benchmark conclusions.")
    if not ideas: ideas.append("Apply spectral matching to build site-specific accelerograms for nonlinear checks.")
    return {"similarities":sims[:3], "ideas":ideas[:2], "tag":"heur"}

load_llm_cache()

def ideas(profile,title,abstract):
    if not OPENAI_API_KEY:
        out = heuristics(profile,title,abstract); out["tag"]="heur"; return out
    key = _key(profile,title,abstract)
    if key in LLM_CACHE:
        out = LLM_CACHE[key]; out["tag"]="llm_cache"; return out
    prompt = f"""You are an assistant for a researcher in earthquake and structural engineering.
Return JSON with:
- similarities: 2-3 bullets of concrete overlaps
- ideas: 1-2 bullets of specific extensions
PROFILE:\n{profile}\nTITLE:\n{title}\nABSTRACT:\n{abstract}\n"""
    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type":"application/json"}
    body={"model": LLM_MODEL, "messages":[{"role":"user","content":prompt}], "temperature":0.1, "response_format":{"type":"json_object"}}
    last=None
    for attempt in range(LLM_MAX_RETRIES):
        try:
            resp = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, data=json.dumps(body), timeout=30)
            if resp.status_code==429 or 500<=resp.status_code<600: raise requests.HTTPError(f"{resp.status_code} {resp.text[:120]}")
            resp.raise_for_status()
            parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
            out={"similarities":parsed.get("similarities",[])[:3], "ideas":parsed.get("ideas",[])[:2], "tag":"llm"}
            LLM_CACHE[key]=out; save_llm_cache(); return out
        except Exception as e:
            last=e
            delay = (LLM_BACKOFF_BASE*(2**attempt))+random.uniform(*LLM_BACKOFF_JITTER)
            time.sleep(delay)
    logging.warning(f"[llm] failed -> {last}")
    out = heuristics(profile,title,abstract); out["tag"]="llm_fail"; return out
