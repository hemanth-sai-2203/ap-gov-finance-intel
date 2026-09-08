import os
import re
import logging
from typing import List, Tuple
from langchain_core.documents import Document
from langchain_community.document_loaders import PyMuPDFLoader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Telugu filter ────────────────────────────────────────────────────────────

TELUGU_RANGE_REGEX = re.compile(r'[\u0C00-\u0C7F]+')


def clean_and_filter_telugu_text(text: str) -> str:
    """
    Cleans mixed Telugu/English document text:
    1. Discards pages that are predominantly (>70%) Telugu.
    2. Strips Telugu Unicode characters from bilingual pages.
    3. Normalises whitespace.
    """
    if not text:
        return ""
    total_chars = len(text.strip())
    if total_chars == 0:
        return ""
    telugu_char_count = sum(len(m.group(0)) for m in TELUGU_RANGE_REGEX.finditer(text))
    if (telugu_char_count / total_chars) > 0.70:
        return ""
    cleaned = TELUGU_RANGE_REGEX.sub(' ', text)
    cleaned = re.sub(r'[ \t]+', ' ', cleaned)
    cleaned = re.sub(r'\n\s*\n+', '\n\n', cleaned)
    return cleaned.strip()


# ─── AP Finance boilerplate patterns ──────────────────────────────────────────
#
# These patterns match zero-semantic-signal header/footer text that appears
# on almost every page of AP Finance GOs, budget books and PRC volumes.
# Stripping them BEFORE chunking means:
#   (a) chunks are shorter → more meaningful per slot
#   (b) similarity search stops pulling pure-header chunks as results
#   (c) reference citation lists are captured as metadata, not as chunks

# Typical page header of a GO:
#   "GOVERNMENT OF ANDHRA PRADESH ABSTRACT"
#   "Finance (Pay Cell) Department – G.O.Ms.No.42  Dated: 30-04-2015."
_GO_ABSTRACT_HEADER = re.compile(
    r'GOVERNMENT\s+OF\s+ANDHRA\s+PRADESH\s+ABSTRACT[\s\S]{0,300}?(?=\n\n|ORDER|ORDERS|Whereas|1\.)',
    re.IGNORECASE
)

# "The following order is issued:" / "ORDER:" / "ORDERS:" separators
_ORDER_SEPARATOR = re.compile(
    r'^\s*(The\s+following\s+(order|orders)\s+(is|are)\s+issued\s*:?|ORDER\s*:|ORDERS\s*:)\s*$',
    re.IGNORECASE | re.MULTILINE
)

# "Read the following:" preamble + numbered citation list
#   Captured into metadata as referenced_gos, then stripped from page text.
_READ_THE_FOLLOWING_BLOCK = re.compile(
    r'Read\s+the\s+following\s*:\s*\n((?:\s*\d+[\.\)]\s+G\.?O\.?.*?\n)+)',
    re.IGNORECASE
)

# Individual GO citation line used to extract cross-references
_GO_CITATION = re.compile(
    r'G\.?O\.?\s*(?:Ms\.?|Rt\.?|P\.?)?\s*No\.?\s*\d+[\s\S]{0,120}?(?:Dated|dt\.?)\s*[\d\-/]+',
    re.IGNORECASE
)

# Closing boilerplate (bottom of every GO)
_GO_FOOTER = re.compile(
    r'(Yours\s+faithfully|To\s+The\s+Pay\s+and\s+Accounts|Copy\s+to\s*:?|By\s+order\s+and\s+in\s+the\s+name)[\s\S]*$',
    re.IGNORECASE
)

# Repeated page stamp lines:
#   "3" or "Page 3 of 47" or "- 3 -"
_PAGE_NUMBER_LINE = re.compile(
    r'^\s*[-–—]?\s*\d{1,4}\s*[-–—]?\s*$',
    re.MULTILINE
)

# "Contd..." or "...continued on next page"
_CONTD = re.compile(
    r'^\s*[Cc]ontd?\.?\s*$',
    re.MULTILINE
)

# Budget estimate page headers: repeated title like "BUDGET ESTIMATES 2024-25"
# and column headers like "Head of Account | Budget | Revised | Actuals"
_BUDGET_PAGE_HEADER = re.compile(
    r'^(BUDGET\s+ESTIMATES|REVISED\s+ESTIMATES|ACTUAL\s+RECEIPTS|STATEMENT\s+NO\.)[\s\S]{0,200}?(?=\n\d|\nTotal|\nGrand)',
    re.IGNORECASE | re.MULTILINE
)

# Column-only rows from tables that got extracted as plain text with no context
# e.g.  "  2202-01-101  500.00  520.00  480.00"
# These are useless without the surrounding header — they go to SQL, not chunks.
_PURE_NUMBER_ROW = re.compile(
    r'^\s*[\d\-]{4,20}\s+[\d,\.]+\s+[\d,\.]+\s*$',
    re.MULTILINE
)


