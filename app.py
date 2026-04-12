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
.streamlit-expanderHeader { font-weight: 600; }
.block-container { padding-top: 1rem; padding-bottom: 2rem; }
h1 { font-weight: 700; }
.stProgress > div > div { background: linear-gradient(90deg, #4A90E2, #6C63FF); }
.score-caption {
    font-size: 12px;
    color: #888;
    text-align: center;
}
.credibility-note {
    font-size: 11px;
    color: #999;
    text-align: center;
    margin-top: 5px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------
# 2. Session State
# ---------------------------
if "paid" not in st.session_state:
    st.session_state.paid = False
if "cv_text" not in st.session_state:
    st.session_state.cv_text = ""
if "analysis_free" not in st.session_state:
    st.session_state.analysis_free = None
if "manual_job_query" not in st.session_state:
    st.session_state.manual_job_query = ""
if "displayed_jobs_free" not in st.session_state:
    st.session_state.displayed_jobs_free = []
if "displayed_jobs_pro" not in st.session_state:
    st.session_state.displayed_jobs_pro = []

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
    - strength_score: 0-100 (Overall CV quality - impact, achievements, clarity, alignment)
    - ats_score: 0-100 (How well this CV would perform with automated screening systems)
    - interview_likelihood: "Low", "Moderate", or "High" (Estimated chance of getting interviews)
    - recruiter_verdict: One sentence explaining the scores, especially if ATS score is high but interview likelihood is low
    - experience_level: "Entry","Mid","Senior"
    - target_roles: List of 2-3 roles this CV aligns with
    - top_strengths: List of 2-3 strengths
    - top_weaknesses: List of 2-3 weaknesses

    If full == true, also include:
    - missing_keywords: List of 4-8 keywords recruiters would expect
    - rewrite_suggestions: List of 3-5 specific improvement suggestions

    For the verdict: If ATS score is high but interview likelihood is low, explain that the CV is machine-readable but lacks compelling achievements or role alignment.

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
    mapping = {
        "Low": "0-20%",
        "Moderate": "30-60%",
        "High": "65-85%"
    }
    return mapping.get(likelihood, "30-60%")

@st.cache_data(ttl=3600)
def generate_job_query(cv_text):
    prompt = f"""
    Extract 3 likely job titles from this CV.
    Return ONLY comma-separated titles.
    No explanation.
    CV:
    {cv_text[:6000]}
    """
    return model.generate_content(prompt).text.strip()

def deduplicate_jobs(jobs):
    seen = set()
    unique_jobs = []
    for job in jobs:
        unique_key = f"{job.get('title', '')}_{job.get('company', '')}".lower()
        if unique_key not in seen:
            seen.add(unique_key)
            unique_jobs.append(job)
    return unique_jobs

def get_jobs_from_adzuna(query, country_code, location_refine, limit=5):
    url = f"https://api.adzuna.com/v1/api/jobs/{country_code}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": JOB_API_KEY,
        "results_per_page": limit * 2,
        "what": query,
        "content-type": "json"
    }
    if location_refine and location_refine.strip():
        params["where"] = location_refine.strip()
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            jobs = resp.json().get("results", [])
            formatted_jobs = []
            for j in jobs:
                company = j.get("company", {})
                if isinstance(company, dict):
                    company_name = company.get("display_name", "Unknown Company")
                else:
                    company_name = str(company) if company else "Unknown Company"
                
                formatted_jobs.append({
                    "title": j.get("title", "Untitled Position"),
                    "company": company_name,
                    "location": location_refine or country_code.upper(),
                    "url": j.get("redirect_url", "#"),
                    "description": j.get("description", "")
                })
            unique_jobs = deduplicate_jobs(formatted_jobs)
            return unique_jobs[:limit]
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
            "jobs":[
                {{
                    "job_title":"...",
                    "company_name":"...",
                    "location":"...",
                    "apply_url":"...",
                    "brief_description":"..."
                }}
            ]
        }}
        """
        response = model.generate_content(prompt)
        raw = clean_json_response(response.text)
        result = json.loads(raw)
        jobs = result.get("jobs", [])
        return [
            {
                "title": job.get("job_title", "Untitled Position"),
                "company": job.get("company_name", "Unknown Company"),
                "location": job.get("location", location),
                "url": job.get("apply_url", "#"),
                "description": job.get("brief_description", "")
            }
            for job in jobs
        ]
    except Exception as e:
        return []

def get_job_matches(cv_text, analysis, manual_query, country_code, country_name, location_refine, limit=5):
    query = manual_query
    if not query or len(query) < 3:
        target_roles = analysis.get('target_roles', [])
        if target_roles and target_roles[0] != "N/A":
            query = target_roles[0]
        else:
            query = generate_job_query(cv_text)
    
    if not query or len(query) < 3:
        return []
    
    adzuna_countries = ["us", "gb", "ca", "au", "de", "fr", "in", "za"]
    
    if country_code in adzuna_countries:
        jobs = get_jobs_from_adzuna(query, country_code, location_refine, limit)
        if len(jobs) < 2:
            search_location = f"{location_refine}, {country_name}" if location_refine else country_name
            gemini_jobs = get_jobs_from_gemini_search(cv_text, query, search_location, limit - len(jobs))
            jobs.extend(gemini_jobs)
        return jobs
    else:
        search_location = f"{location_refine}, {country_name}" if location_refine else country_name
        return get_jobs_from_gemini_search(cv_text, query, search_location, limit)

@st.cache_data(ttl=3600)
def score_job_match(cv_text, job_title, job_description=""):
    prompt = f"""
    Score 0-100 match between CV and job '{job_title}'. 
    Then provide a brief reason (max 10 words).
    Return JSON: {{"score": integer, "reason": "string"}}
    CV snippet:
    {cv_text[:2000]}
    Description:
    {job_description[:500]}
    """
    response = model.generate_content(prompt)
    raw = clean_json_response(response.text)
    try:
        result = json.loads(raw)
        return result.get("score", 50), result.get("reason", "Based on role alignment")
    except:
        return 50, "Based on general alignment"

@st.cache_data(ttl=3600)  # FIX: Added cache back
def get_missing_keywords_preview(cv_text):
    prompt = f"""
    From this CV, identify 3 high-impact keywords missing that would most improve interview chances.
    Return ONLY comma-separated keywords.
    Choose the most important recruiter-visible gaps.
    CV:
    {cv_text[:5000]}
    """
    response = model.generate_content(prompt)
    return response.text.strip()

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
<p class='credibility-note'>
🤖 Scores are AI estimates based on recruiter best practices
</p>
""", unsafe_allow_html=True)

