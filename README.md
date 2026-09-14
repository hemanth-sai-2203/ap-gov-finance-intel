# 🏛️ Andhra Pradesh State Government Finance Intelligence Platform

> **An enterprise-grade, evidence-grounded AI research assistant & intelligence engine** covering 15+ years (2011–2027) of official Andhra Pradesh Government Finance publications — Budget Speeches, Departmental Estimates (Volumes I–VIII), AP Financial & Treasury Codes, FRBM Fiscal Compliance Reports, Pay Revision Commission (PRC) Orders, and Socio-Economic Surveys.

---

## 📌 Executive Summary

The **Andhra Pradesh Government Finance Intelligence Platform** solves the challenge of discovering, analyzing, and synthesizing public finance data scattered across hundreds of unstructured PDF volumes and disparate portal archives. 

Instead of manual search through tens of thousands of PDF pages, users can ask natural language questions and receive **statistically exact, policy-compliant, and fully cited answers** backed by clickable source provenance: `[Source: <Document Title>, <Financial Year>, Page <Page Number>]`.

```
                  ┌─────────────────────────────────────────────────────────┐
                  │          USER NATURAL LANGUAGE QUERY                   │
                  │   "What are the rules for re-appropriation of funds?"   │
                  └───────────────────────────┬─────────────────────────────┘
                                              │
                                              ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │                 QUERY ROUTER & EXPANDER                 │
                  │   Classifies: CATALOG | SQL | RAG | HYBRID | COMPARISON │
                  │   Injects AP Finance Terminology & Financial Years      │
                  └──────────────┬───────────────────────────┬──────────────┘
                                 │                           │
                   [Metadata / Numerical]            [Semantic / Policy]
                                 │                           │
                                 ▼                           ▼
            ┌───────────────────────────────┐   ┌──────────────────────────────┐
            │     DETERMINISTIC SQL ENGINE   │   │     HYBRID RETRIEVAL ENGINE   │
            │     (Supabase PostgreSQL)     │   │     (Weaviate Cloud)         │
            │  • Budget Estimates (BE)      │   │  • 768-dim Dense Vector      │
            │  • Revised Estimates (RE)     │   │  • BM25 Keyword Search       │
            │  • Actual Expenditure         │   │  • Reciprocal Rank Fusion    │
            │  • Document Metadata Catalog  │   └──────────────┬───────────────┘
            └──────────────┬────────────────┘                  │
                           │                                   ▼
                           │                    ┌──────────────────────────────┐
                           │                    │    CROSS-ENCODER RERANKER    │
                           │                    │ (ms-marco-MiniLM-L-6-v2)     │
                           │                    └──────────────┬───────────────┘
                           │                                   │
                           └─────────────────┬─────────────────┘
                                             │
                                             ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │               UNIFIED EVIDENCE BUNDLE                    │
                  │  Aggregates Structured SQL Stats + Ranked Context Chunks│
                  └──────────────────────────┬──────────────────────────────┘
                                             │
                                             ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │              GROUNDED LLM SYNTHESIS ENGINE              │
                  │              (Google Gemini 2.5 / 3.7 Flash)            │
                  │  • Anti-Hallucination Strict Evidence System Prompt     │
                  │  • Executive Summary + Key Findings + Page Citations    │
                  └──────────────────────────┬──────────────────────────────┘
                                             │
                                             ▼
                  ┌─────────────────────────────────────────────────────────┐
                  │                  FINAL STRUCTURED BRIEFING              │
                  │  Executive Takeaway | Detailed Findings | Provenance UI │
                  └─────────────────────────────────────────────────────────┘
```

---

## 🚀 Key Capabilities

- **Multi-Route Intent Classification**: Intelligently routes queries to **Deterministic SQL** (for math/totals), **Vector/BM25 Semantic Search** (for rules and policy narratives), **Document Catalog** (for publications listing), or **Hybrid Fusion** (for multi-dimensional queries).
- **Hybrid Retrieval with Reciprocal Rank Fusion (RRF)**: Combines 768-dimensional dense semantic vectors (`bge-base-en-v1.5`) with sparse BM25 lexical search for high precision on government terminology.
- **Two-Stage Cross-Encoder Reranking**: Re-scores top candidates using `cross-encoder/ms-marco-MiniLM-L-6-v2` to eliminate irrelevant context chunks before synthesis.
- **Strict Anti-Hallucination Prompting**: Mandates that every assertion and figure is backed by exact document provenance citations. Prevents fabricated budget figures.
- **Zero Ingestion Vectors in SQL**: Clean database separation where vector embeddings reside in **Weaviate Cloud** (10GB) while relational metadata and tabular budget numbers reside in **Supabase PostgreSQL**.

