"""
FastAPI REST Endpoints Verification Suite with In-Memory SQLite Mock Fixture.
"""
import sys
import os
import unittest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import Base, get_db
from app.db.models import DocumentModel, DocumentChunkModel, FinancialRecordModel
from app.main import app

# In-memory SQLite for reliable, isolated, offline unit testing
TEST_DATABASE_URL = "sqlite:///:memory:"
test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


class TestFastAPIEndpoints(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=test_engine)
        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

        # Seed test records
        db = TestingSessionLocal()
        doc = DocumentModel(
            title="AP Budget in Brief 2026-27",
            category="budget_volumes",
            financial_year="2026-27",
            language="english",
            source_url="https://finance.ap.gov.in/test.pdf",
            total_pages=50,
            total_chunks=120,
            status="processed"
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)

        record = FinancialRecordModel(
            financial_year="2026-27",
            department="School Education",
            scheme_name="General Education",
            head_of_account="2202",
            budget_estimate_cr=32000.50,
            revised_estimate_cr=28500.00,
            actual_expenditure_cr=26100.25,
            source_document_id=doc.id
        )
        db.add(record)
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        Base.metadata.drop_all(bind=test_engine)
        app.dependency_overrides.clear()

    def test_ui_root_endpoint(self):
        """Verify GET / returns the Portal UI HTML."""
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_ui_alias_endpoint(self):
        """Verify GET /ui returns the Portal UI HTML."""
        r = self.client.get("/ui")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/html", r.headers.get("content-type", ""))

    def test_health_endpoint(self):
        """Verify GET /health returns system status."""
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data.get("status"), "healthy")
        self.assertIn("database", data)
        self.assertEqual(data["database"]["total_documents"], 1)

    def test_stats_endpoint(self):
        """Verify GET /api/stats returns document count distribution."""
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["total_documents"], 1)
        self.assertIn("budget_volumes", data["categories_distribution"])

    def test_documents_list_endpoint(self):
        """Verify GET /api/documents returns documents array."""
        r = self.client.get("/api/documents")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("documents", data)
        self.assertEqual(len(data["documents"]), 1)
        self.assertEqual(data["documents"][0]["financial_year"], "2026-27")

    def test_budget_total_endpoint(self):
        """Verify GET /api/budget/total returns SQL aggregations."""
        r = self.client.get("/api/budget/total?financial_year=2026-27")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn("financial_year", data)
        self.assertEqual(data["financial_year"], "2026-27")
        self.assertEqual(data["total_budget_estimate_cr"], 32000.50)


if __name__ == "__main__":
    unittest.main()
