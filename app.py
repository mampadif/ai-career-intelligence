import streamlit as st
import google.generativeai as genai
import PyPDF2
import docx
import requests
import stripe
import json
import re
from datetime import datetime
from fpdf import FPDF

# ---------------------------
# 1. Configuration & Secrets
# ---------------------------
st.set_page_config(page_title="AI Career Intelligence", page_icon="📈", layout="centered")

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
STRIPE_SECRET_KEY = st.secrets["STRIPE_SECRET_KEY"]
STRIPE_PRICE_ID = st.secrets["STRIPE_PRICE_ID"]
JOB_API_KEY = st.secrets["JOB_API_KEY"]
ADZUNA_APP_ID = st.secrets["ADZUNA_APP_ID"]
APP_URL = st.secrets["APP_URL"]
PRO_UNLOCK_CODE = st.secrets["PRO_UNLOCK_CODE"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.0-flash-exp")
stripe.api_key = STRIPE_SECRET_KEY

# ---------------------------
# 2. Session State & Stripe Callback
# ---------------------------
if "paid" not in st.session_state:
    st.session_state.paid = False
if "cv_text" not in st.session_state:
    st.session_state.cv_text = ""
if "analysis_free" not in st.session_state:
    st.session_state.analysis_free = None
if "manual_job_query" not in st.session_state:
    st.session_state.manual_job_query = ""

if "success" in st.query_params:
    st.session_state.paid = True
    st.query_params.clear()

# ---------------------------
# 3. Helper Functions
# ---------------------------
def extract_text_from_file(uploaded_file):
    if uploaded_file.name.endswith(".pdf"):
        reader = PyPDF2.PdfReader(uploaded_file)
        return "".join(page.extract_text() for page in reader.pages)
    elif uploaded_file.name.endswith(".docx"):
        doc = docx.Document(uploaded_file)
        return "\n".join(para.text for para in doc.paragraphs)
    else:
        return uploaded_file.read().decode("utf-8")

def clean_json_response(text):
    match = re.search(r'\{.*\}', text, re.DOTALL)
    return match.group(0) if match else text

def analyze_cv(cv_text, full=False):
    prompt = f"""
    Analyze this CV as a professional recruiter. Return ONLY valid JSON.

    Required fields (always):
    - strength_score (0-100)
    - ats_score (0-100)
    - recruiter_verdict (one sentence)
    - interview_probability (0-100)
    - experience_level ("Entry","Mid","Senior")
    - target_roles (list of 2-3)
    - top_strengths (list of 2-3)
    - top_weaknesses (list of 2-3)

    If full == true, also include:
    - missing_keywords (list of 4-8)
    - rewrite_suggestions (list of 3-5)

    CV:
    {cv_text[:10000]}
    """
    response = model.generate_content(prompt + f"\nFull: {full}")
    raw = clean_json_response(response.text)
    try:
        return json.loads(raw)
    except:
        return {
            "strength_score": 50,
            "ats_score": 50,
            "recruiter_verdict": "Unable to analyze – please try again.",
            "interview_probability": 50,
            "experience_level": "Mid",
            "target_roles": ["N/A"],
            "top_strengths": ["Error parsing response"],
            "top_weaknesses": ["Error parsing response"]
        }

@st.cache_data(show_spinner=False, ttl=3600)
def analyze_cv_cached(cv_text, full=False):
    return analyze_cv(cv_text, full)

@st.cache_data(ttl=3600)   # <-- FIX: cache job query generation
def generate_job_query(cv_text):
    prompt = f"""
    Extract 3 likely job titles from this CV.
    Return ONLY comma-separated titles.
    No explanation.
    CV:
    {cv_text[:6000]}
    """
    return model.generate_content(prompt).text.strip()

def get_job_matches(cv_text, analysis, manual_query, country_code, location_refine, limit=3):
    query = generate_job_query(cv_text)
    if manual_query and len(manual_query) > 2:
        query = manual_query
    elif not query or len(query) < 3:
        target_roles = analysis.get('target_roles', [])
        if target_roles and target_roles[0] != "N/A":
            query = target_roles[0]
        else:
            return []
    
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": JOB_API_KEY,
        "results_per_page": limit,
        "what": query,
        "content-type": "json"
    }
    if location_refine and location_refine.strip():
        params["where"] = location_refine.strip()
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            jobs = resp.json().get("results", [])
            return [{
                "title": j["title"],
                "company": j["company"]["display_name"],
                "url": j["redirect_url"],
                "description": j.get("description", "")
            } for j in jobs]
    except Exception as e:
        st.error(f"Job search error: {e}")
    return []

@st.cache_data(ttl=3600)
def score_job_match(cv_text, job_title, job_description=""):
    prompt = f"Score 0-100 match between CV and job '{job_title}'. Return integer.\nCV snippet:\n{cv_text[:2000]}\nDescription:\n{job_description[:500]}"
    response = model.generate_content(prompt)
    try:
        return int(response.text.strip())
    except:
        return 50