---

## 📊 Ingested Corpus Scope

| Dimension | Scope |
|---|---|
| **Total Publications** | 590 Official Government Documents |
| **Financial Timeline** | 2011–12 through 2026–27 (15 Financial Years) |
| **Passage Chunks Indexed** | 48,000+ Verified Sections |
| **Embedding Model** | `BAAI/bge-base-en-v1.5` (768-dimensional) |
| **Primary Sources** | Finance Department Portal (`apfinance.gov.in`) |

### Document Categories

| Category | Description | Sample Documents |
|---|---|---|
| `budget_speech` | Annual Budget Speeches by Finance Ministers | Budget Speech 2026-27, 2024-25, 2021-22 |
| `finance_manual` | Rules, Codal Provisions, Treasury Guides | A.P. Budget Manual, AP Financial Code, Treasury Code |
| `departmental_estimates` | Volumes I through VIII Detailed Budget Estimates | Vol III (Demands 1–17), Vol I (AFS), Vol IV (Public Accounts) |
| `frbm_compliance` | Fiscal Responsibility and Budget Management Statements | Medium Term Fiscal Policy Statements, Compliance Reviews |
| `prc_volumes` | Pay Revision Commission Reports & Scales | 11th PRC Comprehensive Reports, Pay Scales & Allowances |
| `guidelines_circulars`| Official Government Memos and Guidelines | Comprehensive Budget Release Order (CBRO), Smart Metering |
| `socio_economic_survey`| State-wide Economic Performance Overviews | Socio-Economic Survey Reports (2017–2025) |

---

## 🏗️ Detailed System Architecture

### 1. Ingestion Pipeline
```
[Raw PDFs from apfinance.gov.in]
             │
             ▼
   [PyMuPDF / pdfplumber] ──> Extracts text & page boundaries
             │
             ▼
    [Telugu-Script Filter] ──> Skips pure non-English scans
             │
             ▼
   [Recursive Text Splitter] ──> 1000 char chunks (200 char overlap)
             │
             ├────────────────────────────────────────┐
             ▼                                        ▼
  [Embedder (bge-base-en)]               [SQL Extractor (RegEx/Parser)]
  768-dim Vector Embeddings              Tabular Budget Estimates (BE/RE)
             │                                        │
             ▼                                        ▼
   [Weaviate Cloud Index]                  [Supabase PostgreSQL]
```

### 2. Retrieval & Generation Pipeline
1. **Query Router (`app/search/query_router.py`)**:
   - Parses temporal tags (`2026-27`, `2021`), department names, and document categories.
   - Enriches user queries with domain synonyms (e.g., `"re-appropriation"` → `"powers of reappropriation savings transfer AP Financial Code"`).
   - Directs query to `CATALOG`, `SQL`, `RAG`, `HYBRID`, or `COMPARISON`.

2. **Unified Retrieval (`app/search/engine.py`)**:
   - Pulls exact numbers from PostgreSQL tables using SQL `SUM`, `AVG`, and `GROUP BY`.
   - Runs Hybrid search (`alpha=0.65` dense, `0.35` BM25) on Weaviate Cloud.
   - Cross-encoder reranks top 15 candidate passages down to top 5 high-relevance evidence passages.

3. **Grounded Synthesis (`app/core/llm_engine.py`)**:
   - Injects structured evidence into a strict system prompt.
   - Generates an executive briefing layout via Google Gemini 2.5/3.7 Flash.
   - Extracts clickable source badges with page numbers for UI rendering.

---

## 📁 Repository Structure

```
Gov_intelligence_platform/
├── app/
│   ├── core/
│   │   ├── config.py              # Pydantic Settings & Environment Variables
│   │   ├── llm_engine.py          # Gemini Synthesis & Citation Formatter
│   │   ├── query_pipeline.py      # End-to-End Intelligence Pipeline Coordinator
│   │   └── weaviate_client.py     # Weaviate Cloud Connection Provider
│   ├── db/
│   │   ├── models.py              # SQLAlchemy Schema (documents, chunks, financial_records)
│   │   └── session.py             # Supabase PostgreSQL Session Management
│   ├── ingestion/
│   │   ├── chunker.py             # PDF text extraction & chunking
│   │   ├── embedder.py            # Local & API embedding generation (768-dim)
│   │   └── loader.py              # Multi-category PDF loader & crawler
│   ├── search/
│   │   ├── bm25_search.py         # BM25 Lexical Keyword Search
│   │   ├── engine.py              # Unified Retrieval Orchestrator
│   │   ├── hybrid_search.py       # Dense Vector + BM25 with RRF Fusion
│   │   ├── query_router.py        # Intent Classification & Query Expander
│   │   ├── reranker.py            # Cross-Encoder (ms-marco-MiniLM-L-6-v2)
│   │   ├── sql_engine.py          # Deterministic SQL Analytics & Catalog Queries
│   │   └── vector_search.py       # Pure Dense Vector Search
│   ├── ui/
│   │   └── index.html             # Interactive Glassmorphic Web Dashboard
│   └── main.py                    # FastAPI Application & REST Endpoints
├── data/                          # Downloaded PDF corpus (partitioned by category)
├── render.yaml                    # Production deployment configuration for Render
├── requirements.txt               # Python package dependencies
└── run_ingestion.py               # Batch corpus ingestion script
```

