# 🏛️ Andhra Pradesh Government Finance Intelligence Platform

> **An AI-powered, evidence-grounded research assistant** for the complete corpus of Andhra Pradesh Government Finance publications — Budget Speeches, Departmental Budget Estimates, FRBM Compliance Reports, Pay Revision Commission Volumes, Socio-Economic Surveys, and more.

---

## What Is This Project?

The **AP Government Finance Intelligence Platform** is a production-grade AI system that enables anyone — a researcher, journalist, policy analyst, or government official — to ask natural language questions about Andhra Pradesh's public finances and receive **precise, fully cited, evidence-grounded answers** drawn directly from official government publications.

**Instead of manually searching through thousands of PDF pages, you simply ask:**

- *"What was the total budget allocation for Water Resources Department in 2024-25?"*
- *"How has education expenditure changed from 2015-16 to 2026-27?"*
- *"What are the FRBM compliance commitments for fiscal deficit in 2025-26?"*
- *"Summarize the key policy announcements in the 2026-27 Budget Speech."*

The system retrieves the most relevant official passages, verifies them against structured financial tables, and synthesizes a grounded answer with exact citations — **document title, financial year, and page number**.

---

## Problem Being Solved

The Andhra Pradesh Finance Department publishes **hundreds of official documents** across its portal (`apfinance.gov.in`) — budget volumes, departmental estimates, outcome reports, PRC orders, FRBM statements, and more. These are:

- **Scattered across 15+ web pages and S3 buckets** with no unified search
- **Available only as raw PDFs** — no text extraction or semantic indexing
- **Spanning 14+ financial years** (2011-12 to 2026-27)
- **Mixed with Telugu-script pages** that must be filtered
- **Contains both policy narratives** (requiring semantic AI understanding) **and precise budget numbers** (requiring exact SQL lookups)

No existing tool enables a user to search across all of this simultaneously with evidence-grounded AI answers.

---

## How It Works — System Architecture

```
        USER QUESTION (Natural Language)
                    |
            INTENT ROUTER
   (Classifies: SQL / RAG / Hybrid / Comparison)
          /                         \
  SQL ENGINE                 HYBRID SEARCH ENGINE
  (Supabase PG)              (Weaviate Cloud)
  - Budget totals            - Dense Vector Search (768-dim bge-base)
  - Dept figures             - Sparse BM25 Search
  - Year-on-year             
          \                         /
           CROSS-ENCODER RERANKER
           (ms-marco-MiniLM-L-6-v2)
           Re-scores and ranks all passages
                    |
           GEMINI 2.5 FLASH (LLM)
           Anti-hallucination system prompt
           Grounded answer + inline citations
                    |
           RESPONSE TO USER
           Answer + Citations + SQL Tables
```

---

## Data Corpus — What Has Been Ingested

### Total Scope

| Metric | Value |
|---|---|
| Total Official Government Publications | 590 |
| Financial Years Covered | 2011-12 to 2026-27 (15 years) |
| Vector Embeddings (Weaviate Cloud) | ~48,000+ chunks |
| Relational Metadata Records (Supabase SQL) | ~48,000+ rows |
| Embedding Dimensions | 768-dim (BAAI/bge-base-en-v1.5) |

### Document Categories

| Category | Documents | Description |
|---|---|---|
| Budget Speeches | 16 | Annual Finance Minister budget address (2011-2027) |
| Departmental Budget Volumes (I-VIII) | 367 | Detailed estimates for all 17 government departments |
| Finance Publications and Manuals | 83 | Treasury Code, Budget Manual, policy guidelines |
| FRBM Compliance Reports | 48 | Fiscal Responsibility and Budget Management reviews |
| Pay Revision Commission (11th PRC) | 26 | Government employee pay scale revision orders and volumes |
| Supplementary Demands for Grants | 22 | Mid-year supplementary budget batches |
| Socio-Economic Surveys | 9 | AP economy-wide annual survey reports (2017-2025) |
| Circulars and Treasury Memos | 5 | Key financial governance circulars |

