import streamlit as st
import requests
from bs4 import BeautifulSoup
from langchain_openai import ChatOpenAI

# ==========================================
# PAGE CONFIG (Mobile Friendly)
# ==========================================
st.set_page_config(
    page_title="Mobile Legal Research",
    page_icon="⚖️",
    initial_sidebar_state="collapsed"
)

# Initialize Session State Variables
if "selected_opinion_id" not in st.session_state:
    st.session_state.selected_opinion_id = None
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "case_details_cache" not in st.session_state:
    st.session_state.case_details_cache = {}

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def search_courtlistener(query: str, court_code: str, api_key: str):
    url = "https://www.courtlistener.com/api/rest/v4/search/"
    headers = {"Authorization": f"Token {api_key}"} if api_key else {}
    params = {
        "q": query,
        "type": "o",
        "stat_Precedential": "on",
    }
    if court_code and court_code != "all":
        params["court"] = court_code

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        results = []
        for item in data.get("results", []):
            results.append({
                "id": item.get("id"),
                "case_name": item.get("caseName") or "Unknown Case",
                "citations": item.get("citation", []),
                "court": item.get("court", "Unknown Court"),
                "date_filed": item.get("dateFiled", "N/A"),
                "snippet": item.get("snippet", ""),
                "opinion_id": item.get("opinion_id") or item.get("id")
            })
        return results
    except Exception as e:
        st.error(f"Error querying CourtListener API: {e}")
        return []

def get_full_opinion(opinion_id: int, api_key: str):
    if opinion_id in st.session_state.case_details_cache:
        return st.session_state.case_details_cache[opinion_id]

    url = f"https://www.courtlistener.com/api/rest/v4/opinions/{opinion_id}/"
    headers = {"Authorization": f"Token {api_key}"} if api_key else {}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        raw_html = data.get("html_with_citations") or data.get("html") or data.get("plain_text") or "No text available."
        soup = BeautifulSoup(raw_html, "html.parser")
        text_content = soup.get_text(separator="\n")

        result = {
            "html": raw_html,
            "plain_text": text_content,
            "author": data.get("author_str", "Unknown")
        }
        st.session_state.case_details_cache[opinion_id] = result
        return result
    except Exception as e:
        return {"html": f"Error fetching opinion: {e}", "plain_text": "", "author": "Unknown"}

def generate_ai_memo(query: str, selected_cases: list, openai_key: str):
    if not openai_key:
        return "Please open the left sidebar menu and enter your OpenAI API key."

    context = ""
    for idx, case in enumerate(selected_cases, 1):
        context += f"\n--- CASE {idx} ---\n"
        context += f"Case Title: {case['case_name']}\n"
        context += f"Citations: {', '.join(case['citations']) if case['citations'] else 'N/A'}\n"
        context += f"Court: {case['court']} | Date: {case['date_filed']}\n"
        context += f"Excerpt: {case['snippet']}\n"

    system_prompt = (
        "You are an expert legal research assistant like Casetext CoCounsel.\n"
        "Analyze the provided cases and answer the legal question.\n"
        "RULES:\n"
        "1. Cite ONLY the provided cases using standard Bluebook/legal citations.\n"
        "2. Include direct quotes and pinpoint details where relevant.\n"
        "3. Explicitly lay out binding vs persuasive authority based on the court."
    )

    try:
        llm = ChatOpenAI(model="gpt-4o", openai_api_key=openai_key, temperature=0)
        prompt = f"{system_prompt}\n\nRELEVANT CASES:\n{context}\n\nUSER QUESTION:\n{query}"
        res = llm.invoke(prompt)
        return res.content
    except Exception as e:
        return f"AI Error: {e}"

# ==========================================
# SIDEBAR CONTROLS (Drawer on Mobile)
# ==========================================
st.sidebar.title("⚙️ Settings & Keys")
courtlistener_token = st.sidebar.text_input("CourtListener API Token (Optional)", type="password")
openai_api_key = st.sidebar.text_input("OpenAI API Key (Required for AI)", type="password")

jurisdiction = st.sidebar.selectbox(
    "Jurisdiction / Court Filter",
    options=[
        ("All Courts", "all"),
        ("U.S. Supreme Court", "scotus"),
        ("9th Circuit Court of Appeals", "ca9"),
        ("2nd Circuit Court of Appeals", "ca2"),
        ("California Supreme Court", "cal"),
        ("New York Court of Appeals", "ny"),
        ("Federal District Courts", "fsupp"),
    ],
    format_func=lambda x: x[0]
)[1]

# ==========================================
# MAIN INTERFACE (Single-Column Mobile Stack)
# ==========================================
st.title("⚖️ Mobile Case Search")

# Search Bar
search_query = st.text_input("Enter Query / Topic", placeholder="e.g., qualified immunity summary judgment", key="query_input")
if st.button("🔍 Search Cases", type="primary", use_container_width=True):
    if search_query:
        with st.spinner("Searching..."):
            st.session_state.search_results = search_courtlistener(search_query, jurisdiction, courtlistener_token)
            st.session_state.selected_opinion_id = None

# Results & Features Stack
if st.session_state.search_results:
    st.divider()
    
    # Navigation Tabs for Mobile View
    tab_results, tab_ai, tab_reader = st.tabs(["📋 Cases Found", "🤖 AI Memo", "📖 Case Reader"])
    
    selected_for_ai = []
    
    # Tab 1: Cases Found
    with tab_results:
        st.caption(f"Found {len(st.session_state.search_results)} cases for selected jurisdiction.")
        for case in st.session_state.search_results:
            with st.expander(f"**{case['case_name']}** ({case['date_filed'][:4] if case['date_filed'] else 'N/A'})"):
                c_str = ", ".join(case['citations']) if case['citations'] else 'No official citation'
                st.markdown(f"**Citation:** `{c_str}`")
                st.markdown(f"**Court:** `{case['court'].upper()}`")
                st.caption(f"Snippet: ...{case['snippet']}...")
                
                chk = st.checkbox("Include in AI Memo", key=f"chk_{case['id']}_{idx}", value=True)
                if chk:
                    selected_for_ai.append(case)
                
                if st.button("Open Full Text", key=f"read_{case['id']}", use_container_width=True):
                    st.session_state.selected_opinion_id = case['opinion_id']
                    st.success("Case loaded into '📖 Case Reader' tab above!")

    # Tab 2: AI Legal Assistant
    with tab_ai:
        st.subheader("🤖 AI Legal Synthesis")
        st.caption("Extracts holdings & generates Bluebook citations based on your checked cases.")
        if st.button("Synthesize Selected Cases", type="primary", use_container_width=True):
            if not selected_for_ai:
                st.warning("Please check at least one case in the 'Cases Found' tab.")
            else:
                with st.spinner("Generating legal memo..."):
                    memo = generate_ai_memo(search_query, selected_for_ai, openai_api_key)
                    st.markdown(memo)

    # Tab 3: Reader View
    with tab_reader:
        if st.session_state.selected_opinion_id:
            opinion_data = get_full_opinion(st.session_state.selected_opinion_id, courtlistener_token)
            st.caption(f"Author: {opinion_data['author']}")
            st.divider()
            st.components.v1.html(opinion_data['html'], height=500, scrolling=True)
        else:
            st.info("Select 'Open Full Text' on any case in the 'Cases Found' tab to read the full opinion here.")