---

## 🛠️ REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves the interactive Web Portal Dashboard |
| `GET` | `/health` | System health status (Supabase SQL + Weaviate Cloud + Gemini LLM) |
| `GET` | `/api/stats` | Summary statistics of all ingested categories and years |
| `POST` | `/api/query` | **Main Intelligence Query**: Hybrid Search + SQL + Reranking + Gemini LLM synthesis |
| `POST` | `/api/search` | **Raw Search**: Returns ranked evidence passages with scores without LLM synthesis |
| `GET` | `/api/documents` | List ingested publications filtered by year or category |
| `GET` | `/api/budget/total` | Aggregated total budget estimate and expenditure for a financial year |
| `GET` | `/api/budget/department` | Specific department budget allocation across schemes |
| `GET` | `/api/budget/top-departments` | Top departments ranked by budget allocation |

### Example Request (`POST /api/query`):
```json
{
  "query": "What are the rules for re-appropriation of budget funds under the AP Financial Code?",
  "top_k": 5
}
```

### Example Response:
```json
{
  "query": "What are the rules for re-appropriation of budget funds under the AP Financial Code?",
  "query_type": "rag",
  "answer": "### 📋 Executive Summary\nRe-appropriation of funds under the Andhra Pradesh Financial Code involves the transfer of savings from one head of account to another within the same grant...\n\n### 🔍 Key Findings & Policy Provisions\n* **Sanction Powers:** Re-appropriation sanctions cannot be made between different Grants or from Capital to Revenue accounts [Source: AP Budget Manual 2011, General, Page 42].\n* **Savings Transfer Restrictions:** No re-appropriation is permissible from salaries to non-salary heads without Finance Department concurrence.\n\n### 📑 Document Context & Observations\nGoverned under Chapter IX of the Andhra Pradesh Budget Manual and Article 324 of the AP Financial Code Volume I.",
  "citations": [
    {
      "title": "A.P. Budget Manual (2011)",
      "financial_year": "2011-12",
      "page_number": 42,
      "relevance_score": 0.892,
      "citation_label": "[Source: A.P. Budget Manual (2011), 2011-12, Page 42]"
    }
  ],
  "model_used": "gemini-2.5-flash"
}
```

---

## 💻 Local Setup & Development

### 1. Prerequisites
- Python 3.10+
- Access credentials for:
  - **Google Gemini API Key**
  - **Weaviate Cloud Cluster URL & API Key**
  - **Supabase PostgreSQL Database URL**

### 2. Installation
```bash
# Clone repository
git clone https://github.com/hemanth-sai-2203/ap-gov-finance-intel.git
cd ap-gov-finance-intel

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate      # On Windows
source venv/bin/activate    # On Linux/macOS

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the root directory:
```env
# Application
PROJECT_NAME="AP Government Finance Intelligence Platform"
ENVIRONMENT="development"

# PostgreSQL (Supabase)
DATABASE_URL="postgresql://postgres.xxx:password@aws-0-ap-southeast-2.pooler.supabase.com:6543/postgres"

# Weaviate Cloud (Vector DB)
WEAVIATE_URL="https://xxx.weaviate.network"
WEAVIATE_API_KEY="your-weaviate-api-key"

# LLM & Embedding Keys
GEMINI_API_KEY="your-gemini-api-key"
GEMINI_MODEL="gemini-2.5-flash"
EMBEDDING_MODEL_NAME="BAAI/bge-base-en-v1.5"
```

### 4. Running the Application
```bash
# Start FastAPI backend with Uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser and navigate to:
- **Web Dashboard**: `http://localhost:8000`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 🚢 Deployment

The platform is configured for zero-downtime deployment on **Render** using `render.yaml`:

```yaml
services:
  - type: web
    name: ap-gov-finance-intel
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn app.main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
```

---

## 📄 License & Attribution

Developed for public finance transparency, evidence-grounded policy analysis, and academic research on the official budgetary data of the **Government of Andhra Pradesh**. All ingested documents are official public publications released by the Finance Department, Government of Andhra Pradesh.
