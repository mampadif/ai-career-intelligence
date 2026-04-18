import streamlit as st
import google.generativeai as genai
import PyPDF2
import docx
import requests
import stripe
import json
import re
from datetime import datetime, timedelta
from fpdf import FPDF
from io import BytesIO
from docx import Document
from PIL import Image
import numpy as np

# ---------------------------
# 1. Configuration & Secrets
# ---------------------------
st.set_page_config(page_title="AI Career Intelligence", page_icon="📈", layout="wide")

GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
STRIPE_SECRET_KEY = st.secrets["STRIPE_SECRET_KEY"]
STRIPE_PRICE_ID_PREMIUM_MONTHLY = st.secrets["STRIPE_PRICE_ID_PREMIUM_MONTHLY"]
STRIPE_PRICE_ID_PREMIUM_LIFETIME = st.secrets["STRIPE_PRICE_ID_PREMIUM_LIFETIME"]
STRIPE_PRICE_ID_PRO_MONTHLY = st.secrets["STRIPE_PRICE_ID_PRO_MONTHLY"]
STRIPE_PRICE_ID_PRO_LIFETIME = st.secrets["STRIPE_PRICE_ID_PRO_LIFETIME"]
JOB_API_KEY = st.secrets["JOB_API_KEY"]
ADZUNA_APP_ID = st.secrets["ADZUNA_APP_ID"]
APP_URL = st.secrets["APP_URL"]
PREMIUM_UNLOCK_CODE = st.secrets["PREMIUM_UNLOCK_CODE"].strip()
PRO_UNLOCK_CODE = st.secrets["PRO_UNLOCK_CODE"].strip()

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
# 2. Premium CSS
# ---------------------------
st.markdown("""
<style>
body { background-color: #f8fafc; font-family: 'Inter', sans-serif; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }
.hero {
    text-align: center;
    padding: 2rem 1rem;
    background: linear-gradient(135deg, #f0f9ff, #e6f0ff);
    border-radius: 30px;
    margin-bottom: 2rem;
}
.hero h1 { font-size: 2.5rem; font-weight: 700; color: #0f172a; margin-bottom: 0.5rem; }
.hero p { font-size: 1.2rem; color: #475569; margin-bottom: 1rem; }
.hero-badge { display: inline-block; background-color: #6C63FF; color: white; padding: 0.3rem 1rem; border-radius: 40px; font-size: 0.8rem; margin-bottom: 1rem; }
.metric-card {
    background: white;
    border-radius: 20px;
    padding: 1.2rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.05);
    text-align: center;
    border: 1px solid #e2e8f0;
}
.metric-value { font-size: 2rem; font-weight: 700; color: #1e293b; }
.metric-label { font-size: 0.85rem; color: #64748b; margin-top: 0.25rem; }
.action-card {
    background: white;
    border-radius: 24px;
    padding: 1.5rem;
    box-shadow: 0 8px 20px rgba(0,0,0,0.05);
    height: 100%;
    border: 1px solid #e2e8f0;
}
.action-title { font-size: 1.3rem; font-weight: 700; margin-bottom: 1rem; color: #0f172a; }
.job-card {
    background: white;
    border-radius: 20px;
    padding: 1.2rem;
    margin-bottom: 1rem;
    border: 1px solid #e2e8f0;
}
.job-title { font-size: 1.1rem; font-weight: 700; color: #0f172a; }
.job-company { font-size: 0.85rem; color: #475569; margin-bottom: 0.5rem; }
.job-meta { font-size: 0.75rem; color: #64748b; margin-bottom: 0.5rem; display: flex; gap: 1rem; flex-wrap: wrap; }
.stButton > button {
    border-radius: 40px;
    background: linear-gradient(90deg, #4A90E2, #6C63FF);
    color: white;
    font-weight: 600;
    border: none;
    padding: 0.5rem 1rem;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(108,99,255,0.3);
}
.pricing-card {
    background: white;
    border-radius: 20px;
    padding: 1.5rem;
    text-align: center;
    height: 100%;
    border: 1px solid #e2e8f0;
}
.pricing-title { font-size: 1.5rem; font-weight: 700; }
.pricing-price { font-size: 2rem; font-weight: 800; color: #4A90E2; margin: 1rem 0; }
.pricing-badge { background-color: #6C63FF; color: white; padding: 0.2rem 1rem; border-radius: 30px; font-size: 0.7rem; display: inline-block; margin-bottom: 1rem; }
.footer { text-align: center; margin-top: 3rem; padding-top: 1.5rem; border-top: 1px solid #e2e8f0; color: #64748b; font-size: 0.8rem; }
.tier-badge-free, .tier-badge-premium, .tier-badge-pro {
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    display: inline-block;
}
.tier-badge-free { background-color: #6c757d; color: white; }
.tier-badge-premium { background-color: #4A90E2; color: white; }
.tier-badge-pro { background: linear-gradient(90deg, #6C63FF, #4A90E2); color: white; }
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
if "analysis" not in st.session_state:
    st.session_state.analysis = None
if "target_roles" not in st.session_state:
    st.session_state.target_roles = []
if "primary_role" not in st.session_state:
    st.session_state.primary_role = ""
if "jobs" not in st.session_state:
    st.session_state.jobs = []
if "match_scores" not in st.session_state:
    st.session_state.match_scores = {}
if "saved_jobs" not in st.session_state:
    st.session_state.saved_jobs = []
if "generated_cv" not in st.session_state:
    st.session_state.generated_cv = ""
if "cover_letter_for_job" not in st.session_state:
    st.session_state.cover_letter_for_job = None

# Stripe callbacks
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
# 4. Helper Functions (complete)
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

def parse_adzuna_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        return None

def filter_recent_jobs(jobs, days=30):
    cutoff = datetime.now() - timedelta(days=days)
    recent = []
    for job in jobs:
        job_date = None
        if job.get('created'):
            job_date = parse_adzuna_date(job['created'])
        if job_date and job_date >= cutoff:
            recent.append(job)
        elif not job_date:
            recent.append(job)
    recent.sort(key=lambda x: parse_adzuna_date(x.get('created')) or datetime.min, reverse=True)
    return recent

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
                    "closing_date": closing_date,
                    "created": created,
                    "is_expired": is_expired
                })
            active_jobs = [job for job in formatted if not job.get("is_expired")]
            recent_jobs = filter_recent_jobs(active_jobs, days=30)
            return deduplicate_jobs(recent_jobs)[:limit]
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
                    "brief_description": "...",
                    "date_posted": "..."
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
            "date_display": f"📅 {j.get('date_posted', 'Recently posted')}",
            "closing_date": None,
            "created": j.get('date_posted'),
            "is_expired": False
        } for j in jobs]
    except:
        return []

def get_job_matches(cv_text, analysis, manual_query, country_name, country_code, location_refine, limit=5):
    target_roles = analysis.get("target_roles", [])
    if target_roles and target_roles[0] != "N/A":
        query = target_roles[0]
        source = "CV analysis"
    else:
        query = generate_job_query(cv_text).strip()
        source = "CV text extraction"
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
            st.warning(f"No recent {query} jobs found via Adzuna. Trying expanded search...")
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

def remove_background_and_make_transparent(image_bytes):
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    data = np.array(img)
    if data.shape[2] == 3:
        alpha = np.ones((data.shape[0], data.shape[1]), dtype=np.uint8) * 255
        white_mask = (data[:, :, 0] > 200) & (data[:, :, 1] > 200) & (data[:, :, 2] > 200)
        alpha[white_mask] = 0
        data = np.dstack((data, alpha))
    else:
        alpha = data[:, :, 3]
        white_mask = (data[:, :, 0] > 200) & (data[:, :, 1] > 200) & (data[:, :, 2] > 200)
        alpha[white_mask] = 0
        data[:, :, 3] = alpha
    result_img = Image.fromarray(data, "RGBA")
    output = BytesIO()
    result_img.save(output, format="PNG")
    output.seek(0)
    return output

@st.cache_data(ttl=3600)
def generate_job_description(job_title, company):
    prompt = f"Write a one‑sentence (max 150 characters) job description for a {job_title} position at {company}."
    try:
        return model.generate_content(prompt).text.strip()
    except:
        return "Description not available."

def generate_job_specific_cover_letter(cv_text, job_title, company, job_description):
    prompt = f"""
    Write a professional, tailored cover letter for the following job:

    Job Title: {job_title}
    Company: {company}
    Job Description: {job_description[:1500]}

    Use the candidate's CV below. DO NOT invent experience.
    Keep the letter to 250-350 words. Be specific about why the candidate is a good fit.

    CV:
    {cv_text[:6000]}
    """
    response = model.generate_content(prompt)
    return response.text

# ---------------------------
# 5. UI – Hero & CV Upload
# ---------------------------
st.markdown("""
<div class="hero">
    <div class="hero-badge">🤖 AI-POWERED CAREER INTELLIGENCE</div>
    <h1>📈 AI Career Intelligence</h1>
    <p>Upload your CV → Get recruiter feedback → Improve → Find jobs → Generate cover letters</p>
</div>
""", unsafe_allow_html=True)

# Tier badge
if st.session_state.pro:
    st.markdown('<div style="text-align:right;"><span class="tier-badge-pro">🚀 PRO</span></div>', unsafe_allow_html=True)
elif st.session_state.premium:
    st.markdown('<div style="text-align:right;"><span class="tier-badge-premium">⭐ PREMIUM</span></div>', unsafe_allow_html=True)
else:
    st.markdown('<div style="text-align:right;"><span class="tier-badge-free">🔓 FREE</span></div>', unsafe_allow_html=True)

uploaded_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])

if not uploaded_file:
    st.info("👆 Please upload your CV to begin.")
    st.stop()

cv_text = extract_text_from_file(uploaded_file)
st.session_state.cv_text = cv_text

with st.spinner("Analysing your CV with AI..."):
    analysis = analyze_cv_cached(cv_text, full=False)
    st.session_state.analysis = analysis
    st.session_state.target_roles = analysis.get('target_roles', [])
    st.session_state.primary_role = st.session_state.target_roles[0] if st.session_state.target_roles and st.session_state.target_roles[0] != "N/A" else "your target role"

# Interpretation
strength = analysis['strength_score']
if strength >= 70:
    interpretation = "✅ Your CV is competitive. Minor improvements could increase interview chances significantly."
elif strength >= 50:
    interpretation = "📈 Your CV has good foundations. Addressing keyword gaps will boost recruiter interest."
else:
    interpretation = "⚠️ Your CV needs structural improvement. The suggestions below will help you stand out."
st.info(interpretation)

# Metrics row
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{analysis['strength_score']}</div>
        <div class="metric-label">Overall CV Strength</div>
    </div>
    """, unsafe_allow_html=True)
