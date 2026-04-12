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
from io import BytesIO
from docx import Document

# ---------------------------
# 1. Configuration & Secrets
# ---------------------------
st.set_page_config(page_title="AI Career Intelligence", page_icon="📈", layout="centered")

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
STRIPE_SECRET_KEY = st.secrets["STRIPE_SECRET_KEY"]
STRIPE_PRICE_ID_PREMIUM_MONTHLY = st.secrets["STRIPE_PRICE_ID_PREMIUM_MONTHLY"]
STRIPE_PRICE_ID_PREMIUM_LIFETIME = st.secrets["STRIPE_PRICE_ID_PREMIUM_LIFETIME"]
STRIPE_PRICE_ID_PRO_MONTHLY = st.secrets["STRIPE_PRICE_ID_PRO_MONTHLY"]
STRIPE_PRICE_ID_PRO_LIFETIME = st.secrets["STRIPE_PRICE_ID_PRO_LIFETIME"]
JOB_API_KEY = st.secrets["JOB_API_KEY"]
ADZUNA_APP_ID = st.secrets["ADZUNA_APP_ID"]
APP_URL = st.secrets["APP_URL"]
PREMIUM_UNLOCK_CODE = st.secrets["PREMIUM_UNLOCK_CODE"]
PRO_UNLOCK_CODE = st.secrets["PRO_UNLOCK_CODE"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")
stripe.api_key = STRIPE_SECRET_KEY

# Country mapping
COUNTRY_MAP = {
    "United States": "us",
    "United Kingdom": "gb",
    "Canada": "ca",
    "Australia": "au",
    "Germany": "de",
    "France": "fr",
    "India": "in",
    "South Africa": "za",
    "Nigeria": "ng",
    "Kenya": "ke",
    "Botswana": "bw",
    "Ghana": "gh",
    "Other": "other"
}

# ---------------------------
# 2. Custom CSS
# ---------------------------
st.markdown("""
<style>
body { background-color: #f7f9fc; }
[data-testid="metric-container"] {
    background-color: #ffffff;
    border-radius: 12px;
    padding: 15px;
    border: 1px solid #e6ebf2;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.stButton > button {
    border-radius: 10px;
    background: linear-gradient(90deg, #4A90E2, #6C63FF);
    color: white;
    font-weight: 600;
    border: none;
    transition: transform 0.2s;
}
.stButton > button:hover {
    transform: translateY(-2px);
    background: linear-gradient(90deg, #3a7bc8, #5a52d9);
}
.upgrade-box {
    background: linear-gradient(135deg, #6C63FF, #4A90E2);
    color: white;
    padding: 25px;
    border-radius: 16px;
    margin: 20px 0;
    text-align: center;
}
.upgrade-box h3, .upgrade-box p { color: white; }
.pricing-card {
    background-color: #ffffff;
    border-radius: 12px;
    padding: 20px;
    border: 1px solid #e6ebf2;
    text-align: center;
    height: 100%;
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}
.pricing-card h3 { margin-top: 0; color: #4A90E2; }
.pricing-card .price { font-size: 28px; font-weight: bold; color: #2c3e50; }
.pricing-card .period { font-size: 14px; color: #7f8c8d; }
.pricing-card .launch-badge {
    background-color: #6C63FF;
    color: white;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    display: inline-block;
    margin-bottom: 12px;
}
.tier-badge-free, .tier-badge-premium, .tier-badge-pro {
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    display: inline-block;
}
.tier-badge-free { background-color: #6c757d; color: white; }
.tier-badge-premium { background-color: #4A90E2; color: white; }
.tier-badge-pro { background: linear-gradient(90deg, #6C63FF, #4A90E2); color: white; }
.credibility-note { font-size: 11px; color: #999; text-align: center; margin-top: 5px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# 3. Session State
# ---------------------------
if "premium" not in st.session_state:
    st.session_state.premium = False
if "pro" not in st.session_state:
    st.session_state.pro = False
if "cv_text" not in st.session_state:
    st.session_state.cv_text = ""
if "analysis_free" not in st.session_state:
    st.session_state.analysis_free = None
if "manual_job_query" not in st.session_state:
    st.session_state.manual_job_query = ""
if "displayed_jobs_free" not in st.session_state:
    st.session_state.displayed_jobs_free = []
if "displayed_jobs_premium" not in st.session_state:
    st.session_state.displayed_jobs_premium = []
if "displayed_jobs_pro" not in st.session_state:
    st.session_state.displayed_jobs_pro = []
if "generated_cv" not in st.session_state:
    st.session_state.generated_cv = ""
if "generated_cover_letter" not in st.session_state:
    st.session_state.generated_cover_letter = ""
if "cover_letter_analysis" not in st.session_state:
    st.session_state.cover_letter_analysis = None
if "cover_letter_text" not in st.session_state:
    st.session_state.cover_letter_text = ""

if "success_premium_monthly" in st.query_params:
    st.session_state.premium = True
    st.query_params.clear()
if "success_premium_lifetime" in st.query_params:
    st.session_state.premium = True
    st.query_params.clear()
if "success_pro_monthly" in st.query_params:
    st.session_state.pro = True
    st.query_params.clear()
if "success_pro_lifetime" in st.query_params:
    st.session_state.pro = True
    st.query_params.clear()

# ---------------------------
# 4. Helper Functions
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

def clean_json_response(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start_obj = text.find("{")
    end_obj = text.rfind("}")
    start_arr = text.find("[")
    end_arr = text.rfind("]")
    obj_candidate = text[start_obj:end_obj + 1] if start_obj != -1 and end_obj != -1 else ""
    arr_candidate = text[start_arr:end_arr + 1] if start_arr != -1 and end_arr != -1 else ""
    if obj_candidate and arr_candidate:
        return obj_candidate if len(obj_candidate) >= len(arr_candidate) else arr_candidate
    if obj_candidate:
        return obj_candidate
    if arr_candidate:
        return arr_candidate
    return text

def analyze_cv(cv_text, full=False):
    prompt = f"""
    Analyze this CV as a professional recruiter. Return ONLY valid JSON.

    Required fields:
    - strength_score: 0-100
    - ats_score: 0-100
    - interview_likelihood: "Low","Moderate","High"
    - recruiter_verdict: one sentence explaining the scores
    - experience_level: "Entry","Mid","Senior"
    - target_roles: list of 2-3
    - top_strengths: list of 2-3
    - top_weaknesses: list of 2-3

    If full == true, also include:
    - missing_keywords: list of 4-8
    - rewrite_suggestions: list of 3-5

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
            "interview_likelihood": "Moderate",
            "recruiter_verdict": "Unable to analyze – please try again.",
            "experience_level": "Mid",
            "target_roles": ["N/A"],
            "top_strengths": ["Error parsing response"],
            "top_weaknesses": ["Error parsing response"]
        }

@st.cache_data(show_spinner=False, ttl=3600)
def analyze_cv_cached(cv_text, full=False):
    return analyze_cv(cv_text, full)

def get_interview_percentage(likelihood):
    mapping = {"Low": "0-20%", "Moderate": "30-60%", "High": "65-85%"}
    return mapping.get(likelihood, "30-60%")

@st.cache_data(ttl=3600)
def analyze_cover_letter_full(letter_text, target_role):
    prompt = f"""
    Evaluate this cover letter for a {target_role} position.
    Return ONLY valid JSON:
    {{
        "alignment_score": 0-100,
        "personalization_score": 0-100,
        "impact_score": 0-100,
        "structure_score": 0-100,
        "overall_score": 0-100,
        "verdict": "one sentence",
        "missing_elements": ["element1", "element2", "element3"]
    }}
    Cover letter:
    {letter_text[:4000]}
    """
    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    try:
        return json.loads(raw)
    except:
        return {"overall_score": 50, "verdict": "Unable to evaluate", "missing_elements": []}

@st.cache_data(ttl=3600)
def review_cover_letter_basic(letter_text, target_role):
    prompt = f"""
    Review this cover letter for a {target_role} position.
    Return JSON: {{"overall_score": 0-100, "verdict": "one sentence", "top_missing": "single element"}}
    Cover letter: {letter_text[:4000]}
    """
    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    try:
        return json.loads(raw)
    except:
        return {"overall_score": 50, "verdict": "Unable to review", "top_missing": "Improve alignment"}

@st.cache_data(ttl=3600)
def generate_cover_letter(cv_text, target_role, company_name=""):
    company_text = f" for {company_name}" if company_name else ""
    prompt = f"""
    Write a professional cover letter for a {target_role} position{company_text}.
    Base it on the candidate's CV below. DO NOT invent experience.
    Return ONLY the cover letter as plain text (250-350 words).
    CV:
    {cv_text[:8000]}
    """
    response = model.generate_content(prompt)
    return response.text

@st.cache_data(ttl=3600)
def generate_job_query(cv_text):
    prompt = f"""
    Extract the single best job title from this CV.
    Return ONLY one title.
    No explanation.
    CV: {cv_text[:6000]}
    """
    return model.generate_content(prompt).text.strip()

def deduplicate_jobs(jobs):
    seen = set()
    unique = []
    for job in jobs:
        key = f"{job.get('title', '')}_{job.get('company', '')}".lower()
        if key not in seen:
            seen.add(key)
            unique.append(job)
    return unique

def get_jobs_from_adzuna(query, country_code, location_refine, limit=5):
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": JOB_API_KEY,
        "results_per_page": limit * 2,
        "what": query
    }
    if location_refine and location_refine.strip():
        params["where"] = location_refine.strip()
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            jobs = resp.json().get("results", [])
            formatted = []
            for j in jobs:
                company = j.get("company", {})
                company_name = company.get("display_name", "Unknown") if isinstance(company, dict) else str(company) if company else "Unknown"
                created = j.get("created")
                closing_date = j.get("closing_date")
                date_display = "📅 Date not specified"
                is_expired = False
                if closing_date:
                    date_display = f"📅 Closing: {closing_date}"
                    try:
                        if datetime.strptime(closing_date, "%Y-%m-%d") < datetime.now():
                            is_expired = True
                            date_display = "⚠️ EXPIRED"
                    except:
                        pass
                elif created:
                    date_display = f"📅 Posted: {created}"
                formatted.append({
                    "title": j.get("title", "Untitled"),
                    "company": company_name,
                    "location": location_refine or country_code.upper(),
                    "url": j.get("redirect_url", "#"),
                    "description": j.get("description", ""),
                    "date_display": date_display,
                    "is_expired": is_expired
                })
            return deduplicate_jobs(formatted)[:limit]
        else:
            return []
    except Exception as e:
        return []