### What Each Document Type Contains

- **Budget Speeches**: Annual policy priorities, fiscal targets, flagship scheme announcements
- **Volume I (Annual Financial Statement)**: Consolidated revenue and capital budget, GSDP projections
- **Volume II (Revenue and Receipts)**: Tax and non-tax revenue details
- **Volume III (Departmental Estimates, 1-17)**: Head-of-account budget for all 17 departments
- **Volume IV (Public Accounts)**: Contingency fund, capital accounts
- **Volumes V-VIII**: Outcome Budget, Tribal Sub-Plan, SC Sub-Plan, Budget Annexures, Appendices A and B
- **FRBM Reports**: Fiscal deficit, revenue deficit, debt-to-GSDP ratios, quarterly performance
- **PRC Volumes**: Service-wise pay scales, allowances, HRA, DA, pension rules

---

## Technical Stack

### Backend / Core Engine

| Component | Technology |
|---|---|
| Web Framework | FastAPI (Python 3.11) |
| LLM for Generation | Google Gemini 2.5 Flash |
| Embedding Model | BAAI/bge-base-en-v1.5 (768-dim dense vectors, CPU inference) |
| Vector Database | Weaviate Cloud (GovIntelDocument collection) |
| Relational Database | Supabase PostgreSQL |
| ORM | SQLAlchemy |
| Reranker | cross-encoder/ms-marco-MiniLM-L-6-v2 |
| PDF Parsing | PyMuPDF (fitz) via LangChain PyMuPDFLoader |
| HTTP Client | httpx |

### Frontend / UI

| Component | Technology |
|---|---|
| Dashboard UI | Streamlit |
| Interactive Charts | Plotly Express |
| Data Tables | Pandas |

### Infrastructure

| Component | Technology |
|---|---|
| Cloud Vector Store | Weaviate Cloud (10 GB tier, grpc+http) |
| Cloud SQL | Supabase PostgreSQL (PgBouncer connection pooling) |
| PDF Storage | Local disk (data/raw_pdfs/category/) |
| API Containerization | Docker + Docker Compose |

---

## Search and Retrieval Architecture

### Phase 1: Intent Routing

Every user query is classified by a **Query Router** into one of four modes:

- **SQL** — Numeric/budget queries → Deterministic SQL (exact answers, zero hallucination risk)
- **RAG** — Policy/narrative questions → Hybrid semantic search + LLM synthesis
- **HYBRID** — Mixed numeric + narrative questions → Both SQL and RAG combined
- **COMPARISON** — Year-over-year or department-to-department comparisons

### Phase 2: Evidence Retrieval

**Hybrid Search (Weaviate Cloud)**
- **Dense Vector Search**: Query encoded with bge-base-en-v1.5, finds semantically similar passages
- **BM25 Sparse Search**: Keyword-level exact term matching (critical for GO numbers, department names, scheme codes)
- Both streams are merged and fed to the Cross-Encoder Reranker

**Deterministic SQL Engine (Supabase)**
- Extracts structured financial records from the `financial_records` table
- Supports: total budget by year, department allocations, top-K departments, year-over-year comparison
- Returns exact crore-level figures with zero fabrication risk

**Cross-Encoder Reranker**
- `ms-marco-MiniLM-L-6-v2` re-scores all candidate passages against the query
- Ensures the top-5 passages passed to Gemini are the most precisely relevant

### Phase 3: Grounded Answer Generation (Gemini 2.5 Flash)

- System prompt enforces strict anti-hallucination rules
- LLM reads only the retrieved passages — no parametric recall
- Outputs inline citations: [Source: Budget Speech 2026-27, Page 14]
- Cannot make claims not present in retrieved evidence

---

## Data Preprocessing Pipeline

