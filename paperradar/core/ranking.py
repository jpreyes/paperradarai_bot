import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BETA_DISLIKE = 0.40
PRIOR_SCALE = 0.5


def _mix_title_abstract(it):
    return (" " + (it.get("title", "") or "") + " ") * 3 + " " + (it.get("abstract") or "")


def _boost_profile(profile_text: str, topic_weights: dict) -> str:
    if not topic_weights:
        return profile_text
    additions = []
    for term, weight in sorted(topic_weights.items(), key=lambda kv: kv[1], reverse=True)[:25]:
        repeats = 1
        if weight > 0.2:
            repeats = 3
        elif weight > 0.05:
            repeats = 2
        additions.extend([term] * repeats)
    if additions:
        return f"{profile_text} {' '.join(additions)}"
    return profile_text


def _boost_item(item_text: str, topic_weights: dict) -> str:
    if not topic_weights:
        return item_text
    lower = item_text.lower()
    additions = []
    for term, weight in topic_weights.items():
        if term.lower() in lower:
            repeats = 2 if weight > 0.1 else 1
            additions.extend([term] * repeats)
    if additions:
        return f"{item_text} {' '.join(additions)}"
    return item_text


def _topic_prior(item_text: str, topic_weights: dict) -> float:
    if not topic_weights:
        return 0.0
    lower = item_text.lower()
    score = sum(weight for term, weight in topic_weights.items() if term.lower() in lower)
    return float(PRIOR_SCALE * score)


def rank_items_for_user(profile_text: str, likes: list, dislikes: list, items: list, topic_weights: dict = None):
    if not profile_text or not items:
        return []
    topic_weights = topic_weights or {}
    corpus = [_boost_profile(profile_text, topic_weights)]
    for it in items:
        item_text = _boost_item(_mix_title_abstract(it), topic_weights)
        corpus.append(item_text)
    if likes:
        like_text = " ".join(likes)
        corpus[0] = _boost_profile(f"{profile_text} {like_text}", topic_weights)
    vectorizer = TfidfVectorizer(
        stop_words="english",
        max_features=100_000,
        ngram_range=(1, 3),
        lowercase=True,
        sublinear_tf=True,
        min_df=2,
    )
    X = vectorizer.fit_transform(corpus)
    prof_vec = X[0]
    item_vecs = X[1:]
    sims = cosine_similarity(prof_vec, item_vecs).ravel()
    penalty = np.zeros_like(sims)
    if dislikes:
        try:
            dislike_corpus = [_boost_profile(t, topic_weights) for t in dislikes]
            D = vectorizer.transform(dislike_corpus)
            dcent = D.mean(axis=0)
            penalty = cosine_similarity(item_vecs, dcent).ravel()
        except Exception:
            pass
    ranked = []
    for idx, (it, s_pos) in enumerate(zip(items, sims)):
        item_text = corpus[idx + 1]
        prior = _topic_prior(item_text, topic_weights)
        s_neg = penalty[idx] if len(dislikes) else 0.0
        final = float(s_pos) - BETA_DISLIKE * float(s_neg) + prior
        ranked.append((it, float(final)))
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked
