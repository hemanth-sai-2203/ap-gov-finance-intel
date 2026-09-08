import re
import logging
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ingestion.loader import clean_and_filter_telugu_text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def split_documents(
    documents: List[Document],
    chunk_size: int = 2000,
    chunk_overlap: int = 400,
    skip_tabular: bool = True,
) -> Tuple[List[Document], List[Document]]:
    """
    Splits LangChain Document objects into text chunks for vector embedding.

    Key changes vs previous version:
      - Pages tagged is_tabular=True are separated and returned as tabular_pages
        instead of being chunked. The ingestion pipeline should route these to
        the SQL table extractor, NOT to Weaviate.
      - Boilerplate stripping already happened in loader.py — splitter trusts
        that page_content is already clean.
      - Minimum chunk length raised to 60 chars to avoid embedding tiny fragments.

    Args:
        documents:     LangChain Documents from loader.load_pdf_document()
        chunk_size:    Target max characters per chunk (default 2000)
        chunk_overlap: Overlap chars between adjacent chunks (default 400)
        skip_tabular:  If True, tabular pages are excluded from chunk output
                       and returned separately. If False, everything is chunked.

    Returns:
        (text_chunks, tabular_pages)
        - text_chunks:   List of chunked Documents ready for embedding → Weaviate
        - tabular_pages: List of full-page Documents flagged is_tabular=True,
                         to be routed to SQL table extraction
    """
    tabular_pages: List[Document] = []
    prose_pages:   List[Document] = []

    for doc in documents:
        if skip_tabular and doc.metadata.get("is_tabular", False):
            tabular_pages.append(doc)
        else:
            prose_pages.append(doc)

    logger.info(
        f"Splitting {len(prose_pages)} prose pages (chunk_size={chunk_size}, overlap={chunk_overlap}). "
        f"{len(tabular_pages)} tabular pages routed to SQL extractor."
    )

    if not prose_pages:
        return [], tabular_pages

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
        is_separator_regex=False,
    )

    raw_chunks = splitter.split_documents(prose_pages)
    valid_chunks: List[Document] = []
    chunk_idx = 0

    for chunk in raw_chunks:
        # Re-apply Telugu cleaning (should be a no-op after loader, safety net)
        cleaned = clean_and_filter_telugu_text(chunk.page_content)
        if not cleaned or len(cleaned) < 60:
            continue
        chunk.page_content = cleaned
        chunk.metadata["chunk_index"] = chunk_idx
        valid_chunks.append(chunk)
        chunk_idx += 1

    filtered_count = len(raw_chunks) - len(valid_chunks)
    logger.info(
        f"Generated {len(valid_chunks)} clean text chunks "
        f"(filtered {filtered_count} short/noisy fragments)."
    )
    return valid_chunks, tabular_pages


# ─── Backward-compatible wrapper ──────────────────────────────────────────────
# Older callers (run_ingestion.py, ingest_additional_finance_docs.py) that only
# expect a single list back can use this shim until they are updated.

def split_documents_simple(
    documents: List[Document],
    chunk_size: int = 2000,
    chunk_overlap: int = 400,
) -> List[Document]:
    """
    Convenience wrapper that returns only text chunks (tabular pages are
    silently discarded). Use during the transition period before SQL extraction
    is wired in.
    """
    chunks, _ = split_documents(documents, chunk_size, chunk_overlap)
    return chunks


if __name__ == "__main__":
    sample_doc = [
        Document(
            page_content="The Andhra Pradesh Budget for 2026-27 prioritizes agricultural growth, capital expenditure, and social welfare.",
            metadata={"page_number": 1, "title": "Budget Speech", "is_tabular": False}
        )
    ]
    chunks, tabular = split_documents(sample_doc, chunk_size=50, chunk_overlap=10)
    for c in chunks:
        print("Chunk:", c.page_content, "| Meta:", c.metadata)
