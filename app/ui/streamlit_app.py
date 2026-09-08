import streamlit as st
import httpx
import pandas as pd
import plotly.express as px
import os

# Page Configuration
st.set_page_config(
    page_title="AP Government Finance Intelligence",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #38BDF8;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    .badge-sql {
        background-color: #1E40AF;
        color: #DBEAFE;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-rag {
        background-color: #166534;
        color: #DCFCE7;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .badge-hybrid {
        background-color: #92400E;
        color: #FEF3C7;
        padding: 4px 12px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
        display: inline-block;
    }
    .citation-card {
        background-color: #1E293B;
        border-left: 4px solid #38BDF8;
        padding: 14px;
        border-radius: 6px;
        margin-bottom: 12px;
        color: #E2E8F0;
    }
</style>
""", unsafe_allow_html=True)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

def check_backend():
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False

# Sidebar
with st.sidebar:
    st.image("https://upload.wikimedia.org/wikipedia/commons/3/37/Emblem_of_Andhra_Pradesh.svg", width=80)
    st.title("AP Gov Intelligence")
    st.caption("State Budget & Fiscal Intelligence System")
    
    is_healthy = check_backend()
    if is_healthy:
        st.success("🟢 API Server Connected")
    else:
        st.error("🔴 API Server Offline (Ensure port 8000 is running)")

    st.markdown("---")
    st.markdown("### 📊 Financial Years Active")
    st.markdown("- **2011-12 to 2026-27** (15 Years)")

    st.markdown("---")
    st.markdown("### ⚙️ Engine Architecture")
    st.markdown("- **Deterministic SQL**: Supabase PostgreSQL")
    st.markdown("- **Dense Vector Search**: Weaviate Cloud (768-dim `bge-base-en-v1.5`)")
    st.markdown("- **Sparse Search**: Weaviate BM25 Full-Text")
    st.markdown("- **Reranker**: Cross-Encoder (`ms-marco-MiniLM-L-6-v2`)")
    st.markdown("- **LLM Synthesis**: Google Gemini 2.5 Flash")

# Main Header
st.markdown('<div class="main-header">🏛️ Andhra Pradesh Government Finance Intelligence</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Searchable, evidence-grounded intelligence from official AP Finance Department sources.</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["🔍 Intelligence Assistant", "📈 Budget Explorer", "📄 Official Documents"])

# TAB 1: INTELLIGENCE ASSISTANT
with tab1:
    st.markdown("#### Ask Any Question About AP Finances")
    
    # Initialize query state
    if "current_query" not in st.session_state:
        st.session_state.current_query = ""

    # Quick Suggestion Chips
    st.markdown("**Quick Prompts (Click to try):**")
    chip_cols = st.columns(3)
    
    if chip_cols[0].button("📊 Education Budget in 2026-27", use_container_width=True):
        st.session_state.current_query = "What was the school education budget in 2026-27?"
    if chip_cols[1].button("🌾 Agriculture & Subsidy Schemes", use_container_width=True):
        st.session_state.current_query = "What are the key schemes funded under Agriculture?"
    if chip_cols[2].button("⚖️ Compare Education 2025-26 vs 2026-27", use_container_width=True):
        st.session_state.current_query = "Compare education spending between 2025-26 and 2026-27."

    col_input, col_filters = st.columns([3, 1])
    with col_input:
        user_query = st.text_input(
            "Enter your question:",
            value=st.session_state.current_query,
            placeholder="e.g. What is the budget allocation for Agriculture in 2026-27?",
            key="query_input"
        )
        ask_btn = st.button("🚀 Analyze & Generate Evidence", type="primary", use_container_width=True)

    with col_filters:
        st.markdown("**Filters (Optional)**")
        fy_filter = st.selectbox("Financial Year:", ["All", "2026-27", "2025-26", "2024-25"])
        dept_filter = st.text_input("Department:", placeholder="e.g. Education, Health")

    # Execute query when button clicked or Enter pressed
    if ask_btn and user_query:
        with st.spinner("Routing query, executing SQL/Vector retrieval, and synthesizing answer..."):
            payload = {
                "query": user_query,
                "financial_year": None if fy_filter == "All" else fy_filter,
                "department": dept_filter.strip() if dept_filter.strip() else None,
                "top_k": 5
            }
            
            try:
                resp = httpx.post(f"{API_BASE_URL}/api/query", json=payload, timeout=60.0)
                if resp.status_code == 200:
                    data = resp.json()
                    
                    st.markdown("---")
                    
                    # Routing Info Header
                    q_type = data.get("query_type", "Unknown").upper()
                    badge_class = f"badge-{q_type.lower()}"
                    
                    col_info1, col_info2, col_info3 = st.columns([2, 1, 1])
                    with col_info1:
                        st.markdown(f"**Query Intent / Router Decision:** <span class='{badge_class}'>{q_type}</span>", unsafe_allow_html=True)
                    with col_info2:
                        if data.get("financial_year"):
                            st.markdown(f"**Year:** `{data['financial_year']}`")
                    with col_info3:
                        if data.get("department"):
                            st.markdown(f"**Dept:** `{data['department']}`")
                            
                    st.markdown("### 📝 Grounded Answer")
                    st.info(data.get("answer", "No answer generated."))
                    
                    # Citations Block
                    st.markdown("### 🏷️ Verified Evidence & Sources")
                    citations = data.get("citations", [])
                    if citations:
                        for idx, cit in enumerate(citations, 1):
                            st.markdown(f"""
                            <div class="citation-card">
                                <strong>#{idx} {cit.get('title', 'Document')}</strong><br/>
                                <span>Financial Year: <b>{cit.get('financial_year', 'N/A')}</b> | Page: <b>{cit.get('page', 'N/A')}</b></span><br/>
                                <span>Official Source: <a href="{cit.get('url', '#')}" target="_blank" style="color:#38BDF8;">{cit.get('url', 'N/A')}</a></span>
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.caption("No direct citations attached.")

                    # Raw Evidence Accordion
                    with st.expander("🔍 Inspect Underlying Retrieved Evidence (SQL & Vector)"):
                        if data.get("sql_results"):
                            st.markdown("**Structured SQL Results:**")
                            st.json(data["sql_results"])
                        if data.get("rag_results"):
                            st.markdown("**Reranked Document Chunks:**")
                            for r in data["rag_results"]:
                                st.markdown(f"- **Page {r.get('page_number')}** (Rerank Score: `{r.get('rerank_score'):.3f}`, Method: `{r.get('retrieval_method')}`):")
                                st.text(r.get("text"))
                                st.caption(f"Source: {r.get('source_url')}")
                else:
                    st.error(f"API Error {resp.status_code}: {resp.text}")
            except Exception as e:
                st.error(f"Failed to connect to backend: {e}")

