"""
Search Pipeline & Query Router Test Suite.
Validates:
1. Query Router classification (SQL, RAG, Hybrid, Comparison)
2. Entity extraction (financial year, department, category)
3. Cross-encoder reranker scoring logic
4. SQL engine aggregation queries
"""
import sys
import os
import unittest

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.search.query_router import route_query, QueryType
from app.search.reranker import rerank_candidates
from app.search.sql_engine import get_total_budget_by_year, get_department_allocation, get_top_departments_by_allocation


class TestSearchPipeline(unittest.TestCase):

    def test_query_router_sql_classification(self):
        """Verify deterministic SQL routing for numerical queries."""
        r1 = route_query("What was the education budget in 2026-27?")
        self.assertEqual(r1["query_type"], QueryType.SQL)
        self.assertEqual(r1["primary_year"], "2026-27")
        self.assertEqual(r1["department"], "School Education")

        r2 = route_query("How much was allocated to agriculture in 2024-25?")
        self.assertEqual(r2["query_type"], QueryType.SQL)
        self.assertEqual(r2["primary_year"], "2024-25")
        self.assertEqual(r2["department"], "Agriculture")

    def test_query_router_rag_classification(self):
        """Verify RAG routing for policy and procedural questions."""
        r1 = route_query("What are the powers of sanction under the AP budget manual?")
        self.assertIn(r1["query_type"], [QueryType.RAG, QueryType.HYBRID])
        self.assertEqual(r1["category_filter"], "finance_manual")

        r2 = route_query("Explain the guidelines for Comprehensive Budget Release Order CBRO.")
        self.assertIn(r2["query_type"], [QueryType.RAG, QueryType.HYBRID])

    def test_query_router_comparison_classification(self):
        """Verify multi-year comparison query routing."""
        r1 = route_query("Compare education spending between 2024-25 and 2026-27.")
        self.assertEqual(r1["query_type"], QueryType.COMPARISON)
        self.assertIn("2024-25", r1["all_years"])
        self.assertIn("2026-27", r1["all_years"])

    def test_reranker_scoring(self):
        """Verify cross-encoder reorders passages based on relevance."""
        query = "procedure for issue of Comprehensive Budget Release Order"
        candidates = [
            {"title": "Unrelated", "content": "Weather report for southern districts.", "score": 0.5},
            {"title": "Target Match", "content": "Guidelines for issue of Comprehensive Budget Release Order CBRO and expenditure release.", "score": 0.6},
            {"title": "Somewhat Relevant", "content": "General administrative procedures for treasury officers.", "score": 0.4}
        ]
        reranked = rerank_candidates(query, candidates, top_k=2)
        self.assertEqual(len(reranked), 2)
        self.assertEqual(reranked[0]["title"], "Target Match")
        self.assertGreater(reranked[0]["rerank_score"], reranked[1]["rerank_score"])

    def test_sql_engine_output_schema(self):
        """Verify SQL engine queries return expected dictionary structure."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.db.session import Base
        from app.db.models import FinancialRecordModel

        engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine)
        db = Session()

        db.add(FinancialRecordModel(
            financial_year="2026-27",
            department="School Education",
            scheme_name="General Education",
            head_of_account="2202",
            budget_estimate_cr=32000.50,
            revised_estimate_cr=28500.00,
            actual_expenditure_cr=26100.25
        ))
        db.commit()

        total = get_total_budget_by_year("2026-27", db=db)
        self.assertIsInstance(total, dict)
        self.assertIn("financial_year", total)
        self.assertIn("total_budget_estimate_cr", total)
        self.assertEqual(total["financial_year"], "2026-27")
        self.assertEqual(total["total_budget_estimate_cr"], 32000.50)

        allocs = get_department_allocation("Education", financial_year="2026-27", db=db)
        self.assertEqual(len(allocs), 1)
        self.assertEqual(allocs[0]["department"], "School Education")

        db.close()


if __name__ == "__main__":
    unittest.main()
