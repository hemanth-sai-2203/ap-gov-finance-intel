"""
Unified Retrieval Engine for AP Government Finance Intelligence Platform.

Single entry-point for Phase 2:
  `retrieve_evidence(query: str, top_k: int = 5, ...)`

Coordinates:
  1. Query Router (classifies intent and extracts entities)
  2. SQL Engine (queries structured Supabase financial_records if numerical)
  3. Hybrid Search (Weaviate Dense Vector + BM25 with metadata filtering)
  4. Cross-Encoder Reranker (re-scores passages for maximum precision)
  5. Evidence Packager (builds structured provenance bundle for Phase 3 LLM Generation)
"""
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

from app.search.query_router import route_query, QueryType
from app.search.hybrid_search import hybrid_search
from app.core.weaviate_client import get_weaviate_client
from app.search.vector_search import vector_search
from app.search.bm25_search import bm25_search
from app.search.sql_engine import (
    get_department_allocation,
    get_total_budget_by_year,
    compare_department_across_years,
    get_top_departments_by_allocation
)

logger = logging.getLogger(__name__)


@dataclass
class RetrievedPassage:
    rank: int
    content: str
    title: str
    category: str
    financial_year: str
    page_number: int
    weaviate_id: str
    document_id: Optional[int]
    rerank_score: float
    retrieval_method: str
    source_url: Optional[str] = None


@dataclass
class EvidenceBundle:
    query: str
    query_type: str
    routing_metadata: Dict[str, Any]
    passages: List[RetrievedPassage] = field(default_factory=list)
    sql_records: List[Dict[str, Any]] = field(default_factory=list)
    sql_aggregations: Optional[Dict[str, Any]] = None
    total_evidence_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def get_context_text(self, max_passages: int = 5) -> str:
        """
        Formats retrieved passages and SQL records into a clean context string
        ready for Phase 3 LLM prompt injection.
        """
        sections = []

        # 1. Structured SQL context (if any)
        if self.sql_records:
            sections.append("=== STRUCTURED FINANCIAL DATA (VERIFIED SQL) ===")
            for r in self.sql_records:
                yr = r.get("financial_year", "N/A")
                dept = r.get("department", "N/A")
                be = r.get("budget_estimate_cr", "N/A")
                re = r.get("revised_estimate_cr", "N/A")
                sections.append(f"Department: {dept} | Year: {yr} | Budget Estimate: Rs. {be} Cr | Revised: Rs. {re} Cr")

        if self.sql_aggregations:
            sections.append("=== AGGREGATE SUMMARY (SQL) ===")
            for k, v in self.sql_aggregations.items():
                sections.append(f"{k}: {v}")

        # 2. Text Passages from Weaviate Reranker
        if self.passages:
            sections.append("\n=== OFFICIAL GOVERNMENT DOCUMENT CITATIONS ===")
            for p in self.passages[:max_passages]:
                header = f"[{p.rank}] Source: \"{p.title}\" | Category: {p.category} | Year: {p.financial_year} | Page: {p.page_number} (Relevance Score: {p.rerank_score:.3f})"
                sections.append(f"{header}\n\"{p.content}\"\n")

        return "\n".join(sections)


def retrieve_evidence(
    query: str,
    top_k: int = 5,
    force_year: Optional[str] = None,
    force_category: Optional[str] = None,
    alpha: float = 0.65,
    use_reranker: bool = True
) -> EvidenceBundle:
    """
    Main retrieval coordinator function.

    Args:
        query: Natural language user question
        top_k: Number of highest-relevance passages to return
        force_year: Optional manual override for financial_year
        force_category: Optional manual override for category
        alpha: Hybrid search dense/sparse ratio (0.65 default)
        use_reranker: Apply Cross-Encoder reranking

    Returns:
        EvidenceBundle containing structured passages, SQL data, and routing metadata.
    """
    # 1. Route query and extract entities
    routing = route_query(query)
    q_type = routing["query_type"]
    year = force_year or routing["primary_year"]
    category = force_category or routing["category_filter"]
    dept = routing["department"]

    evidence = EvidenceBundle(
        query=query,
        query_type=q_type.value,
        routing_metadata=routing
    )

    client = None
    try:
        # 2. Execute SQL retrieval if numerical lookup or hybrid
        if routing["requires_sql"]:
            try:
                if q_type == QueryType.COMPARISON and dept:
                    evidence.sql_records = compare_department_across_years(dept)
                elif dept:
                    evidence.sql_records = get_department_allocation(dept, financial_year=year)
                elif year and "total" in query.lower():
                    evidence.sql_aggregations = get_total_budget_by_year(year)
            except Exception as e:
                logger.warning(f"SQL execution encountered notice (table may be unpopulated): {e}")

        # 3. Execute Hybrid / Vector retrieval if textual narrative or hybrid
        if routing["requires_vector"]:
            client = get_weaviate_client()
            raw_results = hybrid_search(
                query=query,
                top_k=top_k,
                alpha=alpha,
                financial_year=year,
                category=category,
                use_reranker=use_reranker,
                client=client
            )

            # Convert to structured RetrievedPassage dataclass
            for rank, r in enumerate(raw_results, 1):
                clean_t = " ".join((r.get("title") or "Official AP Government Document").split())
                p = RetrievedPassage(
                    rank=rank,
                    content=r.get("content", ""),
                    title=clean_t,
                    category=r.get("category", "uncategorized"),
                    financial_year=r.get("financial_year", "N/A"),
                    page_number=int(r.get("page_number") or 1),
                    weaviate_id=r.get("weaviate_id", ""),
                    document_id=r.get("document_id"),
                    rerank_score=float(r.get("rerank_score", r.get("score", 0.0))),
                    retrieval_method=r.get("retrieval_method", "hybrid"),
                    source_url=r.get("source_url")
                )
                evidence.passages.append(p)

        evidence.total_evidence_count = len(evidence.passages) + len(evidence.sql_records)
        return evidence

    finally:
        if client:
            client.close()


if __name__ == "__main__":
    test_queries = [
        "What are the rules regarding re-appropriation of budget funds?",
        "What are the guidelines for Comprehensive Budget Release Order CBRO?",
        "How much was allocated to farmers welfare in 2021 budget?"
    ]

    for q in test_queries:
        print("\n" + "=" * 75)
        print(f"QUERY: \"{q}\"")
        print("=" * 75)
        bundle = retrieve_evidence(q, top_k=2)
        print(f"Routing: Type={bundle.query_type} | Year={bundle.routing_metadata['primary_year']} | Cat={bundle.routing_metadata['category_filter']}")
        print(f"Retrieved Passages: {len(bundle.passages)}")
        for p in bundle.passages:
            print(f"  [{p.rank}] {p.title} ({p.financial_year}) | Page {p.page_number} | Rerank Score: {p.rerank_score:.4f}")
            print(f"      \"{p.content[:150]}...\"")