# TAB 2: BUDGET EXPLORER
with tab2:
    st.markdown("### 📊 AP Structured Budget Explorer")
    st.caption("Deterministic aggregations across 1,850 budget allocation records (SQL).")
    
    col_exp1, col_exp2 = st.columns(2)
    with col_exp1:
        sel_year = st.selectbox("Select Budget Year:", ["2026-27", "2025-26", "2024-25"], key="exp_year")
    
    with col_exp2:
        try:
            total_resp = httpx.get(f"{API_BASE_URL}/api/budget/total?financial_year={sel_year}", timeout=10.0)
            if total_resp.status_code == 200:
                t_data = total_resp.json()
                be_val = t_data.get("total_budget_estimate")
                re_val = t_data.get("total_revised_estimate")
                act_val = t_data.get("total_actual_expenditure")
                
                m1, m2, m3 = st.columns(3)
                m1.metric("Budget Estimate", f"₹{be_val:,.2f} Cr" if be_val else "₹ -- Cr")
                m2.metric("Revised Estimate", f"₹{re_val:,.2f} Cr" if re_val else "₹ -- Cr")
                m3.metric("Actual Exp.", f"₹{act_val:,.2f} Cr" if act_val else "₹ -- Cr")
        except Exception:
            st.caption("Unable to fetch total metrics.")

    st.markdown("---")
    st.markdown("#### Department Allocations Lookup")
    dept_query = st.text_input("Search Department Name:", value="Education", key="dept_lookup")
    
    if dept_query:
        try:
            d_resp = httpx.get(f"{API_BASE_URL}/api/budget/department?department={dept_query}&financial_year={sel_year}", timeout=10.0)
            if d_resp.status_code == 200:
                allocs = d_resp.json().get("allocations", [])
                if allocs:
                    df = pd.DataFrame(allocs)
                    st.dataframe(df, use_container_width=True)
                else:
                    st.info(f"No structured rows found for '{dept_query}' in {sel_year}.")
        except Exception as e:
            st.error(f"Error: {e}")

# TAB 3: OFFICIAL DOCUMENTS
with tab3:
    st.markdown("### 📄 Ingested Official AP Government Documents")
    st.caption("Official Andhra Pradesh State Finance publications indexed in Supabase PostgreSQL & Weaviate Cloud.")
    
    try:
        docs_resp = httpx.get(f"{API_BASE_URL}/api/documents", timeout=10.0)
        if docs_resp.status_code == 200:
            docs_data = docs_resp.json().get("documents", [])
            if docs_data:
                docs_df = pd.DataFrame(docs_data)
                st.dataframe(docs_df, use_container_width=True)
            else:
                st.info("No documents found in repository.")
    except Exception as e:
        st.error(f"Failed to fetch documents: {e}")
