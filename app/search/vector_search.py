import os
import logging
from typing import List, Dict, Any, Optional
import weaviate
from weaviate.classes.query import MetadataQuery, Filter

from app.core.weaviate_client import get_weaviate_client, WEAVIATE_INDEX_NAME
from app.ingestion.embedder import embed_texts

logger = logging.getLogger(__name__)


def vector_search(
    query: str,
    top_k: int = 10,
    financial_year: Optional[str] = None,
    category: Optional[str] = None,
    client: Optional[weaviate.WeaviateClient] = None
) -> List[Dict[str, Any]]:
    """
    Performs dense vector similarity search against Weaviate Cloud.

    Args:
        query: User search query
        top_k: Number of candidate chunks to return
        financial_year: Optional year filter (e.g. '2026-27', '2021')
        category: Optional category filter (e.g. 'budget_speech', 'finance_manual', 'guidelines_circulars')
        client: Optional existing WeaviateClient instance

    Returns:
        List of structured result dictionaries with provenance metadata.
    """
    close_client = False
    if client is None:
        client = get_weaviate_client()
        close_client = True

    try:
        collection = client.collections.get(WEAVIATE_INDEX_NAME)

        # 1. Generate 768-dim query embedding
        query_vector = embed_texts([query])[0]

        # 2. Build metadata filter if specified
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

        # 3. Query Weaviate near_vector
        response = collection.query.near_vector(
            near_vector=query_vector,
            filters=combined_filter,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True, certainty=True),
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
            distance = obj.metadata.distance if obj.metadata else None
            certainty = obj.metadata.certainty if obj.metadata else None

            # Calculate cosine similarity score (1 - distance)
            similarity = 1.0 - distance if distance is not None else certainty

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
                "distance": distance,
                "score": similarity if similarity is not None else 0.0,
                "retrieval_method": "vector"
            })

        logger.info(f"Vector search returned {len(results)} results for query: '{query[:60]}...'")
        return results

    finally:
        if close_client and client:
            client.close()


if __name__ == "__main__":
    test_query = "What are the agricultural investment allocations for farmers?"
    res = vector_search(test_query, top_k=3)
    print(f"\nVector Search Results for: '{test_query}'")
    for r in res:
        print(f"[{r['category']}] {r['title']} ({r['financial_year']}) | Page {r['page_number']} | Score: {r['score']:.4f}")
        print(f"  Snippet: {r['content'][:150]}...\n")
