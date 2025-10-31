import hashlib, json, logging, random, time, requests, re
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

def _key(summary, topics, title, abstract):
    h = hashlib.sha256()
    topic_serial = "|".join(topics or [])
    for s in (summary or "", topic_serial, title or "", abstract or ""):
        h.update(s.encode("utf-8"))
    return h.hexdigest()

def _tokenize(text: str):
    return re.findall(r"[a-zA-ZÁÉÍÓÚáéíóúñü]{4,}", (text or "").lower())

def heuristics(summary, topics, title, abstract):
    pf_tokens = set(_tokenize(summary))
    pf_tokens.update(t.lower() for t in (topics or []))
    paper_tokens = set(_tokenize((title or "") + " " + (abstract or "")))
    overlap = sorted(pf_tokens.intersection(paper_tokens))
    sims = []
    if overlap:
        sims.append("The paper references shared themes: " + ", ".join(overlap[:4]))
    if not sims:
        sims.append("General methodological alignment with your stated interests.")
    ideas = []
    topic_list = list(topics or [])
    if topic_list:
        ideas.append(f"Examine how this work informs your research on {topic_list[0]}.")
    if len(topic_list) > 1:
        ideas.append(f"Contrast the paper's approach with your focus on {topic_list[1]}.")
    if not ideas:
        ideas.append("Identify a concrete follow-up experiment inspired by this paper.")
    return {"similarities": sims[:3], "ideas": ideas[:2], "tag": "heur"}

load_llm_cache()

def ideas(summary, topics, title, abstract):
    if not OPENAI_API_KEY:
        out = heuristics(summary, topics, title, abstract); out["tag"]="heur"; return out
    key = _key(summary, topics, title, abstract)
    if key in LLM_CACHE:
        out = LLM_CACHE[key]; out["tag"]="llm_cache"; return out
    topics_str = ", ".join(topics or [])
    prompt = f"""You compare a researcher's interests with new papers.
Respond in JSON with:
- similarities: 2-3 concise bullets describing concrete commonalities
- ideas: 1-2 actionable bullets proposing next steps or integrations
Research summary:
{summary}
Key topics: {topics_str or 'n/a'}
Paper title:
{title}
Paper abstract:
{abstract}
"""
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
    out = heuristics(summary, topics, title, abstract); out["tag"]="llm_fail"; return out