colA, colB, colC = st.columns(3)
colA.markdown("✅ **Recruiter-style CV assessment**")
colB.markdown("🤖 **Powered by Gemini AI**")
colC.markdown("🌍 **Worldwide job search support**")  # Changed from "Global job coverage"

st.divider()

uploaded_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    cv_text = extract_text_from_file(uploaded_file)
    st.session_state.cv_text = cv_text

    with st.status("Analyzing your CV...", expanded=True) as status:
        st.write("📄 Reading CV document...")
        analysis = analyze_cv_cached(cv_text, full=False)
        st.session_state.analysis_free = analysis
        
        st.write("🔍 Analyzing keywords and structure...")
        st.write("📊 Estimating ATS compatibility...")
        st.write("🎯 Identifying target roles...")
        status.update(label="Analysis complete!", state="complete")

    # Metrics with improved labeling
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("📊 Overall CV Strength")
        st.progress(analysis['strength_score']/100)
        st.caption(f"{analysis['strength_score']}/100")
        st.caption("🎯 *Impact & achievements*")
    
    with col2:
        st.write("🤖 ATS Readiness")
        st.progress(analysis['ats_score']/100)
        st.caption(f"{analysis['ats_score']}/100")
        st.caption("📋 *Machine readability*")
    
    with col3:
        interview_pct = get_interview_percentage(analysis.get('interview_likelihood', 'Moderate'))
        st.write("🎯 Interview Likelihood")
        st.caption(f"**{analysis.get('interview_likelihood', 'Moderate')}**")
        st.caption(f"📊 *Estimated {interview_pct} chance*")
        st.caption("📝 *Based on recruiter patterns*")

    st.info(f"**Recruiter Assessment:** {analysis['recruiter_verdict']}")

    st.subheader("📌 Key Insights")
    st.markdown(f"**Experience Level:** {analysis['experience_level']}")
    st.markdown(f"**Target Roles:** {', '.join(analysis['target_roles'])}")
    with st.expander("Strengths & Weaknesses"):
        st.markdown("**Strengths:**\n" + "\n".join(f"- {s}" for s in analysis['top_strengths']))
        st.markdown("**Weaknesses:**\n" + "\n".join(f"- {w}" for w in analysis['top_weaknesses']))

    # ---------------------------
    # Job Search Settings
    # ---------------------------
    st.subheader("🌍 Job Search Settings")
    
    col_loc1, col_loc2 = st.columns(2)
    with col_loc1:
        country_option = st.selectbox(
            "Country",
            options=["us", "gb", "ca", "au", "de", "fr", "in", "za", "other"],
            format_func=lambda x: {
                "us": "United States", "gb": "United Kingdom", "ca": "Canada",
                "au": "Australia", "de": "Germany", "fr": "France", "in": "India",
                "za": "South Africa", "other": "🌍 Other (Botswana, Ghana, etc.)"
            }.get(x, x.upper()),
            index=0,
            key="country_select"
        )
    with col_loc2:
        location_refine = st.text_input("City / Region (optional)", placeholder="e.g., Gaborone, London, Nairobi")
    
    if country_option == "other":
        country_name = st.text_input("Country name", placeholder="Botswana, Ghana, Nigeria...")
        
        if country_name and "botswana" in country_name.lower():
            st.info("""
            🔎 **Additional Botswana job portals:**
            
            • [Dumela Jobs](https://www.dumelajobs.com)
            • [JobWeb Botswana](https://bw.jobwebbotswana.com)
            • [LinkedIn Botswana Jobs](https://www.linkedin.com/jobs)
            """)
    else:
        country_name = country_option.upper()

    manual_query = st.text_input(
        "Override job title (optional)",
        value=st.session_state.manual_job_query,
        placeholder="e.g., Registered Nurse, Marketing Manager"
    )
    st.session_state.manual_job_query = manual_query

    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        search_clicked = st.button("🔍 Search for Jobs", use_container_width=True, type="primary")
    
    st.subheader("💼 Matching Jobs")
    
    job_limit = 3 if not st.session_state.paid else 20
    
    if search_clicked:
        if country_option == "other" and not country_name:
            st.error("Please enter your country name")
            display_jobs = []
        else:
            with st.spinner("Searching for jobs worldwide..."):
                jobs = get_job_matches(
                    cv_text, analysis, manual_query, 
                    country_option, country_name, location_refine, 
                    limit=job_limit
                )
                if not st.session_state.paid:
                    st.session_state.displayed_jobs_free = jobs
                else:
                    st.session_state.displayed_jobs_pro = jobs
            display_jobs = jobs
    else:
        display_jobs = st.session_state.displayed_jobs_free if not st.session_state.paid else st.session_state.displayed_jobs_pro
    
    if display_jobs:
        st.success(f"✅ Found {len(display_jobs)} jobs matching your CV!")
        for idx, job in enumerate(display_jobs):
            with st.expander(f"**{job['title']}** at {job['company']}"):
                st.markdown(f"📍 **Location:** {job.get('location', 'Not specified')}")
                if job.get('description'):
                    st.markdown(f"📝 **Description:** {job['description'][:300]}...")
                if not st.session_state.paid:
                    st.caption("🔒 **Full match score available after upgrade**")
                else:
                    if st.button(f"🎯 Show Match Score", key=f"score_btn_{idx}"):
                        match_score, match_reason = score_job_match(cv_text, job['title'], job.get('description', ''))
                        st.write(f"**Match Score:** {match_score}%")
                        st.caption(f"📝 *{match_reason}*")
                st.markdown(f"[Apply Now]({job['url']})")
    else:
        if search_clicked and not (country_option == "other" and not country_name):
            st.warning("No jobs found. Try adjusting the job title, country, or location.")
        else:
            st.info("👆 Click 'Search for Jobs' to find opportunities matching your CV.")

    # ---------------------------
    # Conversion Section (Upgrade)
    # ---------------------------
    if not st.session_state.paid:
        st.markdown("---")
        
        st.markdown("""
        <div class="upgrade-box">
        <h3>🚀 Pro Career Optimization</h3>
        <p>✅ Missing ATS Keywords<br>
        ✅ Recruiter Rewrite Suggestions<br>
        ✅ Job Match Scoring<br>
        ✅ Executive PDF Report</p>
        <p><strong>Lifetime early access — $9</strong></p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("#### 🔒 Pro Preview: Missing Keywords We Found")
        with st.spinner("Analyzing your keyword gaps..."):
            real_preview = get_missing_keywords_preview(cv_text)
        
        preview_list = [k.strip() for k in real_preview.split(",") if k.strip()]
        if len(preview_list) > 1:
            blurred_preview = f"{preview_list[0]}, [LOCKED], [LOCKED]"
        else:
            blurred_preview = f"{real_preview[:30]}... [LOCKED]"
        
        st.info(f"`{blurred_preview}` (Upgrade to unlock full list)")
        
        col_left, col_right = st.columns(2)
        with col_left:
            if st.button("💳 Upgrade Now – $9 Lifetime Access", use_container_width=True):
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
    # Paid Section (Pro Features)
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
            st.download_button("📥 Download Executive Career Intelligence Report", pdf_data, file_name="career_report.pdf")
        with col_check:
            checklist_text = generate_ats_checklist(full_analysis)
            st.download_button("📋 Download ATS Optimization Checklist", checklist_text, file_name="ats_checklist.txt")
        
        st.subheader("🚀 Pro Job Matches (20+ jobs)")
        
        col_btn1p, col_btn2p, col_btn3p = st.columns([1, 2, 1])
        with col_btn2p:
            search_pro_clicked = st.button("🔍 Search for Jobs (Pro)", use_container_width=True, type="primary")
        
        if search_pro_clicked:
            if country_option == "other" and not country_name:
                st.error("Please enter your country name")
            else:
                with st.spinner("Searching for jobs worldwide..."):
                    pro_jobs = get_job_matches(cv_text, full_analysis, manual_query, country_option, country_name, location_refine, limit=20)
                    st.session_state.displayed_jobs_pro = pro_jobs
                display_pro_jobs = pro_jobs
        else:
            display_pro_jobs = st.session_state.displayed_jobs_pro
        
        if display_pro_jobs:
            st.success(f"✅ Found {len(display_pro_jobs)} jobs!")
            for idx, job in enumerate(display_pro_jobs):
                with st.expander(f"**{job['title']}** at {job['company']}"):
                    st.markdown(f"📍 **Location:** {job.get('location', 'Not specified')}")
                    if job.get('description'):
                        st.markdown(f"📝 **Description:** {job['description'][:400]}...")
                    if st.button(f"🎯 Show Match Score", key=f"score_btn_pro_{idx}"):
                        match_score, match_reason = score_job_match(cv_text, job['title'], job.get('description', ''))
                        st.write(f"**Match Score:** {match_score}%")
                        st.caption(f"📝 *{match_reason}*")
                    st.markdown(f"[Apply Now]({job['url']})")
        else:
            if search_pro_clicked and not (country_option == "other" and not country_name):
                st.warning("No jobs found. Try adjusting job title or location.")
            else:
                st.info("👆 Click 'Search for Jobs (Pro)' to find opportunities.")

else:
    st.info("👆 Please upload your CV to begin.")

st.markdown("""
<hr>
<center>
<b>AI Career Intelligence</b> • Powered by Gemini AI • Worldwide job search support
</center>
""", unsafe_allow_html=True)