import fitz  # PyMuPDF
import pdfplumber
import logging
import re
from typing import List, Dict, Any, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_pages_and_text(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text and page numbers from PDF using PyMuPDF.
    Returns list of dicts: [{"page_number": int, "text": str}]
    """
    doc = fitz.open(pdf_path)
    pages_data = []
    
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        text = page.get_text("text")
        pages_data.append({
            "page_number": page_idx + 1,
            "text": text
        })
        
    doc.close()
    return pages_data

def extract_tables_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts structured tables from budget PDF pages using pdfplumber.
    Preserves table structure, headers, and cell values.
    """
    extracted_tables = []
    
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx, page in enumerate(pdf.pages):
            page_num = page_idx + 1
            tables = page.extract_tables()
            
            for table_idx, table in enumerate(tables):
                if not table or len(table) < 2:
                    continue
                
                # Clean rows
                cleaned_rows = []
                for row in table:
                    cleaned_row = [str(cell).strip() if cell is not None else "" for cell in row]
                    if any(cleaned_row):
                        cleaned_rows.append(cleaned_row)
                
                if cleaned_rows:
                    extracted_tables.append({
                        "page_number": page_num,
                        "table_index": table_idx + 1,
                        "rows": cleaned_rows
                    })
                    
    return extracted_tables

def parse_budget_allocation_rows(table_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parses structured budget allocations from extracted table rows.
    Looks for numerical budget fields: Major Head, Demand, BE, RE, Actuals.
    """
    parsed_allocations = []
    
    for table_info in table_data:
        page_num = table_info["page_number"]
        rows = table_info["rows"]
        
        # Simple heuristic to identify header vs data rows
        for row in rows:
            # Join row text to check patterns
            row_str = " ".join(row)
            
            # Match 4-digit major head (e.g. 2202 for General Education, 2401 for Crop Husbandry)
            major_head_match = re.search(r'\b(\d{4})\b', row_str)
            major_head = major_head_match.group(1) if major_head_match else None
            
            # Extract numbers from row
            numbers = []
            for cell in row:
                # Remove commas and currency symbols
                clean_num_str = re.sub(r'[^\d.]', '', cell)
                if clean_num_str and clean_num_str.count('.') <= 1:
                    try:
                        val = float(clean_num_str)
                        numbers.append(val)
                    except ValueError:
                        pass
            
            if len(numbers) >= 1:
                # Store candidate allocation row
                parsed_allocations.append({
                    "page_number": page_num,
                    "raw_row": row,
                    "major_head": major_head,
                    "numbers_found": numbers
                })
                
    return parsed_allocations