with col2:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{analysis['ats_score']}</div>
        <div class="metric-label">ATS Readiness</div>
    </div>
    """, unsafe_allow_html=True)
with col3:
    interview_label = analysis.get('interview_likelihood', 'Moderate')
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">{interview_label}</div>
        <div class="metric-label">Interview Likelihood</div>
    </div>
    """, unsafe_allow_html=True)
with col4:
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-value">✓</div>
        <div class="metric-label">Recruiter Verdict</div>
        <div style="font-size:0.75rem;">{analysis['recruiter_verdict'][:60]}...</div>
    </div>
    """, unsafe_allow_html=True)

# ---------------------------
# Action Cards (Improve CV, Find Jobs, Saved Jobs)
# ---------------------------
st.markdown("---")
col_left, col_mid, col_right = st.columns(3)

# Left: Improve CV
with col_left:
    with st.container():
        st.markdown('<div class="action-card">', unsafe_allow_html=True)
        st.markdown('<div class="action-title">📝 Improve Your CV</div>', unsafe_allow_html=True)
        if not st.session_state.premium and not st.session_state.pro:
            preview = get_missing_keywords_preview(st.session_state.cv_text)
            preview_list = [k.strip() for k in preview.split(",") if k.strip()]
            if preview_list:
                st.markdown(f"**Missing keywords preview:** `{preview_list[0]}, [LOCKED], [LOCKED]`")
            st.markdown("🔒 **Upgrade to see full missing keywords and rewrite suggestions**")
            if st.button("⭐ Upgrade Now →", key="upgrade_from_improve"):
                pass
        else:
            full_analysis = analyze_cv_cached(st.session_state.cv_text, full=True)
            st.markdown("**Missing ATS Keywords:**")
            st.markdown(", ".join(full_analysis.get('missing_keywords', [])))
            st.markdown("**Rewrite Suggestions:**")
            for sug in full_analysis.get('rewrite_suggestions', []):
                st.markdown(f"- {sug}")
            if st.session_state.pro:
                if st.button("📄 Generate Improved CV Draft", use_container_width=True):
                    improved = generate_improved_cv(st.session_state.cv_text, st.session_state.primary_role)
                    st.session_state.generated_cv = improved
                if st.session_state.generated_cv:
                    st.text_area("Improved CV Draft", st.session_state.generated_cv, height=200)
                    docx_file = create_docx_from_text(st.session_state.generated_cv, "Improved CV")
                    st.download_button("📥 Download CV", docx_file, file_name="improved_cv.docx")
            else:
                st.info("🚀 Upgrade to Pro for CV draft generator")
        st.markdown('</div>', unsafe_allow_html=True)

# Middle: Find Jobs
with col_mid:
    with st.container():
        st.markdown('<div class="action-card">', unsafe_allow_html=True)
        st.markdown('<div class="action-title">🌍 Find Matching Jobs</div>', unsafe_allow_html=True)
        st.caption(f"🎯 Searching for: **{st.session_state.primary_role}**")
        col_loc1, col_loc2 = st.columns(2)
        with col_loc1:
            country_display = st.selectbox("Country", list(COUNTRY_MAP.keys()), index=0, key="country_select")
            country_code = COUNTRY_MAP[country_display]
        with col_loc2:
            location_refine = st.text_input("City / Region", placeholder="e.g., London, Nairobi, Remote", key="location_input")
        manual_query = st.text_input("Override job title (optional)", placeholder=f"Leave empty to use {st.session_state.primary_role}", key="manual_query_input")
        search_clicked = st.button("🔍 Search for Jobs", use_container_width=True, type="primary")

        if search_clicked:
            with st.spinner("Searching for jobs..."):
                if st.session_state.pro:
                    job_limit = 25
                elif st.session_state.premium:
                    job_limit = 10
                else:
                    job_limit = 1
                jobs = get_job_matches(st.session_state.cv_text, st.session_state.analysis, manual_query, country_display, country_code, location_refine, limit=job_limit)
                st.session_state.jobs = jobs
                st.session_state.match_scores = {}

        if st.session_state.jobs:
            for idx, job in enumerate(st.session_state.jobs):
                st.markdown(f"""
                <div class="job-card">
                    <div class="job-title">{job['title']}</div>
                    <div class="job-company">{job['company']}</div>
                    <div class="job-meta">
                        <span>📍 {job.get('location', 'Not specified')}</span>
                        <span>{job.get('date_display', '📅 Date not specified')}</span>
                        {f"<span>⚠️ Closing: {job['closing_date']}</span>" if job.get('closing_date') else ""}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Match score with explanation
                score_key = f"score_{idx}"
                if st.session_state.premium or st.session_state.pro:
                    if st.button(f"🎯 Show Match Score", key=f"match_btn_{idx}"):
                        score, reason = score_job_match(st.session_state.cv_text, job['title'], job.get('description', ''))
                        st.session_state.match_scores[score_key] = (score, reason)
                    if score_key in st.session_state.match_scores:
                        score, reason = st.session_state.match_scores[score_key]
                        st.write(f"**Match Score:** {score}%")
                        st.caption(f"📝 {reason}")
                else:
                    st.caption("🔒 Match score available after upgrade")

                # Job-specific cover letter button
                if st.button(f"✉️ Generate Cover Letter for this job", key=f"cover_btn_{idx}"):
                    with st.spinner("Generating tailored cover letter..."):
                        if st.session_state.premium or st.session_state.pro:
                            job_desc = job.get('description', '')
                            if not job_desc or len(job_desc) < 20:
                                job_desc = f"A {job['title']} position at {job['company']}."
                            letter = generate_job_specific_cover_letter(
                                st.session_state.cv_text,
                                job['title'],
                                job['company'],
                                job_desc
                            )
                            st.session_state.cover_letter_for_job = letter
                        else:
                            st.session_state.cover_letter_for_job = "Upgrade to Premium to generate cover letters."
                if st.session_state.cover_letter_for_job:
                    st.text_area("Generated Cover Letter", st.session_state.cover_letter_for_job, height=250)
                    docx_file = create_docx_from_text(st.session_state.cover_letter_for_job, "Cover Letter")
                    st.download_button("📥 Download Cover Letter", docx_file, file_name="cover_letter.docx")

                # Save job button
                if st.button(f"💾 Save this job", key=f"save_{idx}"):
                    if not any(saved.get('url') == job['url'] for saved in st.session_state.saved_jobs):
                        st.session_state.saved_jobs.append({
                            "title": job['title'],
                            "company": job['company'],
                            "url": job['url'],
                            "location": job.get('location', ''),
                            "date_display": job.get('date_display', ''),
                            "applied": False,
                            "note": ""
                        })
                        st.success("Job saved!")
                st.markdown(f"[Apply Now]({job['url']})")
                st.markdown("---")
        st.markdown('</div>', unsafe_allow_html=True)

