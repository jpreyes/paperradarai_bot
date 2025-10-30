import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BETA_DISLIKE = 0.40
PRIOR_TERMS  = {"operational modal analysis":0.12, "oma":0.10, "stochastic subspace":0.10, "ssi":0.10,
                "system identification":0.08, "structural health monitoring":0.10, "shm":0.10,
                "damage detection":0.10, "modal parameters":0.08, "natural frequency":0.06, "damping ratio":0.06,
                "bridge":0.10, "building":0.08, "reinforced concrete":0.10, "masonry":0.08, "steel":0.06,
                "girder":0.06, "cable-stayed":0.06, "arch bridge":0.06,
                "soil-structure interaction":0.10, "foundation flexibility":0.08,
                "earthquake":0.04, "seismic":0.04, "gmpe":0.04, "non-ergodic":0.04, "psha":0.04, "vs30":0.03}

BOOST = list(PRIOR_TERMS.keys()) + ["rotational","spectral matching"]

def boost_text(s:str)->str:
    s_low = (s or "").lower()
    bonus = " ".join([w for w in BOOST if w in s_low for _ in range(8)])
    return (s or "") + " " + bonus

def _mix_title_abstract(it):
    return (" " + (it.get('title',"")) + " ")*3 + " " + (it.get('abstract') or "")

def prior_score(title:str, abstract:str)->float:
    t = (title or "").lower(); a = (abstract or "").lower()
    base = sum(w for k,w in PRIOR_TERMS.items() if k in t or k in a)
    title_bonus = sum(0.5*w for k,w in PRIOR_TERMS.items() if k in t)
    return base + title_bonus

def rank_items_for_user(profile_text:str, likes:list, dislikes:list, items:list):
    if not profile_text or not items: return []
    corpus = [boost_text(profile_text)] + [boost_text(_mix_title_abstract(it)) for it in items]
    if likes: corpus[0] = boost_text(profile_text + " " + " ".join(likes))
    vectorizer = TfidfVectorizer(stop_words="english", max_features=100_000,
                                 ngram_range=(1,3), lowercase=True,
                                 sublinear_tf=True, min_df=2)
    X = vectorizer.fit_transform(corpus)
    prof_vec = X[0]; item_vecs = X[1:]
    sims = cosine_similarity(prof_vec, item_vecs).ravel()
    penalty = np.zeros_like(sims)
    if dislikes:
        try:
            D = vectorizer.transform([boost_text(t) for t in dislikes])
            dcent = D.mean(axis=0)
            penalty = cosine_similarity(item_vecs, dcent).ravel()
        except Exception:
            pass
    ranked=[]
    for idx,(it,s_pos) in enumerate(zip(items, sims)):
        pr = prior_score(it.get('title',''), it.get('abstract',''))
        s_neg = penalty[idx] if len(dislikes) else 0.0
        final = float(s_pos) - BETA_DISLIKE*float(s_neg) + pr
        ranked.append((it, float(final)))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked
