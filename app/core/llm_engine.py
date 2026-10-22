"""
Grounded Answer Synthesis Engine for AP Government Finance Intelligence.

Phase 3: Generation Pipeline
1. Takes structured EvidenceBundle from Phase 2 (Unified Retrieval Engine).
2. Builds an anti-hallucination, citation-enforcing system prompt.
3. Calls Google Gemini 2.5 Flash (or pluggable local SLM).
4. Generates precise natural language answers with exact clickable source provenance:
   `[Source: <Title>, <Financial Year>, Page <Page Number>]`
"""
import os
import logging
from typing import Dict, Any, Optional, List
import httpx
from app.core.config import settings
from app.search.engine import EvidenceBundle, retrieve_evidence
from app.core.text_decoder import decode_shifted_pdf_text, sanitize_display_title

logger = logging.getLogger(__name__)

GEMINI_API_KEY = settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY
DEFAULT_MODEL = settings.GEMINI_MODEL or "gemini-3.6-flash"
LLM_PROVIDER = settings.LLM_PROVIDER or "gemini"

# Anti-Hallucination Government Analyst System Prompt
SYSTEM_PROMPT = """You are the official Chief Analyst for Andhra Pradesh Government Finance and Budget Intelligence.

Your answers MUST adhere to these STRICT rules:
1. GROUNDED IN EVIDENCE ONLY: Base your answer EXCLUSIVELY on the provided Official Context (SQL data, Document Passages, or Document Catalog). If the user query is concise or vague, interpret it within the AP State Finance domain. If the provided evidence only partially covers the question (e.g. contains account head classifications but not full procedural rules), clearly state what is verified in the provided records and cite the relevant statutory manual (e.g. AP Financial Code / AP Budget Manual) without fabricating unverified provisions.
2. PRECISE CITATIONS: Every factual claim, allocation figure, or catalog entry MUST include an exact inline citation:
   [Source: <Document Title>, <Financial Year>, Page <Page Number>]
3. EXACT NUMERICAL ACCURACY: Quote exact rupee/crore figures as provided in the evidence. Never fabricate numbers or calculate estimated projections.
4. SCOPE INTEGRITY (NO ENTITY CONFLATION):
   - NEVER attribute a "State Total" budget figure or a whole department's total allocation to an individual scheme (e.g. Amma Vodi, Rythu Bharosa, Cheyutha).
   - If the user asks for a specific scheme allocation and the evidence contains department-wide or state-wide totals but no scheme-specific row, explicitly clarify that the provided figures are for the parent department or state overall, and cite scheme allocations only from verified text passages (such as Budget Speeches or Demands for Grants).
5. STRUCTURED EXECUTIVE BRIEFING FORMAT: Always format every response using this clean, structured layout:

### 📋 Executive Summary
A clear, direct 1–2 sentence answer highlighting the primary takeaway, allocation, or catalog summary.

### 🔍 Key Findings & Policy Provisions
* **Core Detail / Provision:** Exact numerical figure, document title, or statutory rule [Source: Document, FY, Page X].
* **Scope & Applicability:** Relevant department, Demand number, classification, or timeframe.
* **Conditions / Procedures:** Specific administrative requirements or operational guidelines (if present in evidence).

### 📑 Document Context & Observations
Concise paragraph noting background context from the official publication, boundaries of the provided data, or relevant reference manuals.

6. CLEAN READABILITY: Never output dense walls of text. Use bullet points with bold keywords (`* **Keyword:** ...`) and proper paragraph breaks.
"""