# Right: Saved Jobs
with col_right:
    with st.container():
        st.markdown('<div class="action-card">', unsafe_allow_html=True)
        st.markdown('<div class="action-title">💾 Your Saved Jobs</div>', unsafe_allow_html=True)
        if not st.session_state.saved_jobs:
            st.info("Jobs you save will appear here. Click 'Save this job' on any job listing.")
        else:
            for i, saved in enumerate(st.session_state.saved_jobs):
                st.markdown(f"**{saved['title']}** at {saved['company']}")
                st.caption(f"📍 {saved.get('location', '')} | {saved.get('date_display', '')}")
                applied = st.checkbox("Applied", key=f"applied_{i}", value=saved.get('applied', False))
                note = st.text_input("Note", key=f"note_{i}", value=saved.get('note', ''))
                saved['applied'] = applied
                saved['note'] = note
                if st.button(f"Remove", key=f"remove_{i}"):
                    st.session_state.saved_jobs.pop(i)
                    st.rerun()
                st.markdown("---")
        st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------
# Upgrade & Reports Section
# ---------------------------
st.markdown("---")
st.subheader("🚀 Upgrade Your Career Toolkit")
st.markdown("Unlock full potential with our premium plans.")
col_card1, col_card2 = st.columns(2)
with col_card1:
    st.markdown("""
    <div class="pricing-card">
        <div class="pricing-badge">⭐ MOST POPULAR</div>
        <div class="pricing-title">Premium</div>
        <div class="pricing-price">$7<span style="font-size:1rem;">/month</span></div>
        <div class="pricing-price" style="font-size:1.2rem;">or $29 lifetime</div>
        <div class="pricing-features">
            ✅ Recruiter verdict<br>
            ✅ Missing keywords & rewrite suggestions<br>
            ✅ 10 job matches + match scores<br>
            ✅ Full cover‑letter diagnostics<br>
            ✅ ATS checklist & PDF report
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("⭐ Premium Monthly $7", use_container_width=True):
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_PRICE_ID_PREMIUM_MONTHLY, "quantity": 1}],
                mode="subscription",
                success_url=APP_URL + "?success_premium_monthly=true",
                cancel_url=APP_URL,
            )
            st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely</a>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Payment error: {e}")
    if st.button("⭐ Premium Lifetime $29", use_container_width=True):
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_PRICE_ID_PREMIUM_LIFETIME, "quantity": 1}],
                mode="payment",
                success_url=APP_URL + "?success_premium_lifetime=true",
                cancel_url=APP_URL,
            )
            st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely</a>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Payment error: {e}")
with col_card2:
    st.markdown("""
    <div class="pricing-card">
        <div class="pricing-badge">🚀 BEST VALUE</div>
        <div class="pricing-title">Pro</div>
        <div class="pricing-price">$15<span style="font-size:1rem;">/month</span></div>
        <div class="pricing-price" style="font-size:1.2rem;">or $49 lifetime</div>
        <div class="pricing-features">
            ✅ All Premium features<br>
            ✅ CV draft generator<br>
            ✅ Cover letter generator<br>
            ✅ Signature cleaner<br>
            ✅ 25+ job matches<br>
            ✅ Executive intelligence report
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🚀 Pro Monthly $15", use_container_width=True):
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_PRICE_ID_PRO_MONTHLY, "quantity": 1}],
                mode="subscription",
                success_url=APP_URL + "?success_pro_monthly=true",
                cancel_url=APP_URL,
            )
            st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely</a>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Payment error: {e}")
    if st.button("🚀 Pro Lifetime $49", use_container_width=True):
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_PRICE_ID_PRO_LIFETIME, "quantity": 1}],
                mode="payment",
                success_url=APP_URL + "?success_pro_lifetime=true",
                cancel_url=APP_URL,
            )
            st.markdown(f"<a href='{session.url}' target='_blank'>Pay securely</a>", unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Payment error: {e}")

st.markdown("---")
st.subheader("🔓 Already have a code?")
col_code1, col_code2 = st.columns(2)
with col_code1:
    premium_input = st.text_input("Premium unlock code", type="password", key="premium_code_input")
    if st.button("Apply Premium Code", key="apply_premium"):
        if premium_input.strip() == PREMIUM_UNLOCK_CODE:
            st.session_state.premium = True
            st.success("✅ Premium unlocked! Refreshing...")
            st.rerun()
        else:
            st.error("❌ Invalid Premium code.")
with col_code2:
    pro_input = st.text_input("Pro unlock code", type="password", key="pro_code_input")
    if st.button("Apply Pro Code", key="apply_pro"):
        if pro_input.strip() == PRO_UNLOCK_CODE:
            st.session_state.pro = True
            st.success("✅ Pro unlocked! Refreshing...")
            st.rerun()
        else:
            st.error("❌ Invalid Pro code.")

st.subheader("📄 Reports")
if st.session_state.premium or st.session_state.pro:
    with st.spinner("Generating full analysis for report..."):
        full_analysis = analyze_cv_cached(st.session_state.cv_text, full=True)
    pdf_data = generate_pdf_report(full_analysis)
    st.download_button("📥 Download Executive PDF Report", pdf_data, file_name="executive_report.pdf")
    checklist_text = generate_ats_checklist(full_analysis)
    st.download_button("📋 Download ATS Optimization Checklist", checklist_text, file_name="ats_checklist.txt")
else:
    st.info("🔒 **PDF report and ATS checklist are available after upgrading to Premium or Pro.**")

if st.session_state.pro:
    st.subheader("✍️ Signature Cleaner")
    uploaded_sig = st.file_uploader("Upload signature image (JPG, PNG, or JPEG)", type=["jpg", "jpeg", "png"], key="sig_upload")
    if uploaded_sig:
        with st.spinner("Cleaning signature..."):
            try:
                transparent = remove_background_and_make_transparent(uploaded_sig.read())
                st.success("✅ Signature cleaned!")
                st.image(transparent, width=200)
                st.download_button("📥 Download Transparent PNG", transparent, file_name="signature_clean.png", mime="image/png")
            except Exception as e:
                st.error(f"Error: {e}")

# ---------------------------
# Footer
# ---------------------------
st.markdown("""
<div class="footer">
<b>AI Career Intelligence</b> • Powered by Gemini AI • Worldwide job search support
</div>
""", unsafe_allow_html=True)