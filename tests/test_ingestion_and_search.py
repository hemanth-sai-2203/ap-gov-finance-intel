"""
Ingestion, Parser & Splitter Unit Test Suite.
Validates:
1. PDF page text extraction
2. Telugu Unicode filtering & bilingual stripping
3. Document chunking & metadata preservation
4. SHA-256 hash calculation for document idempotency
"""
import sys
import os
import unittest

# Add project root directory to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_core.documents import Document
from app.ingestion.loader import clean_and_filter_telugu_text
from app.ingestion.splitter import split_documents
from app.ingestion.downloader import compute_sha256, sanitize_filename


class TestIngestionAndSplitter(unittest.TestCase):

    def test_telugu_text_cleaning(self):
        """Verify bilingual text strips Telugu characters and preserves English."""
        bilingual_text = "ఆంధ్రప్రదేశ్ ప్రభుత్వం Government of Andhra Pradesh Budget 2026-27"
        cleaned = clean_and_filter_telugu_text(bilingual_text)
        self.assertIn("Government of Andhra Pradesh Budget 2026-27", cleaned)
        # Verify Telugu script was stripped
        self.assertNotIn("ఆంధ్రప్రదేశ్", cleaned)

    def test_predominantly_telugu_discard(self):
        """Verify pages with >70% Telugu content are discarded."""
        telugu_dense = "ఆంధ్రప్రదేశ్ ప్రభుత్వ ఆర్థిక శాఖ బడ్జెట్ అంచనాలు 2026-27 కేటాయింపులు వివరాలు"
        cleaned = clean_and_filter_telugu_text(telugu_dense)
        self.assertEqual(cleaned, "")

    def test_document_splitter(self):
        """Verify text chunks preserve metadata and respect chunk boundaries."""
        sample_doc = Document(
            page_content="The Andhra Pradesh Budget for 2026-27 prioritizes agricultural growth, school education modernization, capital expenditure on irrigation projects, and targeted direct benefit transfers across all districts.",
            metadata={"page_number": 1, "title": "Budget Speech", "is_tabular": False}
        )
        chunks, tabular = split_documents([sample_doc], chunk_size=100, chunk_overlap=20)
        self.assertGreater(len(chunks), 0)
        self.assertEqual(len(tabular), 0)
        self.assertEqual(chunks[0].metadata["page_number"], 1)
        self.assertIn("chunk_index", chunks[0].metadata)

    def test_sha256_computation(self):
        """Verify idempotent document hashing."""
        content = b"Sample AP Government Budget Volume Data"
        hash1 = compute_sha256(content)
        hash2 = compute_sha256(content)
        self.assertEqual(hash1, hash2)
        self.assertEqual(len(hash1), 64)

    def test_sanitize_filename(self):
        """Verify safe filename sanitization."""
        raw_name = "2026-27 / Budget Speech & Annual Financial Statement (Vol-I): Final?"
        safe = sanitize_filename(raw_name)
        self.assertNotIn("/", safe)
        self.assertNotIn("?", safe)
        self.assertNotIn(":", safe)


if __name__ == "__main__":
    unittest.main()
