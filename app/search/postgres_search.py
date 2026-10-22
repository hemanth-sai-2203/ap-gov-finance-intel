"""
PostgreSQL Full-Text + Chunk-Level Search Fallback.

This module activates when Weaviate Cloud is unavailable (paused, expired, or network failure).
It performs keyword-based full-text search directly over the `document_chunks` table in Supabase
using PostgreSQL's native ILIKE (case-insensitive substring match) as a degraded-but-functional
fallback so the platform continues to serve queries even when the vector database is down.

Limitations vs Weaviate:
  - No dense semantic similarity (no embeddings)
  - No BM25 scoring
  - Lower retrieval quality for semantic queries
  - Cross-encoder reranking is still applied if enabled

This is intentionally a FALLBACK — the system should recover to full Weaviate search once
the cloud cluster is resumed.
"""
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import or_, func

from app.db.session import SessionLocal
from app.db.models import DocumentChunkModel, DocumentModel

logger = logging.getLogger(__name__)


COMMON_STOP_WORDS = {
    "what", "which", "where", "when", "who", "whom", "whose", "why", "how",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "can", "will", "just", "should", "now", "the", "and", "for", "with", "from",
    "into", "during", "including", "until", "against", "among", "throughout",
    "despite", "towards", "upon", "concerning", "to", "in", "of", "by", "at",
    "on", "are", "is", "was", "were", "be", "been", "being", "have", "has",
    "had", "having", "do", "does", "did", "doing", "you", "your", "yours",
    "yourself", "yourselves", "across", "available", "year", "years", "financial",
    "total", "allocated", "allocation", "allocations", "budget", "budgets", "amount",
    "tell", "give", "show", "find", "get", "please"
}


def postgres_hybrid_search(
    query: str,
    top_k: int = 5,
    candidate_pool_size: int = 30,
    financial_year: Optional[str] = None,
    category: Optional[str] = None,
    use_reranker: bool = True,
    db: Optional[Session] = None
) -> List[Dict[str, Any]]:
    """
    Degraded-mode search directly over PostgreSQL document_chunks table.

    Uses ILIKE substring matching across content + title when Weaviate is unavailable.
    Filters out stop-words to prevent false matches on generic pronouns and prepositions.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        # Tokenize query into meaningful content keywords (stripping stop words)
        raw_words = [kw.strip(' ,.:;\'"?!()[]{}') for kw in query.split() if len(kw.strip(' ,.:;\'"?!()[]{}')) > 2]
        content_keywords = [w for w in raw_words if w.lower() not in COMMON_STOP_WORDS]
        
        # If all words were stop words, fall back to non-stop raw words
        search_terms = content_keywords if content_keywords else raw_words
        if not search_terms:
            search_terms = [query]

        # Build keyword conditions: content OR title ILIKE each content keyword
        conditions = []
        for kw in search_terms:
            pattern = f"%{kw}%"
            conditions.append(DocumentChunkModel.content.ilike(pattern))

        # Join to document metadata for provenance + apply category/year filters
        q = (
            db.query(DocumentChunkModel, DocumentModel)
            .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.id)
        )

        if conditions:
            q = q.filter(or_(*conditions))

        if financial_year:
            q = q.filter(DocumentModel.financial_year == financial_year)

        if category:
            q = q.filter(DocumentModel.category == category)

        q = q.limit(candidate_pool_size)
        rows = q.all()

        if not rows and (financial_year or category):
            # Relax filters if no results with constraints
            logger.info("PostgreSQL fallback: No results with filters — retrying without year/category constraints.")
            q2 = (
                db.query(DocumentChunkModel, DocumentModel)
                .join(DocumentModel, DocumentChunkModel.document_id == DocumentModel.id)
            )
            if conditions:
                q2 = q2.filter(or_(*conditions))
            q2 = q2.limit(candidate_pool_size)
            rows = q2.all()

        candidates = []
        for chunk, doc in rows:
            # Score by counting genuine content keyword matches
            content_lower = (chunk.content or "").lower()
            keyword_hits = sum(1 for kw in search_terms if kw.lower() in content_lower)
            if keyword_hits == 0:
                continue

            simple_score = keyword_hits / max(len(search_terms), 1)

            candidates.append({
                "weaviate_id": f"pg_{chunk.id}",
                "document_id": chunk.document_id,
                "chunk_index": chunk.chunk_index,
                "title": doc.title if doc else "Unknown Document",
                "category": doc.category if doc else "unknown",
                "financial_year": doc.financial_year if doc else "N/A",
                "language": doc.language if doc else "english",
                "page_number": chunk.page_number or 1,
                "content": chunk.content or "",
                "score": simple_score,
                "rerank_score": simple_score,
                "source_url": doc.source_url if doc else None,
                "retrieval_method": "postgres_fulltext_fallback"
            })

        logger.warning(
            f"[DEGRADED MODE] PostgreSQL fallback search returned {len(candidates)} candidates "
            f"for: '{query[:60]}' (Weaviate unavailable)"
        )

        if not candidates:
            return []

        # Sort by simple keyword score descending before reranking
        candidates.sort(key=lambda x: x["score"], reverse=True)

        # Apply reranker if enabled and candidates exist
        if use_reranker and candidates:
            try:
                from app.search.reranker import rerank_candidates
                return rerank_candidates(query, candidates, top_k=top_k)
            except Exception as re_err:
                logger.warning(f"Reranker unavailable in fallback mode: {re_err}")
                return candidates[:top_k]

        return candidates[:top_k]

    except Exception as e:
        logger.error(f"PostgreSQL fallback search failed: {e}")
        return []
    finally:
        if close_db:
            db.close()


def postgres_health_check() -> Dict[str, Any]:
    """
    Checks PostgreSQL connectivity and returns document/chunk counts.
    Used by the health endpoint to verify the fallback backend is live.
    """
    try:
        db = SessionLocal()
        doc_count = db.query(func.count(DocumentModel.id)).scalar()
        chunk_count = db.query(func.count(DocumentChunkModel.id)).scalar()
        db.close()
        return {
            "postgres_status": "ok",
            "document_count": doc_count,
            "chunk_count": chunk_count
        }
    except Exception as e:
        return {
            "postgres_status": "error",
            "error": str(e),
            "document_count": 0,
            "chunk_count": 0
        }
