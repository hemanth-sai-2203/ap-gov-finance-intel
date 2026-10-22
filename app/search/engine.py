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
from app.core.text_decoder import decode_shifted_pdf_text, sanitize_display_title
from app.search.sql_engine import (
    get_department_allocation,
    get_scheme_allocation,
    get_total_budget_by_year,
    get_total_budget_all_years,
    compare_department_across_years,
    get_top_departments_by_allocation,
    get_document_catalog
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

        # 1. Catalog / Metadata records
        sql_lines = []
        if self.query_type == "catalog" and self.sql_records:
            sql_lines.append("=== OFFICIAL AP GOVERNMENT DOCUMENT CATALOG ===")
            for r in self.sql_records[:30]:
                title = r.get("title", "Document")
                cat = r.get("category", "N/A")
                yr = r.get("financial_year", "N/A")
                pages = r.get("total_pages", "N/A")
                sql_lines.append(f"• Document: {title} | Category: {cat} | Financial Year: {yr} | Pages: {pages}")

        # 2. Structured SQL context (financial data)
        elif self.sql_records:
            sql_lines.append("=== STRUCTURED FINANCIAL DATA (VERIFIED SQL) ===")
            for r in self.sql_records:
                yr = r.get("financial_year", "N/A")
                dept = r.get("department", "N/A")
                scheme = r.get("scheme_name")
                scheme_str = f" | Scheme: {scheme}" if scheme else " | Scheme: Department-wide / General"
                be = r.get("budget_estimate_cr", "N/A")
                re = r.get("revised_estimate_cr", "N/A")
                sql_lines.append(f"Department: {dept}{scheme_str} | Year: {yr} | Budget Estimate: Rs. {be} Cr | Revised: Rs. {re} Cr")

        if self.sql_aggregations:
            sql_lines.append("=== AGGREGATE SUMMARY (SQL) ===")
            for k, v in self.sql_aggregations.items():
                sql_lines.append(f"{k}: {v}")

        # 3. Text Passages from Weaviate Reranker
        passage_lines = []
        if self.passages:
            passage_lines.append("=== OFFICIAL GOVERNMENT DOCUMENT CITATIONS ===")
            for p in self.passages[:max_passages]:
                clean_title = sanitize_display_title(p.title or "Official AP Government Document", category=p.category, financial_year=p.financial_year)
                decoded_content = decode_shifted_pdf_text(p.content or "")
                header = f"[{p.rank}] Source: \"{clean_title}\" | Category: {p.category} | Year: {p.financial_year} | Page: {p.page_number} (Relevance Score: {p.rerank_score:.3f})"
                passage_lines.append(f"{header}\n\"{decoded_content}\"\n")

        # Prioritize passages when asking about schemes or policy narratives
        is_scheme_or_narrative = bool(self.routing_metadata.get("scheme")) or self.query_type in ["rag", "hybrid"]
        if is_scheme_or_narrative and passage_lines:
            sections.extend(passage_lines)
            if sql_lines:
                sections.append("\n=== SUPPLEMENTARY TABULAR RECORDS ===")
                sections.extend(sql_lines)
        else:
            if sql_lines:
                sections.extend(sql_lines)
            if passage_lines:
                sections.append("")
                sections.extend(passage_lines)

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
    normalized_query = routing.get("normalized_query", query)
    year = force_year or routing["primary_year"]
    category = force_category or routing["category_filter"]
    dept = routing["department"]
    scheme = routing.get("scheme")
    scheme_kw = routing.get("scheme_keyword")
    is_state_total = routing.get("is_state_total", False)

    evidence = EvidenceBundle(
        query=query,
        query_type=q_type.value if hasattr(q_type, 'value') else str(q_type),
        routing_metadata=routing
    )

    # Fast-path for greetings: Return immediately with no search overhead
    if q_type == QueryType.GREETING:
        return evidence

    try:
        # 2. Execute SQL retrieval if catalog, numerical lookup or hybrid
        if routing["requires_sql"]:
            try:
                if q_type == QueryType.CATALOG:
                    evidence.sql_records = get_document_catalog(category=category, financial_year=year, limit=40)
                elif q_type == QueryType.COMPARISON and dept:
                    evidence.sql_records = compare_department_across_years(dept)
                elif scheme or scheme_kw:
                    target_scheme = scheme_kw or scheme
                    scheme_records = get_scheme_allocation(target_scheme, financial_year=year)
                    if scheme_records:
                        evidence.sql_records = scheme_records
                    elif dept:
                        # Fallback to parent department allocation
                        evidence.sql_records = get_department_allocation(dept, financial_year=year)
                elif is_state_total:
                    if year:
                        evidence.sql_aggregations = get_total_budget_by_year(year)
                    else:
                        evidence.sql_records = get_total_budget_all_years()
                elif dept:
                    evidence.sql_records = get_department_allocation(dept, financial_year=year)
                elif year and is_state_total:
                    evidence.sql_aggregations = get_total_budget_by_year(year)
            except Exception as e:
                logger.warning(f"SQL execution encountered notice: {e}")

        # 3. Execute Hybrid / Vector retrieval if textual narrative or hybrid
        if routing["requires_vector"]:
            try:
                # Use enriched expanded query if available for enhanced recall
                search_query = routing.get("expanded_queries", [normalized_query])[-1] if routing.get("expanded_queries") else normalized_query
                raw_results = hybrid_search(
                    query=search_query,
                    top_k=top_k,
                    alpha=alpha,
                    financial_year=year,
                    category=category,
                    use_reranker=use_reranker
                )
            except Exception as e:
                logger.warning(f"Hybrid search invocation failed ({e}), falling back to BM25 search...")
                try:
                    raw_results = bm25_search(query=normalized_query, top_k=top_k, financial_year=year, category=category)
                except Exception as bm_err:
                    logger.error(f"BM25 fallback search also failed: {bm_err}")
                    raw_results = []

            # Convert to structured RetrievedPassage dataclass with text decoding and title sanitization
            for rank, r in enumerate(raw_results, 1):
                raw_t = r.get("title") or "Official AP Government Document"
                raw_cat = r.get("category", "uncategorized")
                raw_fy = r.get("financial_year", "N/A")
                clean_t = sanitize_display_title(raw_t, category=raw_cat, financial_year=raw_fy)
                
                # Unscramble +1 shifted font encoding
                decoded_content = decode_shifted_pdf_text(r.get("content", ""))

                p = RetrievedPassage(
                    rank=rank,
                    content=decoded_content,
                    title=clean_t,
                    category=raw_cat,
                    financial_year=raw_fy,
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
        pass


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
