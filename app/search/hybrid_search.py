"""
Hybrid Retrieval Engine: Dense Vector + Sparse BM25 with Reciprocal Rank Fusion (RRF) and Cross-Encoder Reranking.

Pipeline:
  Query
    │
    ├─── Weaviate Native Hybrid Search (alpha=0.65 dense, 0.35 sparse)
    │    (or independent Vector + BM25 parallel runs)
    │
    ▼
  Reciprocal Rank Fusion (RRF) & Candidate Deduplication
    │
    ▼
  Cross-Encoder Reranker (ms-marco-MiniLM-L-6-v2)
    │
    ▼
  Top-K Highest Quality Evidence Passages with Full Provenance
"""
import os
import logging
from typing import List, Dict, Any, Optional
import weaviate
from weaviate.classes.query import MetadataQuery, Filter

from app.core.weaviate_client import get_weaviate_client, WEAVIATE_INDEX_NAME
from app.ingestion.embedder import embed_texts
from app.search.vector_search import vector_search
from app.search.bm25_search import bm25_search
from app.search.reranker import rerank_candidates

logger = logging.getLogger(__name__)


def reciprocal_rank_fusion(
    result_lists: List[List[Dict[str, Any]]],
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    Combines multiple ranked lists using Reciprocal Rank Fusion (RRF).

    RRF score = sum(1 / (k + rank_i)) for each candidate across result sets.
    Scale-independent, parameter-free fusion.
    """
    rrf_scores: Dict[str, float] = {}
    candidate_map: Dict[str, Dict[str, Any]] = {}
    methods_seen: Dict[str, set] = {}

    for r_list in result_lists:
        for rank, item in enumerate(r_list, start=1):
            key = item.get("weaviate_id") or f"{item.get('document_id')}_{item.get('chunk_index')}"
            rrf_scores[key] = rrf_scores.get(key, 0.0) + (1.0 / (k + rank))
            
            if key not in candidate_map:
                candidate_map[key] = dict(item)
                methods_seen[key] = {item.get("retrieval_method", "unknown")}
            else:
                methods_seen[key].add(item.get("retrieval_method", "unknown"))

    # Sort by RRF score descending
    sorted_keys = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    fused_results = []

    for key in sorted_keys:
        item = candidate_map[key]
        item["rrf_score"] = rrf_scores[key]
        # Label hybrid if retrieved by multiple mechanisms
        if len(methods_seen[key]) > 1:
            item["retrieval_method"] = "hybrid_fused"
        fused_results.append(item)

    return fused_results


def hybrid_search(
    query: str,
    top_k: int = 5,
    alpha: float = 0.65,
    candidate_pool_size: int = 15,
    financial_year: Optional[str] = None,
    category: Optional[str] = None,
    use_reranker: bool = True,
    client: Optional[weaviate.WeaviateClient] = None
) -> List[Dict[str, Any]]:
    """
    Executes full hybrid search pipeline:
    1. Weaviate native hybrid query (Dense Vector + BM25)
    2. Optional fallback/supplemental RRF fusion
    3. Cross-Encoder Reranker for top-K selection

    Args:
        query: User search query
        top_k: Number of final reranked passages to return
        alpha: Weight between dense vector (1.0) and sparse BM25 (0.0). Default 0.65.
        candidate_pool_size: Number of initial candidates to pull before reranking
        financial_year: Optional filter for financial year
        category: Optional filter for category
        use_reranker: Whether to apply Cross-Encoder reranking
        client: Optional existing WeaviateClient

    Returns:
        List of top-k ranked passages with complete citation provenance.
    """
    close_client = False
    if client is None:
        client = get_weaviate_client()
        close_client = True

    try:
        collection = client.collections.get(WEAVIATE_INDEX_NAME)

        # 1. Generate 768-dim query vector for the dense component
        query_vector = embed_texts([query])[0]

        # 2. Build metadata filters if specified
        filters = []
        if financial_year:
            filters.append(Filter.by_property("financial_year").equal(financial_year))
        if category:
            filters.append(Filter.by_property("category").equal(category))

        combined_filter = None
        if len(filters) == 1:
            combined_filter = filters[0]
        elif len(filters) > 1:
            combined_filter = Filter.all_of(filters)

        # 3. Native Weaviate Hybrid Query
        response = collection.query.hybrid(
            query=query,
            vector=query_vector,
            alpha=alpha,
            filters=combined_filter,
            limit=candidate_pool_size,
            return_metadata=MetadataQuery(score=True, distance=True),
            return_properties=[
                "document_id",
                "supabase_chunk_id",
                "title",
                "category",
                "financial_year",
                "language",
                "page_number",
                "chunk_index",
                "content"
            ]
        )

        # Fallback to unrestricted search if filter produced zero candidates
        if not response.objects and combined_filter is not None:
            logger.info(f"Filtered search ({combined_filter}) returned 0 candidates. Falling back to open hybrid search...")
            response = collection.query.hybrid(
                query=query,
                vector=query_vector,
                alpha=alpha,
                filters=None,
                limit=candidate_pool_size,
                return_metadata=MetadataQuery(score=True, distance=True),
                return_properties=[
                    "document_id",
                    "supabase_chunk_id",
                    "title",
                    "category",
                    "financial_year",
                    "language",
                    "page_number",
                    "chunk_index",
                    "content"
                ]
            )

        candidates = []
        for obj in response.objects:
            p = obj.properties
            score = obj.metadata.score if obj.metadata else 0.0
            distance = obj.metadata.distance if obj.metadata else None

            candidates.append({
                "weaviate_id": str(obj.uuid),
                "document_id": p.get("document_id"),
                "chunk_index": p.get("chunk_index"),
                "title": p.get("title"),
                "category": p.get("category"),
                "financial_year": p.get("financial_year"),
                "language": p.get("language", "english"),
                "page_number": p.get("page_number"),
                "content": p.get("content"),
                "score": float(score) if score is not None else 0.0,
                "distance": distance,
                "retrieval_method": "hybrid"
            })

        logger.info(f"Hybrid candidate search retrieved {len(candidates)} candidates for: '{query[:60]}...'")

        # 4. Cross-Encoder Reranking
        if use_reranker and candidates:
            final_results = rerank_candidates(query, candidates, top_k=top_k)
        else:
            final_results = candidates[:top_k]

        return final_results

    finally:
        if close_client and client:
            client.close()


if __name__ == "__main__":
    q = "What are the rules and powers for reappropriation of budget funds in Andhra Pradesh?"
    results = hybrid_search(q, top_k=3)
    print(f"\nHybrid Search + Reranker Results for: '{q}'")
    for idx, r in enumerate(results, 1):
        print(f"[{idx}] [{r['category']}] {r['title']} ({r['financial_year']}) | Page {r['page_number']}")
        print(f"    Rerank Score: {r.get('rerank_score', r.get('score', 0)):.4f} | Method: {r['retrieval_method']}")
        print(f"    Snippet: {r['content'][:180]}...\n")
