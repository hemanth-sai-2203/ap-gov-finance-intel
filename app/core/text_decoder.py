"""
Text Decoder and Unscrambler for AP Government Finance Platform.

Fixes font-encoding and character-code shift artifacts in PDFs where fonts were embedded
with a custom subset or missing ToUnicode CMap table (e.g. +1 character code shift
where 'HEALTH' became 'IFBMUI', 'RECORDS' became 'SFDPSET', 'URBANIZATION' became '6SCBOJ[BUJPO').
"""
import re
import logging

logger = logging.getLogger(__name__)

# Common +1 shift patterns:
# 'IBT CFFO' -> 'HAS BEEN'
# 'SFDPSET'  -> 'RECORDS'
# '6SCBO'    -> 'URBAN'
# 'FTUBCMJTIFE' -> 'ESTABLISHED'
# 'BOE'      -> 'AND'
# 'GPS'      -> 'FOR'
# 'UP'       -> 'TO'
# 'JO'       -> 'IN'

SHIFT_DETECT_PATTERN = re.compile(
    r'\b(IBT\s+CFFO|SFDPSET|6SCBO|FTUBCMJTIFE|BOE|GPS|HSPXUI|JNQPSUBOU|DPNQPOFOU|\*IFBMUI)\b',
    re.IGNORECASE
)

# Custom uppercase/symbol mapping found in AP government PDF subset fonts:
CUSTOM_CHAR_MAP = {
    '*': '* ',   # Often a bullet point in AP reports
    '#': 'B',
    '$': 'C',
    '%': 'D',
    '&': 'E',
    '\'': 'F',
    '(': 'G',
    ')': 'H',
    '+': 'I',
    ',': 'J',
    '-': 'L',
    '.': 'M',
    '/': 'N',
    '0': 'O',
    '1': 'P',
    '2': 'Q',
    '3': 'R',
    '4': 'S',
    '5': 'T',
    '6': 'U',
    '7': 'V',
    '8': 'W',
    '9': 'X',
    ':': 'Y',
    ';': 'Z',
    '[': 'Z'
}


def is_shifted_text(text: str) -> bool:
    """Detects if text contains +1 font-shifted words."""
    if not text:
        return False
    if "IBT CFFO" in text or "SFDPSET" in text or "6SCBO" in text or "FTUBCMJTIFE" in text:
        return True
    # Count occurrences of shifted markers
    matches = len(SHIFT_DETECT_PATTERN.findall(text))
    return matches >= 2


def unscramble_char(c: str) -> str:
    """Reverses the +1 shift for a single character."""
    # Custom uppercase / punctuation substitution
    if c in CUSTOM_CHAR_MAP:
        return CUSTOM_CHAR_MAP[c]
    
    code = ord(c)
    # Uppercase A-Z shifted by 1: B-Z -> A-Y, '[' -> Z
    if 66 <= code <= 90:  # 'B' to 'Z'
        return chr(code - 1)
    elif code == 65:      # 'A' wraps or stays
        return 'Z'
    # Lowercase a-z shifted by 1: b-z -> a-y, '{' -> z
    elif 98 <= code <= 122: # 'b' to 'z'
        return chr(code - 1)
    elif code == 97:       # 'a' wraps
        return 'z'
    elif code == 123:      # '{' -> 'z'
        return 'z'
    elif code == 91:       # '[' -> 'Z'
        return 'Z'
    
    return c


def decode_shifted_pdf_text(text: str) -> str:
    """
    Decodes +1 character shifted PDF text into clean English.
    If the text is already normal English, returns it cleaned without changes.
    """
    if not text:
        return ""
    
    # Clean non-printable control characters first (e.g. \x12, \x01, \x15)
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    cleaned = cleaned.replace('|', ' ')
    
    # Check if text is shifted
    if not is_shifted_text(cleaned):
        # Normalize whitespace and return
        return re.sub(r'[ \t]+', ' ', cleaned).strip()
    
    # Decode character by character
    decoded_chars = []
    for ch in cleaned:
        decoded_chars.append(unscramble_char(ch))
    
    result = "".join(decoded_chars)
    
    # Normalize whitespace
    result = re.sub(r'[ \t]+', ' ', result)
    result = re.sub(r'\n\s*\n+', '\n\n', result)
    return result.strip()


def sanitize_display_title(raw_title: str, category: str = "", financial_year: str = "") -> str:
    """
    Replaces generic or button link titles like 'Click Here to Download' with
    official, professional publication names.
    """
    if not raw_title:
        raw_title = ""
    
    title_lower = raw_title.lower().strip()
    if not title_lower or "click here" in title_lower or "download" == title_lower:
        cat_labels = {
            "socio_economic_survey": "Andhra Pradesh Socio-Economic Survey",
            "budget_speech": "Andhra Pradesh Budget Speech",
            "budget_volumes": "Andhra Pradesh Budget Estimates (Volume)",
            "frbm_reports": "Fiscal Responsibility & Budget Management (FRBM) Report",
            "finance_gos": "Finance Department Government Order (G.O.)",
            "prc_reports": "Pay Revision Commission (PRC) Report",
            "finance_manual": "Andhra Pradesh Financial Code & Budget Manual",
            "guidelines_circulars": "Budget Guidelines & Comprehensive Release Orders"
        }
        base = cat_labels.get(category, "AP Official State Finance Publication")
        if financial_year and financial_year != "N/A" and financial_year != "General":
            return f"{base} ({financial_year})"
        return base
    
    # Clean whitespace
    return " ".join(raw_title.split())