def get_jobs_from_gemini_search(cv_text, job_title, location, limit=5):
    try:
        prompt = f"""
        Find {limit} recent job postings for a {job_title} position in {location}.
        Return ONLY valid JSON:
        {{
            "jobs": [
                {{
                    "job_title": "...",
                    "company_name": "...",
                    "location": "...",
                    "apply_url": "...",
                    "brief_description": "..."
                }}
            ]
        }}
        """
        response = model.generate_content(prompt)
        raw = clean_json_response(response.text)
        result = json.loads(raw)
        jobs = result.get("jobs", [])
        return [{
            "title": j.get("job_title", "Untitled"),
            "company": j.get("company_name", "Unknown"),
            "location": j.get("location", location),
            "url": j.get("apply_url", "#"),
            "description": j.get("brief_description", ""),
            "date_display": "📅 Recently posted",
            "is_expired": False
        } for j in jobs]
    except:
        return []

def get_job_matches(cv_text, analysis, manual_query, country_name, country_code, location_refine, limit=5):
    """CV-FIRST: Always prioritize detected roles from CV analysis"""
    # PRIORITY 1: CV-detected roles from Gemini
    target_roles = analysis.get("target_roles", [])
    
    if target_roles and target_roles[0] != "N/A":
        query = target_roles[0]
        source = "CV analysis"
    else:
        query = generate_job_query(cv_text).strip()
        source = "CV text extraction"
    
    # Manual override (optional, with warning)
    if manual_query and len(manual_query.strip()) > 2:
        st.warning(f"⚠️ Overriding CV-detected role '{query}' with '{manual_query}'. This may return less relevant jobs.")
        query = manual_query.strip()
        source = "manual override"
    
    if "," in query:
        query = query.split(",")[0].strip()
    
    if not query or len(query) < 3:
        st.error("Could not determine a valid job title from your CV.")
        return []
    
    st.success(f"🎯 Searching for: **{query}** (from {source}) in {country_name if country_name != 'Other' else country_code.upper()}")
    
    adzuna_supported = ["us", "gb", "ca", "au", "de", "fr", "in", "za"]
    
    if country_code in adzuna_supported:
        jobs = get_jobs_from_adzuna(query, country_code, location_refine, limit)
        if not jobs:
            st.warning(f"No {query} jobs found via Adzuna. Trying expanded search...")
            search_location = f"{location_refine}, {country_name}" if location_refine else country_name
            jobs = get_jobs_from_gemini_search(cv_text, query, search_location, limit)
        return jobs
    else:
        if not country_name or country_name == "Other":
            st.error("Please enter a specific country name for 'Other' selection.")
            return []
        search_location = f"{location_refine}, {country_name}" if location_refine else country_name
        jobs = get_jobs_from_gemini_search(cv_text, query, search_location, limit)
        if not jobs:
            st.warning(f"No {query} jobs found. Try a different country.")
        return jobs