### PDF Ingestion Rules (Applied to Every Document)

1. **Telugu Script Filter**: Any page where more than 60% of characters are in the Unicode Telugu range (U+0C00 to U+0C7F) is excluded
2. **Tabular Ledger Routing**: Pages with high numeric density are routed to the SQL `financial_records` table rather than vector chunks
3. **Boilerplate Stripping**: Repetitive headers, footers, page numbers, and GO abstract boilerplate are removed
4. **Chunk Configuration**: 2,000 characters with 400-character overlap (calibrated for bge-base-en-v1.5's 512-token limit)
5. **Idempotent Uploads**: Before inserting vectors for any document, existing stale vectors are deleted first — prevents bloat on re-runs

### Quality Metrics (Actual Pipeline Stats)

```
Avg Pages Per Document:       ~85 pages
Avg Chunks Generated Per Doc: ~95 chunks
Avg Chunk Size:               ~1,800 characters
Telugu Pages Filtered:        ~6% of all pages
Short/Noisy Fragments:        ~2% of chunks removed
```

---

## Project File Structure

```
Gov_intelligence_platform/
app/
    main.py                        # FastAPI REST API (7 endpoints)
    core/
        config.py                  # Environment configuration (.env)
        llm_engine.py              # Gemini 2.5 Flash generation engine
        query_pipeline.py          # End-to-end pipeline orchestrator
        weaviate_client.py         # Weaviate Cloud connection manager
    db/
        models.py                  # SQLAlchemy ORM models (3 tables)
        session.py                 # Supabase PostgreSQL session factory
        init_db.py                 # Database schema initializer
    ingestion/
        scraper.py                 # Web scraper for apfinance.gov.in
        downloader.py              # PDF downloader + DB registration
        loader.py                  # PyMuPDF page extractor + Telugu filter
        splitter.py                # Text chunker (2000 chars / 400 overlap)
        embedder.py                # BAAI/bge-base-en-v1.5 vectorizer
        store.py                   # Weaviate + Supabase upserter
        financial_extractor.py     # Tabular data to SQL financial_records
    search/
        engine.py                  # Unified retrieval entry-point
        query_router.py            # Intent classifier (SQL / RAG / Hybrid)
        hybrid_search.py           # Vector + BM25 search orchestrator
        vector_search.py           # Weaviate dense vector search
        bm25_search.py             # Weaviate BM25 keyword search
        reranker.py                # Cross-Encoder reranker (ms-marco)
        sql_engine.py              # Deterministic SQL query executors
    ui/
        streamlit_app.py           # Interactive Streamlit dashboard

run_ingestion.py                   # Main ingestion CLI runner
ingest_additional_finance_docs.py  # Secondary crawler for deep portal sections
audit_entire_portal.py             # Full portal PDF audit and gap detection
docker-compose.yml                 # Container orchestration
requirements.txt                   # Python dependencies
.env                               # API keys and DB connection strings
data/
    raw_pdfs/                      # Downloaded PDFs (organized by category)
        budget_speech/
        budget_volumes/
        frbm_report/
        prc_report/
        socio_economic_survey/
```

---

## API Endpoints

The FastAPI backend exposes 7 production-ready endpoints:

| Method | Endpoint | Description |
|---|---|---|
| GET | /health | System health check — Weaviate + Supabase connectivity |
| GET | /api/stats | Live stats: document count, vector chunks, categories |
| POST | /api/query | Main AI Query — Grounded RAG + SQL answer with citations |
| POST | /api/search | Raw hybrid search — returns ranked passages, no LLM |
| GET | /api/documents | List all ingested official government publications |
| GET | /api/budget/total | Deterministic SQL: total budget by year |
| GET | /api/budget/department | Deterministic SQL: department-level budget figures |
| GET | /api/budget/top-departments | Top-K departments by budget allocation |

### Example API Request

```json
POST /api/query
{
  "query": "What are the fiscal deficit targets under FRBM for 2026-27?",
  "financial_year": "2026-27",
  "top_k": 5
}
```

### Example API Response

```json
{
  "query": "What are the fiscal deficit targets under FRBM for 2026-27?",
  "answer": "According to the FRBM Review Report 2026-27, Andhra Pradesh has set a fiscal deficit target of 3.5% of GSDP...",
  "citations": [
    {
      "document": "FRBM_BE_2026-27_BookFinal",
      "financial_year": "2026-27",
      "page": 12,
      "excerpt": "The fiscal deficit for BE 2026-27 is projected at 45,820 crores..."
    }
  ],
  "query_type": "RAG",
  "retrieved_passages_count": 5,
  "engine": "Hybrid BM25 + 768-dim Vector + Cross-Encoder Reranker + Gemini 2.5 Flash"
}
```

---

## Database Schema

### Supabase PostgreSQL (Structured Metadata)

**`documents` table**

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment primary key |
| title | VARCHAR(500) | Full publication title |
| category | VARCHAR(100) | budget_volumes, frbm_report, etc. |
| financial_year | VARCHAR(20) | e.g. "2026-27", "2024-25" |
| language | VARCHAR(20) | Always "english" (Telugu filtered out) |
| source_url | VARCHAR(1000) | Original apfinance.gov.in URL |
| total_pages | INTEGER | Total pages in source PDF |
| total_chunks | INTEGER | Number of vector chunks created |
| status | VARCHAR(50) | pending / downloaded / processed / failed |

**`document_chunks` table**

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment primary key |
| document_id | INTEGER FK | Reference to documents.id |
| chunk_index | INTEGER | Chunk position within document |
| page_number | INTEGER | Source PDF page (1-indexed) |
| content | TEXT | Raw chunk text |
| weaviate_id | VARCHAR(100) | UUID of corresponding Weaviate vector |
| chunk_metadata | JSONB | category, year, title for fast filtering |

**`financial_records` table**

| Column | Type | Description |
|---|---|---|
| id | INTEGER PK | Auto-increment primary key |
| financial_year | VARCHAR(20) | e.g. "2026-27" |
| department | VARCHAR(255) | e.g. "Finance", "School Education" |
| scheme_name | VARCHAR(500) | e.g. "Direct Benefit Transfer" |
| budget_estimate_cr | FLOAT | Budget Estimate in Rs. Crores |
| revised_estimate_cr | FLOAT | Revised Estimate in Rs. Crores |
| actual_expenditure_cr | FLOAT | Actual Expenditure in Rs. Crores |

### Weaviate Cloud (Vector Index)

**GovIntelDocument collection**

| Property | Type | Description |
|---|---|---|
| chunk_text | TEXT | 2,000-character text chunk |
| title | TEXT | Document title |
| category | TEXT | Document category |
| financial_year | TEXT | e.g. "2026-27" |
| page_number | INTEGER | Source page number |
| document_id | INTEGER | FK back to Supabase documents.id |
| source_url | TEXT | Original government portal URL |
| vector | FLOAT[768] | BAAI/bge-base-en-v1.5 embedding |

*Indexed with: HNSW (dense vector) + BM25 (sparse keyword)*

---

## How to Run Locally

### Prerequisites

- Python 3.11+
- A Supabase project (free tier sufficient)
- A Weaviate Cloud cluster (free 14-day trial or sandbox)
- Google Gemini API key (from Google AI Studio — free tier available)

### Setup Steps

```bash
# 1. Clone the repository
git clone <repo-url>
cd Gov_intelligence_platform

# 2. Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate       # Windows
# source venv/bin/activate    # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
cp .env.example .env
# Fill in: SUPABASE_URL, SUPABASE_KEY, WEAVIATE_URL, WEAVIATE_API_KEY, GEMINI_API_KEY

# 5. Initialize database schema
python -m app.db.init_db

# 6. Run ingestion (downloads, chunks, embeds, indexes all 590 documents)
python run_ingestion.py --category all --chunk-size 2000 --chunk-overlap 400

# 7. Start the FastAPI backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 8. Start the Streamlit UI (in a separate terminal)
streamlit run app/ui/streamlit_app.py
```

### Using Docker Compose

```bash
docker-compose up --build
# API available at: http://localhost:8000
# Interactive API docs at: http://localhost:8000/docs
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| Weaviate Cloud for vectors (not pgvector) | Dedicated vector DB with native BM25 hybrid search, HNSW indexing, and metadata filtering. Far superior to pgvector for production hybrid search at scale |
| BAAI/bge-base-en-v1.5 (768-dim) | Best-in-class performance on legislative/government domain text; 512-token context window aligns with the 2,000-char chunk size |
| 2,000 chars / 400-char overlap chunks | Calibrated for bge-base-en-v1.5's 512-token limit: ~400 words = ~2,000 characters; 400-char overlap ensures cross-boundary context is never lost |
| Gemini 2.5 Flash for generation | 1M token context window, state-of-the-art factual grounding, sub-3s response latency |
| Cross-Encoder reranker after retrieval | Bi-encoder (vector) retrieval maximizes recall; Cross-Encoder reranking maximizes precision — two-stage pipeline is standard practice for production RAG |
| Deterministic SQL for numeric queries | Budget figures in Rs. crores must be exact — routing numeric queries to SQL eliminates the hallucination risk that comes from LLM estimation |
| Supabase for structured metadata | Full PostgreSQL compatibility, efficient JOINs, PgBouncer connection pooling for concurrent API load |

---

## Anti-Hallucination Safeguards

This platform is designed for **government policy research** where factual accuracy is non-negotiable. Multiple layers prevent fabricated information:

1. **Retrieval-First**: LLM only sees retrieved passages — never generates from parametric memory alone
2. **Strict System Prompt**: Gemini is explicitly instructed to refuse to answer if evidence is insufficient
3. **Citation Enforcement**: Every factual claim must link to a specific document, financial year, and page
4. **SQL for Numbers**: All budget figures come from deterministic SQL queries, not LLM estimation
5. **Source URLs**: Every retrieved passage links back to its original apfinance.gov.in PDF URL

---

## Future Roadmap (Phase 2 and Beyond)

| Phase | Feature |
|---|---|
| Phase 2 | Add Government Orders (GOs) and Act/Rule documents from Finance Dept archives |
| Phase 2 | Multi-lingual support: Telugu language queries mapped to English embeddings via cross-lingual model |
| Phase 2 | Audio query interface: speech-to-text to RAG to text-to-speech response |
| Phase 3 | Expand to other AP government departments (Revenue, Agriculture, Education portals) |
| Phase 3 | Real-time ingestion: auto-detect new publications via scheduled weekly crawler |
| Phase 4 | Multi-state expansion: Telangana, Tamil Nadu, Karnataka government finance portals |
| Phase 4 | Central Government integration: Union Budget, Finance Commission reports, PFMS data |

---

## Current Ingestion Status (as of Sep 6, 2026)

```
Documents Processed:    590 / 590  (100.0% COMPLETED)
Vector Chunks Live:     63,068     (Weaviate Cloud, 768-dim)
SQL Metadata Rows:      63,068     (Supabase PostgreSQL)
Financial Years:        2011-12 to 2026-27 (15 Years)
Pipeline Status:        COMPLETED (Exit Code: 0)

Progress: [██████████████████████████████] 100.0% COMPLETE
```

---

## Author

**Hemanth** — Built as Phase 1 of a comprehensive AP Government Intelligence Platform.
Designed to be open, auditable, and extensible for public sector AI applications.

---

*Data Source: Andhra Pradesh Finance Department — https://apfinance.gov.in*

*All documents are official government publications in the public domain.*