def safe_encode(text):
    return text.encode('latin-1', 'ignore').decode('latin-1')

def generate_pdf_report(analysis_full):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, safe_encode("AI Career Intelligence Report"), ln=True)
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, safe_encode(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", size=12)
    for k, v in analysis_full.items():
        if isinstance(v, list):
            v = ", ".join(v)
        line = safe_encode(f"{k.replace('_', ' ').title()}: {v}")
        pdf.multi_cell(0, 8, line)
    return pdf.output(dest='S').encode('latin-1')

def generate_ats_checklist(analysis_full):
    checklist = "✅ ATS OPTIMIZATION CHECKLIST\n\n"
    checklist += "Missing Keywords to Add:\n" + "\n".join(f"  • {kw}" for kw in analysis_full.get('missing_keywords', [])) + "\n\n"
    checklist += "Rewrite Suggestions:\n" + "\n".join(f"  • {sug}" for sug in analysis_full.get('rewrite_suggestions', [])) + "\n\n"
    checklist += "General Tips:\n  • Use action verbs\n  • Quantify achievements\n  • Tailor summary to target role"
    return checklist

# ---------------------------
# 4. UI
# ---------------------------
st.title("📈 AI Career Intelligence")
st.markdown("Upload your CV → Get ATS score, recruiter verdict, and personalized job matches worldwide.")

if not st.session_state.paid:
    st.info("🔓 **Upgrade to Pro** – Unlock full rewrite suggestions, missing keywords, unlimited job matches, and PDF export.")

uploaded_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    cv_text = extract_text_from_file(uploaded_file)
    st.session_state.cv_text = cv_text

    with st.spinner("Analyzing with Gemini AI..."):
        analysis = analyze_cv_cached(cv_text, full=False)
        st.session_state.analysis_free = analysis

    # Metrics row
    col1, col2, col3 = st.columns(3)
    col1.metric("📊 Strength Score", f"{analysis['strength_score']}/100")
    col2.metric("🤖 ATS Score", f"{analysis['ats_score']}/100")
    col3.metric("🎯 Interview Probability", f"{analysis['interview_probability']}%")

    st.info(f"**Recruiter Verdict:** {analysis['recruiter_verdict']}")

    # Free insights
    st.subheader("📌 Key Insights")
    st.markdown(f"**Experience Level:** {analysis['experience_level']}")
    st.markdown(f"**Target Roles:** {', '.join(analysis['target_roles'])}")
    with st.expander("Strengths & Weaknesses"):
        st.markdown("**Strengths:**\n" + "\n".join(f"- {s}" for s in analysis['top_strengths']))
        st.markdown("**Weaknesses:**\n" + "\n".join(f"- {w}" for w in analysis['top_weaknesses']))

    # Job search settings
    st.subheader("🌍 Job Search Settings")
    col_loc1, col_loc2 = st.columns(2)
    with col_loc1:
        country_code = st.selectbox(
            "Country",
            options=[
                "us", "gb", "ca", "au", "de", "fr", "in", "za", "es", "it", "nl", 
                "br", "mx", "sg", "ae", "pl", "se", "no", "dk", "fi", "ch", "at", 
                "be", "ie", "nz", "hk", "my", "ph", "th", "vn", "id", "kr", "jp", 
                "tr", "il", "sa", "eg", "ma", "ng", "ke", "pk", "lk", "np", "bd", 
                "ua", "ro", "cz", "hu", "gr", "pt", "ar", "cl", "co", "pe", "ve", 
                "cr", "pa", "do", "pr"
            ],
            format_func=lambda x: {
                "us": "United States", "gb": "United Kingdom", "ca": "Canada", 
                "au": "Australia", "de": "Germany", "fr": "France", "in": "India", 
                "za": "South Africa", "es": "Spain", "it": "Italy", "nl": "Netherlands",
                "br": "Brazil", "mx": "Mexico", "sg": "Singapore", "ae": "UAE",
                "pl": "Poland", "se": "Sweden", "no": "Norway", "dk": "Denmark",
                "fi": "Finland", "ch": "Switzerland", "at": "Austria", "be": "Belgium",
                "ie": "Ireland", "nz": "New Zealand", "hk": "Hong Kong", "my": "Malaysia",
                "ph": "Philippines", "th": "Thailand", "vn": "Vietnam", "id": "Indonesia",
                "kr": "South Korea", "jp": "Japan", "tr": "Turkey", "il": "Israel",
                "sa": "Saudi Arabia", "eg": "Egypt", "ma": "Morocco", "ng": "Nigeria",
                "ke": "Kenya", "pk": "Pakistan", "lk": "Sri Lanka", "np": "Nepal",
                "bd": "Bangladesh", "ua": "Ukraine", "ro": "Romania", "cz": "Czech Republic",
                "hu": "Hungary", "gr": "Greece", "pt": "Portugal", "ar": "Argentina",
                "cl": "Chile", "co": "Colombia", "pe": "Peru", "ve": "Venezuela",
                "cr": "Costa Rica", "pa": "Panama", "do": "Dominican Republic", "pr": "Puerto Rico"
            }.get(x, x.upper()),
            index=0
        )
    with col_loc2:
        location_refine = st.text_input("City / Region (optional)", placeholder="e.g., Gaborone, Cape Town, Remote")

    if country_code == "za":
        st.caption("🇿🇦 South Africa has strong job coverage. For other African countries, select South Africa and specify your city/region.")
    elif country_code in ["eg", "ma", "ng", "ke"]:
        st.caption(f"✅ Job coverage available for {country_code.upper()}.")
    else:
        st.caption("🌍 For African countries not listed, select 'South Africa' and specify your city/region in the field above.")

    manual_query = st.text_input(
        "Optional: Override detected job title (e.g., 'Registered Nurse', 'Marketing Manager')",
        value=st.session_state.manual_job_query,
        key="manual_job_input"
    )
    st.session_state.manual_job_query = manual_query

    # Free job matches (3, no scores)
    st.subheader("💼 Matching Jobs (Preview)")
    free_jobs = get_job_matches(cv_text, analysis, manual_query, country_code, location_refine, limit=3)
    if free_jobs:
        for job in free_jobs:
            st.markdown(f"**{job['title']}** at {job['company']} – [Apply]({job['url']})")
    else:
        st.warning("No jobs found. Try adjusting job title or location.")

    # ---------------------------
    # CONVERSION SECTION (Upgrade)
    # ---------------------------
    if not st.session_state.paid:
        st.markdown("---")
        st.header("🏆 Unlock the Pro Career Suite")

        c1, c2, c3 = st.columns(3)
        c1.write("🎯 **ATS Optimization**\nGet the exact keywords missing from your CV.")
        c2.write("📝 **Bullet Point Rewrites**\nProfessional AI‑rewritten achievements.")
        c3.write("📑 **Executive PDF**\nDownloadable report for your records.")

        st.markdown("#### 🔒 Pro Preview: Missing Keywords")
        st.info("`Docker`, `AWS`, `Power BI`, `Leadership metrics` (UPGRADE TO SEE YOURS)")

        col_left, col_right = st.columns(2)
        with col_left:
            # Updated button text
            if st.button("💳 Unlock Full Career Optimization – $9"):
                try:
                    checkout_session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                        mode="payment",
                        success_url=APP_URL + "?success=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{checkout_session.url}' target='_blank'>Pay securely with Stripe</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Payment error: {e}")
        with col_right:
            unlock_code = st.text_input("Unlock code (if already purchased)", type="password")
            if unlock_code == PRO_UNLOCK_CODE:
                st.session_state.paid = True
                st.success("Pro access granted! Refreshing...")
                st.rerun()

    # ---------------------------
    # PAID SECTION
    # ---------------------------
    else:
        st.balloons()
        st.success("✅ Pro access unlocked – generating your full report...")
        with st.spinner("Creating detailed improvement plan..."):
            full_analysis = analyze_cv_cached(cv_text, full=True)

        st.subheader("🔑 Missing ATS Keywords")
        st.markdown(", ".join(full_analysis.get('missing_keywords', [])))

        st.subheader("✍️ Rewrite Suggestions")
        for sug in full_analysis.get('rewrite_suggestions', []):
            st.markdown(f"- {sug}")

        col_pdf, col_check = st.columns(2)
        with col_pdf:
            pdf_data = generate_pdf_report(full_analysis)
            st.download_button("📥 Download Full PDF Report", pdf_data, file_name="career_report.pdf")
        with col_check:
            checklist_text = generate_ats_checklist(full_analysis)
            st.download_button("📋 Download ATS Checklist", checklist_text, file_name="ats_checklist.txt")

        st.subheader("🚀 AI‑Ranked Job Matches (Pro)")
        with st.spinner("Finding jobs..."):
            pro_jobs = get_job_matches(cv_text, full_analysis, manual_query, country_code, location_refine, limit=15)
        if pro_jobs:
            for idx, job in enumerate(pro_jobs):
                with st.expander(f"**{job['title']}** at {job['company']}"):
                    if st.button(f"🔍 Show Match Score", key=f"score_btn_{idx}"):
                        match_score = score_job_match(cv_text, job['title'], job.get('description', ''))
                        st.write(f"**AI Match Score:** {match_score}%")
                        st.markdown(f"[Apply Now]({job['url']})")
                    else:
                        st.markdown(f"[Apply without AI analysis]({job['url']})")
        else:
            st.warning("No jobs found. Try adjusting job title or location.")
        st.info("📧 Email alerts for new jobs – coming soon.")

else:
    st.info("👆 Please upload your CV to begin.")

st.markdown("---")
st.caption("AI Career Intelligence – Powered by Gemini 2.0 | Job data by Adzuna")