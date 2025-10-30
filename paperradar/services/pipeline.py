from paperradar.fetchers.merge import fetch_entries
from paperradar.core.filters import is_recent
from paperradar.core.ranking import rank_items_for_user
from paperradar.core.llm import ideas as llm_ideas, heuristics as llm_heur

def build_ranked(u:dict):
    items = fetch_entries()
    if u.get("max_age_hours",0):
        items = [it for it in items if is_recent(it.get("published",""), u["max_age_hours"])]
    likes = (u.get("likes_by_profile",{}).get(u.get("active_profile","default"), [])
             if len(u.get("profiles",{}))>1 else u.get("likes_global",[]))
    dislikes = (u.get("dislikes_by_profile",{}).get(u.get("active_profile","default"), [])
             if len(u.get("profiles",{}))>1 else u.get("dislikes_global",[]))
    ranked = rank_items_for_user(u.get("profile",""), likes, dislikes, items)
    return ranked

def make_bullets(u:dict, item:dict, use_llm:bool):
    if use_llm:
        return llm_ideas(u.get("profile",""), item["title"], item.get("abstract",""))
    # FORZAR heurística cuando use_llm es False (no llamar al LLM)
    return llm_heur(u.get("profile",""), item["title"], item.get("abstract",""))

