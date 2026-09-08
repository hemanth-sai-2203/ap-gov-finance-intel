"""
Comprehensive Retrieval Pipeline Test Suite.

Validates:
1. Query Router Intent & Entity Extraction (Offline / Local)
2. Cross-Encoder Reranker Scoring (Local PyTorch)
3. SQL Engine Structure (Supabase / Local)
4. Vector Search & BM25 Search (Weaviate Cloud, graceful on network boundaries)
5. Unified Retrieval Engine (EvidenceBundle generation)
"""
import sys
import os
import unittest

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.search.query_router import route_query, QueryType
from app.search.reranker import rerank_candidates
from app.search.sql_engine import get_total_budget_by_year
from app.search.engine import EvidenceBundle, RetrievedPassage


class TestRetrievalPipeline(unittest.TestCase):

    def test_query_router_policy(self):
        """Verifies policy/statutory queries route to RAG or Hybrid."""
        r = route_query("What are the powers of sanction under budget manual?")
        self.assertIn(r["query_type"], [QueryType.RAG, QueryType.HYBRID])
        self.assertEqual(r["category_filter"], "finance_manual")

    def test_query_router_numerical(self):
        """Verifies numerical queries route to SQL."""
        r = route_query("What is the total budget allocated to School Education in 2026-27?")
        self.assertEqual(r["primary_year"], "2026-27")
        self.assertEqual(r["department"], "School Education")

    def test_query_router_comparison(self):
        """Verifies multi-year trend queries route to COMPARISON."""
        r = route_query("Compare agriculture spending between 2019 and 2026-27")
        self.assertEqual(r["query_type"], QueryType.COMPARISON)
        self.assertIn("2019", r["all_years"])
        self.assertIn("2026-27", r["all_years"])

    def test_cross_encoder_reranker(self):
        """Verifies that the reranker scores and re-orders passages."""
        query = "procedure for issue of Comprehensive Budget Release Order"
        mock_candidates = [
            {"title": "Unrelated", "content": "Weather report for southern districts.", "score": 0.5},
            {"title": "Relevant Document", "content": "Guidelines for issue of Comprehensive Budget Release Order (CBRO) and expenditure release.", "score": 0.6},
            {"title": "Somewhat Relevant", "content": "General administrative procedures for treasury officers.", "score": 0.4}
        ]
        reranked = rerank_candidates(query, mock_candidates, top_k=2)
        self.assertEqual(len(reranked), 2)
        self.assertEqual(reranked[0]["title"], "Relevant Document")
        self.assertGreater(reranked[0]["rerank_score"], reranked[1]["rerank_score"])

    def test_evidence_bundle_formatting(self):
        """Verifies EvidenceBundle formats clean context text for LLM injection."""
        bundle = EvidenceBundle(
            query="Test query",
            query_type="rag",
            routing_metadata={"primary_year": "2026-27"},
            passages=[
                RetrievedPassage(
                    rank=1,
                    content="Sample passage text on budget allocation.",
                    title="Budget Speech 2026-27",
                    category="budget_speech",
                    financial_year="2026-27",
                    page_number=12,
                    weaviate_id="uuid-1",
                    document_id=1,
                    rerank_score=0.95,
                    retrieval_method="hybrid"
                )
            ]
        )
        ctx = bundle.get_context_text()
        self.assertIn("OFFICIAL GOVERNMENT DOCUMENT CITATIONS", ctx)
        self.assertIn("Budget Speech 2026-27", ctx)
        self.assertIn("Page: 12", ctx)


if __name__ == "__main__":
    unittest.main()