@st.cache_data(ttl=3600)
def score_job_match(cv_text, job_title, job_description=""):
    prompt = f"""
    Score 0-100 match between CV and job '{job_title}'.
    Return JSON: {{"score": int, "reason": "string (max 10 words)"}}
    CV snippet:
    {cv_text[:2000]}
    Job description:
    {job_description[:500]}
    """
    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    try:
        result = json.loads(raw)
        return result.get("score", 50), result.get("reason", "Based on role alignment")
    except:
        return 50, "General alignment"

@st.cache_data(ttl=3600)
def get_missing_keywords_preview(cv_text):
    prompt = f"""
    From this CV, identify 3 high-impact keywords missing that would most improve interview chances.
    Return ONLY comma-separated keywords.
    CV:
    {cv_text[:5000]}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

def generate_improved_cv(cv_text, target_role):
    prompt = f"""
    Rewrite this CV for a {target_role} role.
    DO NOT invent experience. DO NOT change facts.
    Improve bullet points, add achievement language.
    Return the complete rewritten CV as plain text.
    Original: {cv_text[:10000]}
    """
    response = model.generate_content(prompt)
    return response.text

def create_docx_from_text(text, title="Document"):
    doc = Document()
    doc.add_heading(title, 0)
    doc.add_paragraph("Review before submission.")
    for line in text.split('\n'):
        if line.strip():
            doc.add_paragraph(line)
    bio = BytesIO()
    doc.save(bio)
    bio.seek(0)
    return bio

def safe_encode(text):
    return text.encode('latin-1', 'ignore').decode('latin-1')

def generate_pdf_report(analysis_full):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, safe_encode("Executive Career Intelligence Report"), ln=True)
    pdf.set_font("Arial", "I", 10)
    pdf.cell(0, 10, safe_encode(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"), ln=True)
    pdf.ln(5)
    pdf.set_font("Arial", size=12)
    for k, v in analysis_full.items():
        if isinstance(v, list):
            v = ", ".join(v)
        pdf.multi_cell(0, 8, safe_encode(f"{k.replace('_', ' ').title()}: {v}"))
    return pdf.output(dest='S').encode('latin-1')

def generate_ats_checklist(analysis_full):
    checklist = "✅ ATS OPTIMIZATION CHECKLIST\n\n"
    checklist += "Missing Keywords to Add:\n" + "\n".join(f"  • {kw}" for kw in analysis_full.get('missing_keywords', [])) + "\n\n"
    checklist += "Rewrite Suggestions:\n" + "\n".join(f"  • {sug}" for sug in analysis_full.get('rewrite_suggestions', [])) + "\n\n"
    return checklist

# ---------------------------
# 5. UI - Hero Section
# ---------------------------
st.markdown("""
<h1 style='text-align:center;'>📈 AI Career Intelligence</h1>
<p style='text-align:center; font-size:18px; color:#5f6b7a;'>
Upload your CV → Get recruiter feedback, ATS readiness, and matching jobs
</p>
<p class='credibility-note'>🤖 Scores are AI estimates based on recruiter best practices</p>
""", unsafe_allow_html=True)

colA, colB, colC = st.columns(3)
colA.markdown("✅ **Recruiter-style CV assessment**")
colB.markdown("🤖 **Powered by Gemini AI**")
colC.markdown("🌍 **Worldwide job search support**")
st.divider()

if st.session_state.pro:
    st.markdown('<span class="tier-badge-pro">🚀 PRO TIER ACTIVE</span>', unsafe_allow_html=True)
    st.success("✅ Full application engine unlocked")
elif st.session_state.premium:
    st.markdown('<span class="tier-badge-premium">⭐ PREMIUM TIER ACTIVE</span>', unsafe_allow_html=True)
    st.info("✅ Improvement tools unlocked")
else:
    st.markdown('<span class="tier-badge-free">🔓 FREE TIER</span>', unsafe_allow_html=True)
    st.info("📌 Free tier includes basic scores and 1 job match")

uploaded_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    cv_text = extract_text_from_file(uploaded_file)
    st.session_state.cv_text = cv_text

    with st.status("Analyzing your CV...", expanded=True) as status:
        st.write("📄 Reading CV document...")
        analysis = analyze_cv_cached(cv_text, full=False)
        st.session_state.analysis_free = analysis
        st.write("🔍 Analyzing keywords...")
        st.write("📊 Calculating ATS compatibility...")
        st.write("🎯 Identifying target roles...")
        status.update(label="Analysis complete!", state="complete")

    # Metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write("📊 Overall CV Strength")
        st.progress(analysis['strength_score']/100)
        st.caption(f"{analysis['strength_score']}/100")
    with col2:
        st.write("🤖 ATS Readiness")
        st.progress(analysis['ats_score']/100)
        st.caption(f"{analysis['ats_score']}/100")
    with col3:
        interview_pct = get_interview_percentage(analysis.get('interview_likelihood', 'Moderate'))
        st.write("🎯 Interview Likelihood")
        st.caption(f"**{analysis.get('interview_likelihood', 'Moderate')}**")
        st.caption(f"📊 *Estimated {interview_pct} chance*")

    # Target roles
    st.subheader("📌 Target Roles (Detected from Your CV)")
    target_roles = analysis.get('target_roles', [])
    if target_roles and target_roles[0] != "N/A":
        for role in target_roles:
            st.info(f"📌 {role}")
        primary_role = target_roles[0]
    else:
        st.warning("No specific roles detected")
        primary_role = st.text_input("Enter your target job title", key="manual_role_input")

    # Free insights
    st.subheader("🔍 Key Insights (Limited Preview)")
    strengths = analysis.get('top_strengths', [])[:2]
    weaknesses = analysis.get('top_weaknesses', [])[:2]
    st.markdown("**Strengths:**\n" + "\n".join(f"- {s}" for s in strengths))
    st.markdown("**Weaknesses:**\n" + "\n".join(f"- {w}" for w in weaknesses))

    if not st.session_state.premium and not st.session_state.pro:
        with st.spinner("Analyzing keyword gaps..."):
            preview_keywords = get_missing_keywords_preview(cv_text)
        preview_list = [k.strip() for k in preview_keywords.split(",") if k.strip()]
        if preview_list:
            blurred = f"{preview_list[0]}, [LOCKED], [LOCKED]"
        else:
            blurred = "Keywords detected after upgrade"
        st.caption(f"🔒 **Missing keywords preview:** {blurred}")
        st.caption("🔒 **Upgrade to Premium to see full insights**")

    if st.session_state.premium or st.session_state.pro:
        st.info(f"**Recruiter Assessment:** {analysis['recruiter_verdict']}")
        st.markdown(f"**Experience Level:** {analysis['experience_level']}")

    # ---------------------------
    # Cover Letter Assistant
    # ---------------------------
    st.subheader("📝 Cover Letter Assistant")
    cl_mode = st.radio(
        "What would you like to do?",
        ["📄 Review my existing cover letter", "✨ Generate a new cover letter for me"],
        horizontal=True,
        key="cl_mode"
    )

    if cl_mode == "📄 Review my existing cover letter":
        st.caption(f"Target role: **{primary_role}**")
        cl_tab1, cl_tab2 = st.tabs(["📁 Upload", "📝 Paste"])
        
        with cl_tab1:
            uploaded_cl = st.file_uploader("Upload cover letter", type=["pdf", "docx", "txt"], key="cl_review_upload")
            if uploaded_cl:
                try:
                    if uploaded_cl.name.endswith(".pdf"):
                        reader = PyPDF2.PdfReader(uploaded_cl)
                        st.session_state.cover_letter_text = "".join(page.extract_text() for page in reader.pages)
                    elif uploaded_cl.name.endswith(".docx"):
                        doc = docx.Document(uploaded_cl)
                        st.session_state.cover_letter_text = "\n".join(para.text for para in doc.paragraphs)
                    else:
                        st.session_state.cover_letter_text = uploaded_cl.read().decode("utf-8")
                    st.success(f"✅ Loaded")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        with cl_tab2:
            pasted_text = st.text_area("Paste your cover letter", height=150, key="cl_review_paste")
            if pasted_text:
                st.session_state.cover_letter_text = pasted_text
        
        if st.session_state.cover_letter_text:
            with st.expander("Preview loaded cover letter"):
                st.text(st.session_state.cover_letter_text[:500] + ("..." if len(st.session_state.cover_letter_text) > 500 else ""))
        
        if st.button("🔍 Analyze Cover Letter", use_container_width=True, type="primary"):
            if st.session_state.cover_letter_text and len(st.session_state.cover_letter_text.strip()) > 50:
                with st.spinner("Evaluating..."):
                    if st.session_state.premium or st.session_state.pro:
                        cl_analysis = analyze_cover_letter_full(st.session_state.cover_letter_text, primary_role)
                        st.metric("Application Readiness Score", f"{cl_analysis.get('overall_score', 50)}/100")
                        st.info(f"**Feedback:** {cl_analysis.get('verdict', 'Review needed')}")
                        col_cl1, col_cl2, col_cl3, col_cl4 = st.columns(4)
                        with col_cl1:
                            st.metric("Role Alignment", f"{cl_analysis.get('alignment_score', 50)}/100")
                        with col_cl2:
                            st.metric("Personalization", f"{cl_analysis.get('personalization_score', 50)}/100")
                        with col_cl3:
                            st.metric("Impact", f"{cl_analysis.get('impact_score', 50)}/100")
                        with col_cl4:
                            st.metric("Structure", f"{cl_analysis.get('structure_score', 50)}/100")
                        missing = cl_analysis.get('missing_elements', [])
                        if missing:
                            st.markdown("**Missing Elements:** " + ", ".join(missing[:3]))
                    else:
                        basic = review_cover_letter_basic(st.session_state.cover_letter_text, primary_role)
                        st.metric("Cover Letter Score", f"{basic.get('overall_score', 50)}/100")
                        st.info(f"**Feedback:** {basic.get('verdict', 'Review complete')}")
                        st.markdown(f"**Improvement Preview:** {basic.get('top_missing', 'Needs stronger alignment')}")
                        st.caption("🔒 **Upgrade to Premium for full analysis**")
            else:
                st.warning("Please provide a cover letter (at least 50 characters)")

    else:
        st.caption(f"Target role: **{primary_role}**")
        company_name = st.text_input("Company name (optional)", placeholder="e.g., Microsoft, Google", key="company_name")
        if not st.session_state.premium and not st.session_state.pro:
            st.info("🔒 **Cover letter generation is a Premium feature**")
        else:
            if st.button("✨ Generate Cover Letter", use_container_width=True, type="primary"):
                with st.spinner("Generating..."):
                    generated = generate_cover_letter(cv_text, primary_role, company_name)
                    st.session_state.generated_cover_letter = generated
                st.markdown("### 📄 Generated Cover Letter")
                st.text_area("Your cover letter", st.session_state.generated_cover_letter, height=250)
                docx_file = create_docx_from_text(st.session_state.generated_cover_letter, "Cover Letter")
                st.download_button("📥 Download", docx_file, file_name="cover_letter.docx")

    # ---------------------------
    # Job Search (CV-First)
    # ---------------------------
    st.subheader("🌍 Job Search")
    
    st.caption("📌 **Based on your CV, we recommend searching for:**")
    if target_roles and target_roles[0] != "N/A":
        st.info(f"🎯 {target_roles[0]}")
    else:
        st.warning("No specific roles detected")
    
    col_loc1, col_loc2 = st.columns(2)
    with col_loc1:
        country_display = st.selectbox("Country", list(COUNTRY_MAP.keys()), index=0, key="country_select")
        country_code = COUNTRY_MAP[country_display]
    with col_loc2:
        location_refine = st.text_input("City / Region", placeholder="e.g., London, Nairobi, Gaborone", key="location_input")

    if country_display == "Other":
        st.info("🌍 Using AI-powered search for your selected country")
        if location_refine and "botswana" in location_refine.lower():
            st.markdown("🔎 **Botswana job portals:** [Dumela](https://www.dumelajobs.com) | [JobWeb](https://bw.jobwebbotswana.com) | [LinkedIn](https://www.linkedin.com/jobs)")

    st.caption("✏️ Optional override - only if you want to search for a different role")
    manual_query = st.text_input("Override job title (optional)", placeholder=f"Leave empty to use {target_roles[0] if target_roles and target_roles[0] != 'N/A' else 'CV-detected role'}", key="manual_query_input")
    
    search_clicked = st.button("🔍 Search for Jobs", use_container_width=True, type="primary", key="search_jobs_button")
    
    st.subheader("💼 Matching Jobs")
    
    if st.session_state.pro:
        job_limit = 25
    elif st.session_state.premium:
        job_limit = 10
    else:
        job_limit = 1

    if search_clicked:
        with st.spinner("Searching for jobs matching your CV..."):
            jobs = get_job_matches(cv_text, analysis, manual_query, country_display, country_code, location_refine, limit=job_limit)
            if st.session_state.pro:
                st.session_state.displayed_jobs_pro = jobs
            elif st.session_state.premium:
                st.session_state.displayed_jobs_premium = jobs
            else:
                st.session_state.displayed_jobs_free = jobs
        if jobs:
            st.success(f"✅ Found {len(jobs)} jobs")
        else:
            st.warning("No jobs found. Try a different country.")

    display_jobs = []
    if st.session_state.pro:
        display_jobs = st.session_state.displayed_jobs_pro
    elif st.session_state.premium:
        display_jobs = st.session_state.displayed_jobs_premium
    else:
        display_jobs = st.session_state.displayed_jobs_free

    if display_jobs:
        for idx, job in enumerate(display_jobs):
            with st.expander(f"**{job['title']}** at {job['company']}"):
                st.caption(job.get('date_display', '📅 Date not specified'))
                st.markdown(f"📍 **Location:** {job.get('location', 'Not specified')}")
                if st.session_state.pro or st.session_state.premium:
                    if st.button(f"🎯 Show Match Score", key=f"score_{idx}"):
                        score, reason = score_job_match(cv_text, job['title'], job.get('description', ''))
                        st.write(f"**Match Score:** {score}%")
                        st.caption(f"📝 {reason}")
                else:
                    st.caption("🔒 **Match score available after upgrade**")
                st.markdown(f"[Apply Now]({job['url']})")
        if not st.session_state.premium and not st.session_state.pro:
            st.info("🔒 **Upgrade to Premium for more jobs with match scores!**")

    # ---------------------------
    # Premium/Pro Features
    # ---------------------------
    if st.session_state.premium and not st.session_state.pro:
        st.markdown("---")
        st.subheader("⭐ Premium Features")
        with st.spinner("Generating full analysis..."):
            full_analysis = analyze_cv_cached(cv_text, full=True)
        st.subheader("🔑 Missing Keywords")
        st.markdown(", ".join(full_analysis.get('missing_keywords', [])))
        st.subheader("✍️ Rewrite Suggestions")
        for sug in full_analysis.get('rewrite_suggestions', []):
            st.markdown(f"- {sug}")
        col_pdf, col_check = st.columns(2)
        with col_pdf:
            pdf_data = generate_pdf_report(full_analysis)
            st.download_button("📥 PDF Report", pdf_data, file_name="career_report.pdf")
        with col_check:
            checklist_text = generate_ats_checklist(full_analysis)
            st.download_button("📋 ATS Checklist", checklist_text, file_name="ats_checklist.txt")
        st.info("🚀 **Upgrade to Pro for CV and cover letter generators**")

    elif st.session_state.pro:
        st.markdown("---")
        st.subheader("🚀 Pro Features")
        with st.spinner("Generating full analysis..."):
            full_analysis = analyze_cv_cached(cv_text, full=True)
        st.subheader("🔑 Missing Keywords")
        st.markdown(", ".join(full_analysis.get('missing_keywords', [])))
        st.subheader("✍️ Rewrite Suggestions")
        for sug in full_analysis.get('rewrite_suggestions', []):
            st.markdown(f"- {sug}")
        col_pdf, col_check = st.columns(2)
        with col_pdf:
            pdf_data = generate_pdf_report(full_analysis)
            st.download_button("📥 Executive PDF Report", pdf_data, file_name="executive_report.pdf")
        with col_check:
            checklist_text = generate_ats_checklist(full_analysis)
            st.download_button("📋 ATS Checklist", checklist_text, file_name="ats_checklist.txt")
        st.markdown("---")
        st.subheader("🧾 CV Draft Generator")
        if st.button("📄 Generate Improved CV Draft", use_container_width=True):
            with st.spinner("Generating..."):
                st.session_state.generated_cv = generate_improved_cv(cv_text, primary_role)
        if st.session_state.generated_cv:
            st.text_area("Improved CV Draft", st.session_state.generated_cv, height=250)
            docx_file = create_docx_from_text(st.session_state.generated_cv, "Improved CV")
            st.download_button("📥 Download CV", docx_file, file_name="improved_cv.docx")

    # ---------------------------
    # Upgrade Section
    # ---------------------------
    if not st.session_state.premium and not st.session_state.pro:
        st.markdown("---")
        st.markdown("""
        <div class="upgrade-box">
        <h3>🚀 Upgrade Your Career Toolkit</h3>
        <p>Limited launch pricing • Lifetime access available</p>
        </div>
        """, unsafe_allow_html=True)
        col_card1, col_card2 = st.columns(2)
        with col_card1:
            st.markdown("""
            <div class="pricing-card">
            <span class="launch-badge">⭐ PREMIUM</span>
            <h3>Premium</h3>
            <div><span class="price">$9</span><span class="period">/month</span></div>
            <div><span class="price">$29</span><span class="period"> lifetime</span></div>
            </div>
            """, unsafe_allow_html=True)
        with col_card2:
            st.markdown("""
            <div class="pricing-card">
            <span class="launch-badge">🚀 PRO</span>
            <h3>Pro</h3>
            <div><span class="price">$19</span><span class="period">/month</span></div>
            <div><span class="price">$49</span><span class="period"> lifetime</span></div>
            </div>
            """, unsafe_allow_html=True)
        
        col_up1, col_up2, col_up3, col_up4 = st.columns(4)
        with col_up1:
            if st.button("Premium Monthly $9", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PREMIUM_MONTHLY, "quantity": 1}],
                        mode="subscription",
                        success_url=APP_URL + "?success_premium_monthly=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")
        with col_up2:
            if st.button("Premium Lifetime $29", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PREMIUM_LIFETIME, "quantity": 1}],
                        mode="payment",
                        success_url=APP_URL + "?success_premium_lifetime=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")
        with col_up3:
            if st.button("Pro Monthly $19", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PRO_MONTHLY, "quantity": 1}],
                        mode="subscription",
                        success_url=APP_URL + "?success_pro_monthly=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")
        with col_up4:
            if st.button("Pro Lifetime $49", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PRO_LIFETIME, "quantity": 1}],
                        mode="payment",
                        success_url=APP_URL + "?success_pro_lifetime=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error: {e}")
        st.markdown("---")
        st.caption("📝 **Testing unlock codes:**")
        col_code1, col_code2 = st.columns(2)
        with col_code1:
            if st.text_input("Premium code", type="password", key="premium_code") == PREMIUM_UNLOCK_CODE:
                st.session_state.premium = True
                st.rerun()
        with col_code2:
            if st.text_input("Pro code", type="password", key="pro_code") == PRO_UNLOCK_CODE:
                st.session_state.pro = True
                st.rerun()

else:
    st.info("👆 Please upload your CV to begin.")

# ---------------------------
# Footer
# ---------------------------
st.markdown("""
<hr>
<center><b>AI Career Intelligence</b> • Powered by Gemini AI • Worldwide job search support</center>
""", unsafe_allow_html=True)