def call_gemini_api(prompt: str, model_name: str = "gemini-3-flash-preview") -> str:
    """Calls Gemini REST API via httpx with low temperature and anti-hallucination prompt."""
    api_key = (settings.GEMINI_API_KEY or settings.GOOGLE_API_KEY or "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY must be set in .env")

    # Order models by live verified responsiveness & speed
    candidate_models = [
        model_name,
        "gemini-2.5-flash",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
        "gemini-flash-latest",
        "gemini-1.5-pro",
        "gemini-3.6-flash"
    ]
    seen = set()
    models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key
    }

    last_error = None
    for m in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"

        payload = {
            "system_instruction": {
                "parts": [{"text": SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096
            }
        }

        try:
            # 12s timeout per candidate to fail over quickly if Google hangs or rate-limits
            response = httpx.post(url, headers=headers, json=payload, timeout=12.0)
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates and "content" in candidates[0]:
                    parts = candidates[0]["content"].get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
                return "No response generated by model."
            else:
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
                logger.warning(f"Model '{m}' returned status {response.status_code}, trying next model...")
        except Exception as e:
            last_error = str(e)
            logger.warning(f"Model '{m}' call failed ({e}), trying next model...")

    raise RuntimeError(f"All Gemini API model attempts failed. Last error: {last_error}.")


def build_deterministic_briefing(query: str, evidence: EvidenceBundle) -> str:
    """
    Constructs a high-precision, executive briefing directly from retrieved evidence
    if LLM API calls time out or fail. Ensures zero broken user experience.
    """
    lines = [
        "### 📋 Executive Summary",
        f"Official verified data from the Andhra Pradesh State Finance and Budget Intelligence platform for query: *\"{query}\"*.",
        "",
        "### 🔍 Key Findings & Policy Provisions"
    ]
    findings_added = False

    # 1. State-level Budget Aggregations (Deterministic SQL)
    if evidence.sql_aggregations:
        agg = evidence.sql_aggregations
        yr = agg.get("financial_year", "State Financial Year")
        be = agg.get("total_budget_estimate_cr", 0.0)
        re = agg.get("total_revised_estimate_cr", 0.0)
        act = agg.get("total_actual_expenditure_cr", 0.0)
        lines.append(f"* **Total State Budget Estimate ({yr}):** ₹{be:,.2f} Crore [Source: AP State Budget Estimates, {yr}]")
        if re:
            lines.append(f"* **Revised Estimate ({yr}):** ₹{re:,.2f} Crore [Source: AP State Budget Estimates, {yr}]")
        if act:
            lines.append(f"* **Actual Expenditure ({yr}):** ₹{act:,.2f} Crore [Source: AP State Accounts, {yr}]")
        findings_added = True

    # 2. Structured Tabular Financial Records (Department & Scheme Outlays)
    if evidence.sql_records:
        lines.append("\n* **Official Financial Records (SQL):**" if findings_added else "* **Official Financial Records (SQL):**")
        for r in evidence.sql_records[:8]:
            yr = r.get("financial_year", "N/A")
            dept = r.get("department")
            scheme_item = r.get("scheme_name")
            be = r.get("budget_estimate_cr")
            re = r.get("revised_estimate_cr")
            be_str = f"₹{be:,.2f} Cr" if be is not None else "N/A"
            re_str = f" | Revised: ₹{re:,.2f} Cr" if re is not None else ""
            if scheme_item and scheme_item != "General Departmental Allocation":
                lines.append(f"  * **{scheme_item} ({yr}):** Allocation: {be_str}{re_str} [Source: {dept or 'State'} Budget Record, {yr}]")
            elif dept:
                lines.append(f"  * **{dept} ({yr}):** Department Budget Estimate: {be_str}{re_str} [Source: {dept} Financial Record, {yr}]")
            else:
                lines.append(f"  * **Financial Year {yr}:** Total Allocation: {be_str} [Source: Annual Financial Statement, {yr}]")
        findings_added = True

    # 3. Verified Document Passages (Demands for Grants, Speeches, Manuals, Policies)
    if evidence.passages:
        lines.append("\n* **Verified Document Records & Policy Provisions:**" if findings_added else "* **Verified Document Records & Policy Provisions:**")
        for idx, p in enumerate(evidence.passages[:4], 1):
            clean_title = sanitize_display_title(p.title or "Official Publication", category=p.category, financial_year=p.financial_year)
            decoded = decode_shifted_pdf_text(p.content or "")
            clean_content = " ".join(decoded.split())[:280]
            lines.append(f"  * **Official Record #{idx} ({clean_title}):** \"{clean_content}...\" [Source: {clean_title}, {p.financial_year}, Page {p.page_number}]")
        findings_added = True

    if not findings_added:
        lines.append("* No verified figures or policy provisions could be matched in the current database for this query.")

    lines.extend([
        "",
        "### 📑 Document Context & Observations",
        "The figures above are extracted deterministically from verified Andhra Pradesh Government gazettes, Annual Financial Statements, and Demands for Grants."
    ])

    return "\n".join(lines)





def generate_answer(
    query: str,
    evidence: EvidenceBundle,
    model_name: str = DEFAULT_MODEL
) -> Dict[str, Any]:
    """
    Synthesizes a fully grounded response using Gemini API.

    Args:
        query: User natural language question
        evidence: EvidenceBundle produced by Phase 2 retrieve_evidence()
        model_name: Gemini model name (default: gemini-2.5-flash)

    Returns:
        Dict with:
          - 'answer': Generated answer with inline citations
          - 'citations': List of distinct structured citations
          - 'evidence_bundle': The underlying EvidenceBundle
          - 'model_used': Model identifier
    """
    # Fast-path for greetings: Return polite, helpful welcome with zero bogus citations
    if getattr(evidence, "query_type", "").lower() == "greeting":
        return {
            "query": query,
            "answer": (
                "### 🏛️ Andhra Pradesh State Finance Intelligence Assistant\n\n"
                "Welcome to the Andhra Pradesh State Finance and Budget Intelligence platform. I am connected to verified official publications, annual budget estimates, FRBM compliance reports, and the AP Financial Code.\n\n"
                "**Here are a few questions you can ask me:**\n"
                "* *\"What are the key priorities in the 2024-25 Budget Speech?\"*\n"
                "* *\"What is the total budget allocation for the School Education Department in 2026-27?\"*\n"
                "* *\"Compare agriculture department allocations between 2023-24 and 2024-25.\"*\n"
                "* *\"Explain the guidelines and procedure for Comprehensive Budget Release Orders (CBRO).\"*\n"
                "* *\"What are the rules regarding re-appropriation of budget funds in the AP Financial Code?\"*"
            ),
            "citations": [],
            "evidence_bundle": evidence.to_dict(),
            "model_used": "greeting_handler"
        }

    if not evidence.passages and not evidence.sql_records and not evidence.sql_aggregations:
        return {
            "query": query,
            "answer": "No relevant records or policy documents were found in the Andhra Pradesh Finance Intelligence database for your query. Please verify if the relevant financial year or document has been ingested.",
            "citations": [],
            "evidence_bundle": evidence.to_dict(),
            "model_used": "none"
        }

    # Format the evidence context block
    context_text = evidence.get_context_text(max_passages=6)

    prompt = f"""USER QUESTION:
{query}

============================================================
OFFICIAL AP GOVERNMENT EVIDENCE CONTEXT:
============================================================
{context_text}
============================================================

Please synthesize a comprehensive, highly accurate response strictly grounded in the evidence above. Include inline citations `[Source: Title, Year, Page X]` for each statement.
"""

    # Extract structured citations list for UI display upfront
    citations = []
    seen = set()

    for p in evidence.passages:
        raw_title = p.title or "Official AP Government Document"
        clean_title = sanitize_display_title(raw_title, category=p.category, financial_year=p.financial_year)
        cite_key = (clean_title, p.financial_year, p.page_number)
        if cite_key not in seen:
            seen.add(cite_key)
            decoded_content = decode_shifted_pdf_text(p.content or "")
            excerpt = " ".join(decoded_content.split())[:280] if decoded_content else ""
            citations.append({
                "title": clean_title,
                "document": clean_title,
                "category": p.category,
                "financial_year": p.financial_year,
                "page_number": p.page_number,
                "page": p.page_number,
                "excerpt": excerpt,
                "content": decoded_content,
                "relevance_score": round(float(p.rerank_score), 4),
                "source_url": p.source_url,
                "citation_label": f"[Source: {clean_title}, {p.financial_year}, Page {p.page_number}]"
            })

    for r in evidence.sql_records:
        raw_title = r.get("source_document_title") or r.get("title") or f"{r.get('department', 'State')} Budget Record"
        clean_title = " ".join(raw_title.split())
        cite_key = (clean_title, r.get("financial_year"), "SQL")
        if cite_key not in seen:
            seen.add(cite_key)
            dept = r.get("department")
            if dept:
                be = r.get("budget_estimate_cr")
                re = r.get("revised_estimate_cr")
                excerpt = f"Department: {dept} | Budget Estimate: ₹{be} Cr" + (f" | Revised Estimate: ₹{re} Cr" if re else "")
                cite_label = f"[Source: {dept} Financial Record, {r.get('financial_year')}]"
            else:
                be = r.get("budget_estimate_cr")
                be_txt = f"₹{be:,.2f} Cr" if be is not None else "N/A"
                excerpt = f"Financial Year: {r.get('financial_year')} | Total Budget: {be_txt}"
                cite_label = f"[Source: {clean_title}, {r.get('financial_year')}]"

            citations.append({
                "title": clean_title,
                "document": clean_title,
                "category": r.get("category", "financial_records"),
                "financial_year": r.get("financial_year"),
                "page_number": "SQL Data",
                "page": "SQL",
                "excerpt": excerpt,
                "content": excerpt,
                "relevance_score": 1.0,
                "source_url": r.get("source_url"),
                "citation_label": cite_label
            })

    try:
        logger.info(f"Generating answer with {model_name} for query: '{query[:60]}...'")
        answer_text = call_gemini_api(prompt, model_name=model_name)
        model_used = model_name
    except Exception as e:
        logger.warning(f"LLM API synthesis unavailable or timed out ({e}). Engaging deterministic analyst briefing...")
        answer_text = build_deterministic_briefing(query, evidence)
        model_used = "deterministic_analyst_briefing"

    return {
        "query": query,
        "answer": answer_text,
        "citations": citations,
        "evidence_bundle": evidence.to_dict(),
        "model_used": model_used
    }


def ask_gov_intel(query: str, top_k: int = 5) -> Dict[str, Any]:
    """
    Full End-to-End Entry Point (Phase 2 Retrieval -> Phase 3 Generation).

    Usage:
        result = ask_gov_intel("What are the rules for re-appropriation of budget funds?")
        print(result["answer"])
    """
    evidence = retrieve_evidence(query=query, top_k=top_k)
    return generate_answer(query=query, evidence=evidence)


if __name__ == "__main__":
    test_queries = [
        "What are the rules for re-appropriation of budget funds in Andhra Pradesh?",
        "What is the procedure for Comprehensive Budget Release Order CBRO in 2026-27?",
        "What was the farmer welfare input subsidy support in the 2021 budget?"
    ]

    for q in test_queries:
        print("\n" + "=" * 80)
        print(f"USER QUERY: \"{q}\"")
        print("=" * 80)
        res = ask_gov_intel(q, top_k=3)
        print("\n--- SYNTHESIZED ANSWER ---")
        print(res["answer"])
        print("\n--- CITATIONS (PROVENANCE) ---")
        for c in res["citations"]:
            print(f"  • {c['citation_label']} (Relevance: {c['relevance_score']:.3f})")
        print()