def strip_go_boilerplate(text: str) -> Tuple[str, List[str]]:
    """
    Removes known zero-signal boilerplate from an AP Finance document page and
    extracts GO cross-references as a structured list.

    Returns:
        (cleaned_text, referenced_gos)
        - cleaned_text:    page text with headers/footers/reference-blocks removed
        - referenced_gos:  list of GO citation strings found in the "Read the following" block
    """
    referenced_gos: List[str] = []

    # 1. Extract GO cross-reference citations before stripping
    for m in _READ_THE_FOLLOWING_BLOCK.finditer(text):
        block = m.group(1)
        for citation in _GO_CITATION.findall(block):
            referenced_gos.append(citation.strip())
        text = text[:m.start()] + text[m.end():]

    # 2. Strip abstract/header block
    text = _GO_ABSTRACT_HEADER.sub('', text)

    # 3. Strip "ORDER:" / "The following order is issued:" separator lines
    text = _ORDER_SEPARATOR.sub('', text)

    # 4. Strip closing footer (everything from "Yours faithfully" onward)
    text = _GO_FOOTER.sub('', text)

    # 5. Strip lone page-number lines and "Contd..." lines
    text = _PAGE_NUMBER_LINE.sub('', text)
    text = _CONTD.sub('', text)

    # 6. Strip budget estimate repeated column-header blocks
    text = _BUDGET_PAGE_HEADER.sub('', text)

    # 7. Normalise whitespace left behind after removals
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip(), referenced_gos


# ─── Table density detector ────────────────────────────────────────────────────

def estimate_table_density(text: str) -> float:
    """
    Returns a rough 0–1 score estimating what fraction of the page is tabular.
    A page with score > 0.55 is considered 'predominantly tabular'.

    Heuristic: count lines that look like data rows (contain multiple
    whitespace-separated numbers or head-of-account codes).
    """
    lines = text.splitlines()
    if not lines:
        return 0.0
    # A "table line" has ≥2 numeric tokens (integers or decimals)
    num_token = re.compile(r'\b\d[\d,\.]{1,14}\b')
    table_line_count = sum(1 for l in lines if len(num_token.findall(l)) >= 2)
    return table_line_count / max(len(lines), 1)


# ─── Main loader ──────────────────────────────────────────────────────────────

def load_pdf_document(
    file_path: str,
    doc_metadata: dict = None
) -> List[Document]:
    """
    Loads a local PDF file into LangChain Document objects using PyMuPDFLoader.

    Pipeline per page:
      1. Telugu filter   — drop or strip Telugu script
      2. Boilerplate strip — remove GO headers, footers, reference blocks
      3. Table-density check — tag pages that are mostly tabular
         (these pages will be skipped by the chunker and routed to SQL extraction)

    Each Document carries enriched metadata including:
      - referenced_gos: list of GO numbers cited on this page (from "Read the following" block)
      - is_tabular:     True if page is predominantly a data table
      - table_density:  0–1 score
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"PDF file not found at: {file_path}")

    logger.info(f"Loading PDF with PyMuPDFLoader: {file_path}")
    loader = PyMuPDFLoader(file_path)
    raw_docs = loader.load()

    doc_metadata = doc_metadata or {}
    enriched_docs = []
    skipped_telugu = 0
    skipped_short = 0
    tabular_pages = 0

    for i, doc in enumerate(raw_docs):
        # Step 1: Telugu filter
        page_text = clean_and_filter_telugu_text(doc.page_content)
        if not page_text or len(page_text) < 20:
            skipped_telugu += 1
            continue

        # Step 2: Boilerplate strip
        page_text, referenced_gos = strip_go_boilerplate(page_text)
        if not page_text or len(page_text) < 20:
            skipped_short += 1
            continue

        # Step 3: Table density
        density = estimate_table_density(page_text)
        is_tabular = density > 0.55

        if is_tabular:
            tabular_pages += 1

        page_num = doc.metadata.get("page", i) + 1
        meta = {
            **doc.metadata,
            **doc_metadata,
            "page_number":    page_num,
            "source_file":    os.path.basename(file_path),
            "referenced_gos": referenced_gos,
            "is_tabular":     is_tabular,
            "table_density":  round(density, 3),
        }
        enriched_docs.append(Document(page_content=page_text, metadata=meta))

    logger.info(
        f"Loaded {len(enriched_docs)} valid English pages from {os.path.basename(file_path)} "
        f"(skipped: {skipped_telugu} Telugu, {skipped_short} short-after-strip; "
        f"{tabular_pages} tabular pages tagged)"
    )
    return enriched_docs


if __name__ == "__main__":
    print("PyMuPDFLoader module ready.")
