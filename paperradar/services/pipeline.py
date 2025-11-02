from paperradar.fetchers.merge import fetch_entries
from paperradar.fetchers.search_terms import set_custom_terms
from paperradar.core.filters import is_recent
from paperradar.core.ranking import rank_items_for_user
from paperradar.core.llm import ideas as llm_ideas, heuristics as llm_heur

def build_ranked(u:dict):
    set_custom_terms(u.get("profile_topics", []))
    items = fetch_entries()
    if u.get("max_age_hours",0):
        items = [it for it in items if is_recent(it.get("published",""), u["max_age_hours"])]
    likes = (u.get("likes_by_profile",{}).get(u.get("active_profile","default"), [])
             if len(u.get("profiles",{}))>1 else u.get("likes_global",[]))
    dislikes = (u.get("dislikes_by_profile",{}).get(u.get("active_profile","default"), [])
             if len(u.get("profiles",{}))>1 else u.get("dislikes_global",[]))
    ranked = rank_items_for_user(
        u.get("profile", ""),
        likes,
        dislikes,
        items,
        topic_weights=u.get("profile_topic_weights", {}),
    )
    return ranked

def make_bullets(u:dict, item:dict, use_llm:bool):
    summary = u.get("profile_summary") or u.get("profile", "")
    topics = u.get("profile_topics", [])
    if use_llm:
        return llm_ideas(summary, topics, item["title"], item.get("abstract",""))
    # FORZAR heurística cuando use_llm es False (no llamar al LLM)
    return llm_heur(summary, topics, item["title"], item.get("abstract",""))
