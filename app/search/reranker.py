"""
Cross-Encoder Reranker Module for High-Precision Document Passage Re-ranking.

Uses a pretrained Cross-Encoder model (ms-marco-MiniLM-L-6-v2) to evaluate
joint deep attention between (Query, Document Passage) pairs.

Significantly boosts Precision@K over bi-encoder similarity alone.
"""
import logging
from typing import List, Dict, Any, Optional
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker_instance: Optional[CrossEncoder] = None


def get_reranker(model_name: str = DEFAULT_RERANKER_MODEL) -> Optional[CrossEncoder]:
    """
    Singleton factory for CrossEncoder reranker.
    Loads on demand and reuses across queries.
    Gracefully falls back to None if model download fails or memory is tight.
    """
    global _reranker_instance
    if _reranker_instance is None:
        try:
            logger.info(f"Loading cross-encoder reranker: {model_name} (CPU execution)...")
            try:
                _reranker_instance = CrossEncoder(model_name, max_length=512, local_files_only=True)
            except Exception:
                _reranker_instance = CrossEncoder(model_name, max_length=512)
            logger.info(f"[OK] Cross-encoder reranker '{model_name}' loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load CrossEncoder model ({e}). Using fallback ranking.")
            return None
    return _reranker_instance


def rerank_candidates(
    query: str,
    candidates: List[Dict[str, Any]],
    top_k: int = 5,
    content_key: str = "content"
) -> List[Dict[str, Any]]:
    """
    Reranks a list of candidate chunk dictionaries against the user query.
    Falls back gracefully to original candidate ranking if model is unavailable.
    """
    if not candidates:
        return []

    # If only 1 candidate, return it directly
    if len(candidates) == 1:
        candidates[0]["rerank_score"] = 1.0
        return candidates

    try:
        reranker = get_reranker()
        if reranker is None:
            return candidates[:top_k]

        # Form (query, passage) pairs
        pairs = [(query, c.get(content_key, "")) for c in candidates]
        scores = reranker.predict(pairs)

        for i, candidate in enumerate(candidates):
            candidate["rerank_score"] = float(scores[i])

        # Sort descending by rerank score
        reranked = sorted(candidates, key=lambda x: x["rerank_score"], reverse=True)
        return reranked[:top_k]

    except Exception as e:
        logger.error(f"Error during cross-encoder reranking: {e}")
        return candidates[:top_k]


if __name__ == "__main__":
    q = "What is the procedure for Comprehensive Budget Release Order?"
    sample_candidates = [
        {"title": "Doc A", "content": "The weather in Andhra Pradesh is pleasant.", "score": 0.5},
        {"title": "Doc B", "content": "Guidelines for issue of Comprehensive Budget Release Order (CBRO) and distribution of expenditure.", "score": 0.8},
        {"title": "Doc C", "content": "Annual administrative report on general tourism development.", "score": 0.4}
    ]
    ranked = rerank_candidates(q, sample_candidates, top_k=2)
    print(f"\nReranked Results for: '{q}'")
    for r in ranked:
        print(f"Title: {r['title']} | Rerank Score: {r['rerank_score']:.4f}")
        print(f"Content: {r['content']}\n")
