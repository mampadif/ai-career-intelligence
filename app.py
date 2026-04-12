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

# ---------------------------
# 1.5 CUSTOM CSS
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
    box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    text-align: center;
    height: 100%;
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
.streamlit-expanderHeader { font-weight: 600; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }
h1 { font-weight: 700; }
.stProgress > div > div { background: linear-gradient(90deg, #4A90E2, #6C63FF); }
.credibility-note { font-size: 11px; color: #999; text-align: center; margin-top: 5px; }
.tier-badge-free { background-color: #6c757d; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; display: inline-block; }
.tier-badge-premium { background-color: #4A90E2; color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; display: inline-block; }
.tier-badge-pro { background: linear-gradient(90deg, #6C63FF, #4A90E2); color: white; padding: 4px 12px; border-radius: 20px; font-size: 12px; display: inline-block; }
</style>
""", unsafe_allow_html=True)

# ---------------------------
# 2. Session State
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
if "cover_letter_analysis" not in st.session_state:
    st.session_state.cover_letter_analysis = None
if "cover_letter_text" not in st.session_state:
    st.session_state.cover_letter_text = ""
if "improved_cover_letter" not in st.session_state:
    st.session_state.improved_cover_letter = ""
if "analyze_cover_letter_trigger" not in st.session_state:
    st.session_state.analyze_cover_letter_trigger = False

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

    IMPORTANT: These scores are AI estimates based on recruiter best practices, not mathematical calculations.
    
    Required fields:
    - strength_score: 0-100
    - ats_score: 0-100
    - interview_likelihood: "Low", "Moderate", or "High"
    - recruiter_verdict: one sentence
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
def analyze_cover_letter(letter_text, job_title=""):
    prompt = f"""
    Evaluate this cover letter as a professional recruiter.

    Return ONLY valid JSON:
    {{
        "alignment_score": 0-100,
        "personalization_score": 0-100,
        "impact_score": 0-100,
        "structure_score": 0-100,
        "overall_score": 0-100,
        "verdict": "one sentence",
        "missing_elements": ["list", "of", "elements"]
    }}

    Job role: {job_title}
    Cover letter: {letter_text[:4000]}
    """
    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    try:
        return json.loads(raw)
    except:
        return {"overall_score": 50, "verdict": "Unable to evaluate", "missing_elements": []}

@st.cache_data(ttl=3600)
def improve_cover_letter(letter_text, job_title):
    prompt = f"""
    Improve this cover letter for a {job_title} role.
    DO NOT invent experience. Keep facts unchanged.
    Return the complete improved cover letter as plain text.
    Original: {letter_text[:4000]}
    """
    response = model.generate_content(prompt)
    return response.text

@st.cache_data(ttl=3600)
def generate_job_query(cv_text):
    prompt = f"Extract 3 likely job titles from this CV. Return ONLY comma-separated titles. CV: {cv_text[:6000]}"
    return model.generate_content(prompt).text.strip()

def deduplicate_jobs(jobs):
    seen = set()
    unique_jobs = []
    for job in jobs:
        key = f"{job.get('title', '')}_{job.get('company', '')}".lower()
        if key not in seen:
            seen.add(key)
            unique_jobs.append(job)
    return unique_jobs

def get_jobs_from_adzuna(query, country_code, location_refine, limit=5):
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {"app_id": ADZUNA_APP_ID, "app_key": JOB_API_KEY, "results_per_page": limit * 2, "what": query}
    if location_refine and location_refine.strip():
        params["where"] = location_refine.strip()
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            jobs = resp.json().get("results", [])
            formatted_jobs = []
            for j in jobs:
                company = j.get("company", {})
                company_name = company.get("display_name", "Unknown Company") if isinstance(company, dict) else str(company) if company else "Unknown Company"
                created = j.get("created")
                closing_date = j.get("closing_date")
                date_display = "📅 Date not specified"
                is_expired = False
                if closing_date:
                    date_display = f"📅 Closing: {closing_date}"
                    try:
                        close_date = datetime.strptime(closing_date, "%Y-%m-%d")
                        if close_date < datetime.now():
                            is_expired = True
                            date_display = f"⚠️ EXPIRED (Closed: {closing_date})"
                    except:
                        pass
                elif created:
                    date_display = f"📅 Posted: {created}"
                
                formatted_jobs.append({
                    "title": j.get("title", "Untitled Position"),
                    "company": company_name,
                    "location": location_refine or country_code.upper(),
                    "url": j.get("redirect_url", "#"),
                    "description": j.get("description", ""),
                    "date_display": date_display,
                    "is_expired": is_expired
                })
            return deduplicate_jobs(formatted_jobs)[:limit]
        return []
    except Exception as e:
        return []

def get_jobs_from_gemini_search(cv_text, job_title, location, limit=5):
    try:
        prompt = f"Find {limit} recent job postings for {job_title} in {location}. Return JSON: {{'jobs':[{{'job_title':'...','company_name':'...','location':'...','apply_url':'...','date_posted':'...'}}]}}"
        response = model.generate_content(prompt)
        raw = clean_json_response(response.text)
        result = json.loads(raw)
        jobs = result.get("jobs", [])
        return [{
            "title": j.get("job_title", "Untitled"),
            "company": j.get("company_name", "Unknown"),
            "location": j.get("location", location),
            "url": j.get("apply_url", "#"),
            "description": "",
            "date_display": f"📅 {j.get('date_posted', 'Recently posted')}",
            "is_expired": False
        } for j in jobs]
    except:
        return []

def get_job_matches(cv_text, analysis, manual_query, country_code, country_name, location_refine, limit=5):
    query = manual_query
    if not query or len(query) < 3:
        target_roles = analysis.get('target_roles', [])
        query = target_roles[0] if target_roles and target_roles[0] != "N/A" else generate_job_query(cv_text)
    if not query or len(query) < 3:
        return []
    
    adzuna_countries = ["us", "gb", "ca", "au", "de", "fr", "in", "za"]
    if country_code in adzuna_countries:
        return get_jobs_from_adzuna(query, country_code, location_refine, limit)
    else:
        search_location = f"{location_refine}, {country_name}" if location_refine else country_name
        return get_jobs_from_gemini_search(cv_text, query, search_location, limit)

@st.cache_data(ttl=3600)
def score_job_match(cv_text, job_title, job_description=""):
    prompt = f"Score 0-100 match between CV and '{job_title}'. Return JSON: {{'score': int, 'reason': 'string'}}"
    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    try:
        result = json.loads(raw)
        return result.get("score", 50), result.get("reason", "Based on role alignment")
    except:
        return 50, "Based on general alignment"

@st.cache_data(ttl=3600)
def get_missing_keywords_preview(cv_text):
    prompt = f"From this CV, identify 3 high-impact missing keywords. Return ONLY comma-separated. CV: {cv_text[:5000]}"
    response = model.generate_content(prompt)
    return response.text.strip()

def generate_improved_cv(cv_text, target_role):
    prompt = f"""
    Rewrite this CV for a {target_role} role.
    IMPORTANT: DO NOT invent experience. DO NOT change facts.
    Improve bullet points, add achievement language, improve ATS keywords.
    Return the complete rewritten CV as plain text.
    Original: {cv_text[:10000]}
    """
    response = model.generate_content(prompt)
    return response.text

def create_docx_from_text(text):
    doc = Document()
    doc.add_heading("Recruiter-Optimized CV Draft", 0)
    doc.add_paragraph("This draft improves clarity and keyword alignment but should be reviewed before submission.")
    doc.add_paragraph("")
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
# 4. UI - Hero Section
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

# Display current tier
if st.session_state.pro:
    st.markdown('<span class="tier-badge-pro">🚀 PRO TIER ACTIVE</span>', unsafe_allow_html=True)
    st.success("✅ Full application engine unlocked – CV generator, cover letter generator, and more!")
elif st.session_state.premium:
    st.markdown('<span class="tier-badge-premium">⭐ PREMIUM TIER ACTIVE</span>', unsafe_allow_html=True)
    st.info("✅ Improvement tools unlocked – missing keywords, rewrite suggestions, and full job matches!")
else:
    st.markdown('<span class="tier-badge-free">🔓 FREE TIER</span>', unsafe_allow_html=True)
    st.info("📌 Free tier includes basic scores and 1 job match. Upgrade to unlock full features.")

uploaded_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    cv_text = extract_text_from_file(uploaded_file)
    st.session_state.cv_text = cv_text

    with st.status("Analyzing your CV...", expanded=True) as status:
        st.write("📄 Reading CV document...")
        analysis = analyze_cv_cached(cv_text, full=False)
        st.session_state.analysis_free = analysis
        status.update(label="Analysis complete!", state="complete")

    # ---------------------------
    # METRICS - Always visible
    # ---------------------------
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

    # ---------------------------
    # TARGET ROLES
    # ---------------------------
    st.subheader("📌 Target Roles")
    target_roles = analysis.get('target_roles', [])
    if target_roles and target_roles[0] != "N/A":
        for role in target_roles:
            st.info(f"📌 {role}")
    else:
        st.warning("No specific roles detected")

    # ---------------------------
    # FREE TIER: Limited insights
    # ---------------------------
    st.subheader("🔍 Key Insights (Limited Preview)")
    strengths = analysis.get('top_strengths', [])[:2]
    weaknesses = analysis.get('top_weaknesses', [])[:2]
    st.markdown("**Strengths:**\n" + "\n".join(f"- {s}" for s in strengths))
    st.markdown("**Weaknesses:**\n" + "\n".join(f"- {w}" for w in weaknesses))
    
    if not st.session_state.premium and not st.session_state.pro:
        st.caption("🔒 **Upgrade to Premium to see full strengths, weaknesses, and recruiter verdict**")
    
    # ---------------------------
    # PREMIUM/PRO: Recruiter Verdict
    # ---------------------------
    if st.session_state.premium or st.session_state.pro:
        st.info(f"**Recruiter Assessment:** {analysis['recruiter_verdict']}")
        st.markdown(f"**Experience Level:** {analysis['experience_level']}")

    # ---------------------------
    # Cover Letter Section - FIXED
    # ---------------------------
    st.subheader("🧾 Application Readiness Score")
    
    cl_tab1, cl_tab2 = st.tabs(["📁 Upload Cover Letter", "📝 Paste Cover Letter"])
    cover_letter_text = ""

    with cl_tab1:
        uploaded_cl = st.file_uploader("Upload cover letter (PDF, DOCX, TXT)", type=["pdf", "docx", "txt"], key="cl_upload")
        if uploaded_cl:
            try:
                if uploaded_cl.name.endswith(".pdf"):
                    reader = PyPDF2.PdfReader(uploaded_cl)
                    cover_letter_text = "".join(page.extract_text() for page in reader.pages)
                elif uploaded_cl.name.endswith(".docx"):
                    doc = docx.Document(uploaded_cl)
                    cover_letter_text = "\n".join(para.text for para in doc.paragraphs)
                else:
                    cover_letter_text = uploaded_cl.read().decode("utf-8")
                st.success(f"✅ Loaded from {uploaded_cl.name}")
                st.session_state.analyze_cover_letter_trigger = True
            except Exception as e:
                st.error(f"Error: {e}")

    with cl_tab2:
        pasted_text = st.text_area("Paste your cover letter", height=150, key="cl_paste")
        if pasted_text:
            cover_letter_text = pasted_text
            st.session_state.analyze_cover_letter_trigger = True

    # Analyze button for manual trigger
    analyze_cl_clicked = st.button("🔍 Analyze Cover Letter", key="analyze_cl_button")

    # Trigger analysis
    if cover_letter_text and (st.session_state.analyze_cover_letter_trigger or analyze_cl_clicked):
        st.session_state.cover_letter_text = cover_letter_text
        target_role = analysis.get('target_roles', ['your target role'])[0]
        
        with st.spinner("Evaluating your cover letter..."):
            cl_analysis = analyze_cover_letter(cover_letter_text, target_role)
            st.session_state.cover_letter_analysis = cl_analysis
        
        st.metric("Application Readiness", f"{cl_analysis.get('overall_score', 50)}/100")
        
        if st.session_state.premium or st.session_state.pro:
            col_cl1, col_cl2, col_cl3, col_cl4 = st.columns(4)
            with col_cl1:
                st.metric("Role Alignment", f"{cl_analysis.get('alignment_score', 50)}/100")
            with col_cl2:
                st.metric("Personalization", f"{cl_analysis.get('personalization_score', 50)}/100")
            with col_cl3:
                st.metric("Impact", f"{cl_analysis.get('impact_score', 50)}/100")
            with col_cl4:
                st.metric("Structure", f"{cl_analysis.get('structure_score', 50)}/100")
            st.info(f"**Verdict:** {cl_analysis.get('verdict', 'Review needed')}")
            
            missing = cl_analysis.get('missing_elements', [])
            if missing:
                st.markdown("**Missing Elements:** " + ", ".join(missing[:3]))
        else:
            st.caption("🔒 **Upgrade to Premium to see detailed breakdown + improvement suggestions**")
        
        st.session_state.analyze_cover_letter_trigger = False

    # ---------------------------
    # Job Search - FIXED
    # ---------------------------
    st.subheader("🌍 Job Search Settings")
    
    st.caption("🎯 **Roles detected:** " + (", ".join(target_roles[:2]) if target_roles[0] != "N/A" else "None"))
    
    col_loc1, col_loc2 = st.columns(2)
    with col_loc1:
        country_option = st.selectbox("Country", ["us", "gb", "ca", "au", "de", "fr", "in", "za", "other"], index=0, key="country_select")
    with col_loc2:
        location_refine = st.text_input("City / Region", placeholder="e.g., London, Nairobi", key="location_input")
    
    if country_option == "other":
        country_name = st.text_input("Country name", placeholder="Botswana, Ghana...", key="country_name_input")
        if country_name and "botswana" in country_name.lower():
            st.info("🔎 Botswana job portals: [Dumela Jobs](https://www.dumelajobs.com) | [JobWeb](https://bw.jobwebbotswana.com) | [LinkedIn](https://www.linkedin.com/jobs)")
    else:
        country_name = country_option.upper()
    
    manual_query = st.text_input("Override job title (optional)", placeholder="Leave empty to use detected roles", key="manual_query_input")
    
    search_clicked = st.button("🔍 Search for Jobs", use_container_width=True, type="primary", key="search_jobs_button")
    
    st.subheader("💼 Matching Jobs")
    
    # Tier-based job limits
    if st.session_state.pro:
        job_limit = 25
        tier_label = "Pro"
    elif st.session_state.premium:
        job_limit = 10
        tier_label = "Premium"
    else:
        job_limit = 1
        tier_label = "Free"
    
    if search_clicked:
        if country_option == "other" and not country_name:
            st.error("Please enter your country name")
        else:
            with st.spinner(f"Searching for jobs ({tier_label} tier)..."):
                jobs = get_job_matches(cv_text, analysis, manual_query, country_option, country_name, location_refine, limit=job_limit)
                if st.session_state.pro:
                    st.session_state.displayed_jobs_pro = jobs
                elif st.session_state.premium:
                    st.session_state.displayed_jobs_premium = jobs
                else:
                    st.session_state.displayed_jobs_free = jobs
    
    # Display jobs based on tier
    display_jobs = []
    if st.session_state.pro:
        display_jobs = st.session_state.displayed_jobs_pro
    elif st.session_state.premium:
        display_jobs = st.session_state.displayed_jobs_premium
    else:
        display_jobs = st.session_state.displayed_jobs_free
    
    if display_jobs:
        st.success(f"✅ Found {len(display_jobs)} jobs matching your profile!")
        for idx, job in enumerate(display_jobs):
            with st.expander(f"**{job['title']}** at {job['company']}"):
                st.caption(job.get('date_display', '📅 Date not specified'))
                st.markdown(f"📍 **Location:** {job.get('location', 'Not specified')}")
                
                if st.session_state.pro or st.session_state.premium:
                    col_score1, col_score2 = st.columns([1, 1])
                    with col_score1:
                        if st.button(f"🎯 Show Match Score", key=f"score_{idx}_{job['title']}"):
                            score, reason = score_job_match(cv_text, job['title'], job.get('description', ''))
                            st.write(f"**Match Score:** {score}%")
                            st.caption(f"📝 *{reason}*")
                else:
                    st.caption("🔒 **Match score available after upgrade**")
                
                if job.get('is_expired'):
                    st.warning("⚠️ This job may have expired. Check before applying.")
                
                st.markdown(f"[Apply Now]({job['url']})")
        
        if not st.session_state.premium and not st.session_state.pro:
            st.info("🔒 **Upgrade to Premium ($9/month or $29 lifetime) for 10+ jobs with match scores!**")
        elif st.session_state.premium and not st.session_state.pro:
            st.info("🚀 **Upgrade to Pro ($19/month or $49 lifetime) for 25+ jobs + CV/cover letter generators!**")

    # ---------------------------
    # UPGRADE SECTION - OPTIMIZED PRICING
    # ---------------------------
    if not st.session_state.premium and not st.session_state.pro:
        st.markdown("---")
        st.markdown("""
        <div class="upgrade-box">
        <h3>🚀 Upgrade Your Career Toolkit</h3>
        <p style="font-size:14px; margin-top:-10px;">Limited launch pricing • Best for active job seekers</p>
        </div>
        """, unsafe_allow_html=True)
        
        col_card1, col_card2 = st.columns(2)
        
        with col_card1:
            st.markdown("""
            <div class="pricing-card">
            <span class="launch-badge">⭐ MOST POPULAR</span>
            <h3>Premium</h3>
            <div><span class="price">$9</span><span class="period">/month</span></div>
            <div style="margin: 10px 0;"><span class="price">$29</span><span class="period"> lifetime</span></div>
            <p style="font-size:13px; color:#666;">🎯 Recruiter verdict<br>
            🔑 Missing keywords & rewrite suggestions<br>
            💼 10 job matches + match scores<br>
            📝 Full cover letter diagnostics<br>
            📋 ATS checklist & PDF report</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col_card2:
            st.markdown("""
            <div class="pricing-card">
            <span class="launch-badge">🚀 BEST VALUE</span>
            <h3>Pro</h3>
            <div><span class="price">$19</span><span class="period">/month</span></div>
            <div style="margin: 10px 0;"><span class="price">$49</span><span class="period"> lifetime</span></div>
            <p style="font-size:13px; color:#666;">✅ All Premium features<br>
            📄 Recruiter-optimized CV draft generator<br>
            ✉️ Job-specific cover letter generator<br>
            🎯 25+ job matches<br>
            📊 Executive intelligence report</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        col_up1, col_up2, col_up3, col_up4 = st.columns(4)
        with col_up1:
            if st.button("⭐ Premium Monthly $9", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PREMIUM_MONTHLY, "quantity": 1}],
                        mode="subscription",
                        success_url=APP_URL + "?success_premium_monthly=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely with Stripe</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Payment error: {e}")
        with col_up2:
            if st.button("⭐ Premium Lifetime $29", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PREMIUM_LIFETIME, "quantity": 1}],
                        mode="payment",
                        success_url=APP_URL + "?success_premium_lifetime=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely with Stripe</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Payment error: {e}")
        with col_up3:
            if st.button("🚀 Pro Monthly $19", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PRO_MONTHLY, "quantity": 1}],
                        mode="subscription",
                        success_url=APP_URL + "?success_pro_monthly=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely with Stripe</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Payment error: {e}")
        with col_up4:
            if st.button("🚀 Pro Lifetime $49", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PRO_LIFETIME, "quantity": 1}],
                        mode="payment",
                        success_url=APP_URL + "?success_pro_lifetime=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely with Stripe</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Payment error: {e}")
        
        st.markdown("---")
        st.caption("📝 **Unlock codes (for testing):**")
        col_code1, col_code2 = st.columns(2)
        with col_code1:
            code = st.text_input("Premium code", type="password", key="premium_code")
            if code == PREMIUM_UNLOCK_CODE:
                st.session_state.premium = True
                st.rerun()
        with col_code2:
            code = st.text_input("Pro code", type="password", key="pro_code")
            if code == PRO_UNLOCK_CODE:
                st.session_state.pro = True
                st.rerun()

    # ---------------------------
    # PREMIUM FEATURES
    # ---------------------------
    elif st.session_state.premium and not st.session_state.pro:
        st.markdown("---")
        st.subheader("⭐ Premium Features Unlocked")
        
        with st.spinner("Generating full analysis..."):
            full_analysis = analyze_cv_cached(cv_text, full=True)
        
        st.subheader("🔑 Missing ATS Keywords")
        st.markdown(", ".join(full_analysis.get('missing_keywords', [])))
        
        st.subheader("✍️ Rewrite Suggestions")
        for sug in full_analysis.get('rewrite_suggestions', []):
            st.markdown(f"- {sug}")
        
        col_pdf, col_check = st.columns(2)
        with col_pdf:
            pdf_data = generate_pdf_report(full_analysis)
            st.download_button("📥 Download PDF Report", pdf_data, file_name="career_report.pdf")
        with col_check:
            checklist_text = generate_ats_checklist(full_analysis)
            st.download_button("📋 Download ATS Checklist", checklist_text, file_name="ats_checklist.txt")
        
        st.info("🚀 **Upgrade to Pro ($19/month or $49 lifetime) for CV and cover letter generators!**")
        
        col_up_pro1, col_up_pro2 = st.columns([3, 1])
        with col_up_pro2:
            if st.button("Upgrade to Pro", use_container_width=True):
                try:
                    session = stripe.checkout.Session.create(
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PRICE_ID_PRO_MONTHLY, "quantity": 1}],
                        mode="subscription",
                        success_url=APP_URL + "?success_pro_monthly=true",
                        cancel_url=APP_URL,
                    )
                    st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely with Stripe</a>", unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Payment error: {e}")

    # ---------------------------
    # PRO FEATURES
    # ---------------------------
    elif st.session_state.pro:
        st.markdown("---")
        st.subheader("🚀 Pro Features Unlocked")
        
        with st.spinner("Generating full intelligence report..."):
            full_analysis = analyze_cv_cached(cv_text, full=True)
        
        st.subheader("🔑 Missing ATS Keywords")
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
        
        # CV Draft Generator
        st.subheader("🧾 Recruiter-Optimized CV Draft")
        target_role = target_roles[0] if target_roles and target_roles[0] != "N/A" else "your target role"
        st.caption(f"🎯 **Targeting:** {target_role}")
        
        if st.button("📄 Generate Improved CV Draft", use_container_width=True):
            with st.spinner("Generating recruiter-optimized CV..."):
                st.session_state.generated_cv = generate_improved_cv(cv_text, target_role)
        
        if st.session_state.generated_cv:
            st.markdown("### 📄 Recruiter-Optimized Draft CV")
            st.caption("⚠️ **Note:** Improves clarity and keyword alignment. Review before submission.")
            st.text_area("Improved CV Draft", st.session_state.generated_cv, height=300)
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                st.download_button("📥 Download TXT", st.session_state.generated_cv, file_name="improved_cv.txt")
            with col_dl2:
                docx_file = create_docx_from_text(st.session_state.generated_cv)
                st.download_button("📥 Download DOCX", docx_file, file_name="improved_cv.docx")
        
        st.markdown("---")
        
        # Cover Letter Generator
        if st.session_state.cover_letter_text:
            st.subheader("📝 Cover Letter Generator")
            st.caption(f"🎯 **Targeting:** {target_role}")
            
            if st.button("✉️ Generate Improved Cover Letter", use_container_width=True):
                with st.spinner("Generating recruiter-optimized cover letter..."):
                    st.session_state.improved_cover_letter = improve_cover_letter(st.session_state.cover_letter_text, target_role)
            
            if st.session_state.improved_cover_letter:
                st.markdown("### ✨ Improved Cover Letter Draft")
                st.caption("⚠️ **Note:** Improves persuasion and recruiter tone. Review before submission.")
                st.text_area("Improved Cover Letter", st.session_state.improved_cover_letter, height=250)
                st.download_button("📥 Download Cover Letter", st.session_state.improved_cover_letter, file_name="improved_cover_letter.txt")
        else:
            st.info("📝 Upload or paste a cover letter above to use the cover letter generator.")

else:
    st.info("👆 Please upload your CV to begin.")

# ---------------------------
# Footer
# ---------------------------
st.markdown("""
<hr>
<center>
<b>AI Career Intelligence</b> • Powered by Gemini AI • Worldwide job search support
</center>
""", unsafe_allow_html=True)