"""
Sparse BM25 Keyword Search Module using Weaviate Cloud native full-text index.

Optimized for exact keyword matches, official government codes, scheme names:
- "CBRO", "G.O.Ms.No", "Major Head 2202", "Rythu Bharosa"
- Exact fiscal numbers and specific departmental terminology.
"""
import os
import logging
from typing import List, Dict, Any, Optional
import weaviate
from weaviate.classes.query import MetadataQuery, Filter
from app.core.weaviate_client import get_weaviate_client, WEAVIATE_INDEX_NAME

logger = logging.getLogger(__name__)


def bm25_search(
    query: str,
    top_k: int = 10,
    financial_year: Optional[str] = None,
    category: Optional[str] = None,
    client: Optional[weaviate.WeaviateClient] = None
) -> List[Dict[str, Any]]:
    """
    Performs sparse BM25 keyword search using Weaviate's native search index.

    Args:
        query: Exact search query or keywords
        top_k: Number of candidate chunks to return
        financial_year: Optional year filter (e.g. '2026-27', '2021')
        category: Optional category filter (e.g. 'budget_speech', 'finance_manual', 'guidelines_circulars')
        client: Optional existing WeaviateClient instance

    Returns:
        List of structured result dictionaries with BM25 score and provenance.
    """
    close_client = False
    if client is None:
        client = get_weaviate_client()
        close_client = True

    try:
        collection = client.collections.get(WEAVIATE_INDEX_NAME)

        # 1. Build metadata filters if specified
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

        # 2. Query Weaviate BM25 on content property
        response = collection.query.bm25(
            query=query,
            query_properties=["content", "title"],
            filters=combined_filter,
            limit=top_k,
            return_metadata=MetadataQuery(score=True),
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

        results = []
        for obj in response.objects:
            p = obj.properties
            bm25_score = obj.metadata.score if obj.metadata else 0.0

            results.append({
                "weaviate_id": str(obj.uuid),
                "document_id": p.get("document_id"),
                "chunk_index": p.get("chunk_index"),
                "title": p.get("title"),
                "category": p.get("category"),
                "financial_year": p.get("financial_year"),
                "language": p.get("language", "english"),
                "page_number": p.get("page_number"),
                "content": p.get("content"),
                "score": float(bm25_score),
                "bm25_score": float(bm25_score),
                "retrieval_method": "bm25"
            })

        logger.info(f"BM25 search returned {len(results)} results for query: '{query[:60]}...'")
        return results

    finally:
        if close_client and client:
            client.close()


if __name__ == "__main__":
    test_kw = "Comprehensive Budget Release Order CBRO"
    res = bm25_search(test_kw, top_k=3)
    print(f"\nBM25 Search Results for: '{test_kw}'")
    for r in res:
        print(f"[{r['category']}] {r['title']} ({r['financial_year']}) | Page {r['page_number']} | BM25 Score: {r['score']:.4f}")
        print(f"  Snippet: {r['content'][:150]}...\n")
