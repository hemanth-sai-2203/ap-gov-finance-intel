"""
Unified Query Pipeline for AP Government Finance Intelligence.

Wires together:
1. Phase 2 Unified Retrieval Engine (`app.search.engine.retrieve_evidence`)
   - Intent Routing (SQL, RAG, Hybrid, Comparison)
   - Dense Vector Search (Weaviate Cloud 768-dim)
   - Sparse BM25 Search (Weaviate Cloud)
   - Cross-Encoder Reranker (`ms-marco-MiniLM-L-6-v2`)
   - Deterministic SQL Engine (Supabase PostgreSQL)
2. Phase 3 Grounded Generation Engine (`app.core.llm_engine.generate_answer`)
   - Anti-hallucination system prompt
   - Google Gemini 2.5 Flash
   - Structured inline citations
"""
import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.search.engine import retrieve_evidence, EvidenceBundle
from app.core.llm_engine import generate_answer

logger = logging.getLogger(__name__)


def run_query(
    query: str,
    financial_year: Optional[str] = None,
    category: Optional[str] = None,
    department: Optional[str] = None,
    top_k: int = 5,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """
    Executes the full end-to-end intelligence query pipeline:
    User Question -> Hybrid Retrieval & Reranking -> Gemini Synthesis -> Citations.

    Args:
        query: Natural language question
        financial_year: Optional filter for a specific year (e.g. '2026-27')
        category: Optional filter for document type ('budget_speech', 'finance_manual', 'guidelines_circulars')
        department: Optional department name hint
        top_k: Number of highest-ranked passages to pass as context
        db: Optional SQLAlchemy database session

    Returns:
        Structured response dictionary with answer, citations, evidence, and routing metadata.
    """
    logger.info(f"Executing End-to-End Query Pipeline for: '{query[:80]}'...")

    # Step 1: Execute Unified Retrieval & Reranking (Phase 2)
    evidence: EvidenceBundle = retrieve_evidence(
        query=query,
        top_k=top_k,
        force_year=financial_year,
        force_category=category
    )

    # Step 2: Synthesize Grounded Answer with Gemini 2.5 Flash (Phase 3)
    synthesis_result = generate_answer(
        query=query,
        evidence=evidence
    )

    # Step 3: Format final response for API clients
    return {
        "query": query,
        "answer": synthesis_result["answer"],
        "citations": synthesis_result["citations"],
        "query_type": evidence.query_type,
        "routing_metadata": evidence.routing_metadata,
        "retrieved_passages_count": len(evidence.passages),
        "sql_records_count": len(evidence.sql_records),
        "model_used": synthesis_result.get("model_used", "gemini-2.5-flash"),
        "engine": "Hybrid BM25 + 768-dim Vector + Cross-Encoder Reranker + Gemini 2.5 Flash"
    }
