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
# Using gemini-2.5-flash (stable, no shutdown until at least 2027)
model = genai.GenerativeModel("gemini-2.5-flash")
stripe.api_key = STRIPE_SECRET_KEY

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
    """Safe JSON extractor - handles markdown and finds first/last valid JSON"""
    text = text.strip()
    
    # Remove markdown code blocks
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    
    # Find first { and last } for object
    start_obj = text.find("{")
    end_obj = text.rfind("}")
    # Find first [ and last ] for array
    start_arr = text.find("[")
    end_arr = text.rfind("]")
    
    obj_candidate = text[start_obj:end_obj + 1] if start_obj != -1 and end_obj != -1 else ""
    arr_candidate = text[start_arr:end_arr + 1] if start_arr != -1 and end_arr != -1 else ""
    
    # Return the larger candidate (likely the full response)
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
    """Remove duplicate jobs based on title and company"""
    seen = set()
    unique_jobs = []
    for job in jobs:
        unique_key = f"{job.get('title', '')}_{job.get('company', '')}".lower()
        if unique_key not in seen:
            seen.add(unique_key)
            unique_jobs.append(job)
    return unique_jobs

def get_jobs_from_adzuna(query, country_code, location_refine, limit=5):
    """Get jobs from Adzuna API with deduplication and safe field access"""
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
                # SAFE: Handle missing 'display_name' key
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
        st.warning(f"Adzuna error: {e}")
        return []

def get_jobs_from_gemini_search(cv_text, job_title, location, limit=5):
    """
    Use Gemini for countries not supported by Adzuna (Botswana, Ghana, etc.)
    With improved error handling and fallback text parsing
    """
    try:
        prompt = f"""
        Find {limit} recent, legitimate job postings for a {job_title} position in {location}.
        
        For each job, provide:
        1. Job title
        2. Company name
        3. Location
        4. Direct apply URL
        5. Brief description (1 sentence)
        
        Format your response as a simple list. Do NOT use JSON.
        Just provide the information in this format:
        
        Job 1:
        Title: [job title]
        Company: [company name]
        Location: [location]
        URL: [apply link]
        Description: [brief description]
        
        Job 2:
        ...
        """
        
        response = model.generate_content(prompt)
        response_text = response.text
        
        # Parse the text response instead of JSON
        jobs = []
        lines = response_text.strip().split('\n')
        
        current_job = {}
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if line.lower().startswith('job') and ':' in line:
                # Save previous job if exists
                if current_job and 'title' in current_job:
                    jobs.append(current_job)
                current_job = {}
            elif line.lower().startswith('title:'):
                current_job['title'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('company:'):
                current_job['company'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('location:'):
                current_job['location'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('url:'):
                current_job['url'] = line.split(':', 1)[1].strip()
            elif line.lower().startswith('description:'):
                current_job['description'] = line.split(':', 1)[1].strip()
        
        # Add the last job
        if current_job and 'title' in current_job:
            jobs.append(current_job)
        
        # If parsing failed, try a simpler approach
        if not jobs:
            simple_prompt = f"""
            Find {limit} job posting URLs for {job_title} in {location}.
            Return ONLY the URLs, one per line.
            No explanations.
            """
            simple_response = model.generate_content(simple_prompt)
            urls = simple_response.text.strip().split('\n')
            
            for idx, url in enumerate(urls):
                if url.startswith('http'):
                    jobs.append({
                        "title": f"{job_title} Position {idx+1}",
                        "company": "Unknown Company",
                        "location": location,
                        "url": url,
                        "description": f"Job posting for {job_title} in {location}"
                    })
        
        # Convert to standard format
        return [{
            "title": job.get("title", f"{job_title} Position"),
            "company": job.get("company", "Unknown Company"),
            "location": job.get("location", location),
            "url": job.get("url", "#"),
            "description": job.get("description", f"Job posting for {job_title} in {location}")
        } for job in jobs[:limit]]
        
    except Exception as e:
        st.warning(f"Gemini search error: {e}")
        return []

def get_job_matches(cv_text, analysis, manual_query, country_code, country_name, location_refine, limit=5):
    """Get jobs - Adzuna for supported countries, guidance for others"""
    query = manual_query
    if not query or len(query) < 3:
        target_roles = analysis.get('target_roles', [])
        if target_roles and target_roles[0] != "N/A":
            query = target_roles[0]
        else:
            query = generate_job_query(cv_text)
    
    if not query or len(query) < 3:
        return []
    
    # For "other" countries, provide guidance instead of failing
    if country_code == "other":
        st.info(f"""
        📢 **Job search for {country_name}**  
        
        We're expanding our coverage! Meanwhile, try these options:
        
        1. Select **South Africa** or another nearby country above
        2. Use the **job title override** to search manually
        3. Check local job boards specific to {country_name}
        
        Direct job search for {country_name} coming in our next update!
        """)
        return []
    else:
        return get_jobs_from_adzuna(query, country_code, location_refine, limit)

@st.cache_data(ttl=3600)
def score_job_match(cv_text, job_title, job_description=""):
    prompt = f"Score 0-100 match between CV and job '{job_title}'. Return integer.\nCV snippet:\n{cv_text[:2000]}\nDescription:\n{job_description[:500]}"
    response = model.generate_content(prompt)
    try:
        return int(response.text.strip())
    except:
        return 50

@st.cache_data(ttl=3600)
def get_missing_keywords_preview(cv_text):
    prompt = f"""
    From this CV, identify 2-3 specific keywords that are missing that recruiters would expect.
    Return ONLY a comma-separated list.
    No explanation.
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
st.markdown("Upload your CV → Get ATS score, recruiter verdict, and job matches worldwide.")

if not st.session_state.paid:
    st.info("🔓 **Upgrade to Pro** – Unlock full rewrite suggestions, missing keywords, and more job matches.")

uploaded_file = st.file_uploader("Upload your CV (PDF or DOCX)", type=["pdf", "docx"])

if uploaded_file:
    cv_text = extract_text_from_file(uploaded_file)
    st.session_state.cv_text = cv_text

    with st.spinner("Analyzing with Gemini AI..."):
        analysis = analyze_cv_cached(cv_text, full=False)
        st.session_state.analysis_free = analysis

    # Metrics
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
    
    col_loc1, col_loc2, col_loc3 = st.columns([2, 2, 1])
    with col_loc1:
        country_option = st.selectbox(
            "Country",
            options=["other", "us", "gb", "ca", "au", "de", "fr", "in", "za", "ng", "ke"],
            format_func=lambda x: {
                "other": "🌍 Other Country (Botswana, Ghana, Zimbabwe, etc.)",
                "us": "United States", "gb": "United Kingdom", "ca": "Canada",
                "au": "Australia", "de": "Germany", "fr": "France", "in": "India",
                "za": "South Africa", "ng": "Nigeria", "ke": "Kenya"
            }.get(x, x.upper()),
            index=0,
            key="country_select"
        )
    with col_loc2:
        location_refine = st.text_input(
            "City / Region (optional)", 
            placeholder="e.g., Gaborone, London, Nairobi",
            key="location_input"
        )
    
    if country_option == "other":
        with col_loc3:
            country_name = st.text_input("Country name", placeholder="Botswana, Ghana...", key="other_country")
        if country_name and "botswana" in country_name.lower():
            st.success("🇧🇼 Botswana selected! We'll help you find jobs.")
    else:
        country_name = country_option.upper()

    manual_query = st.text_input(
        "Override job title (optional)",
        value=st.session_state.manual_job_query,
        placeholder="e.g., Registered Nurse, Marketing Manager",
        key="manual_job_input"
    )
    st.session_state.manual_job_query = manual_query

    # Search button
    col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
    with col_btn2:
        search_clicked = st.button("🔍 Search for Jobs", use_container_width=True, type="primary")
    
    st.subheader("💼 Matching Jobs")
    
    job_limit = 3 if not st.session_state.paid else 20
    
    if search_clicked:
        if country_option == "other" and not country_name:
            st.error("Please enter your country name (e.g., Botswana)")
        else:
            with st.spinner("Searching for jobs..."):
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
        for idx, job in enumerate(display_jobs):
            with st.expander(f"**{job['title']}** at {job['company']}"):
                st.markdown(f"📍 **Location:** {job.get('location', 'Not specified')}")
                if job.get('description'):
                    st.markdown(f"📝 **Description:** {job['description'][:300]}...")
                if not st.session_state.paid:
                    st.caption("🔒 **Full match score available after upgrade**")
                else:
                    if st.button(f"🎯 Show Match Score", key=f"score_btn_{idx}"):
                        match_score = score_job_match(cv_text, job['title'], job.get('description', ''))
                        st.write(f"**Match Score:** {match_score}%")
                st.markdown(f"[Apply Now]({job['url']})")
        
        if not st.session_state.paid and len(display_jobs) >= 3:
            st.info("🔓 **Upgrade to Pro** to see 20+ jobs and get AI match scores!")
    else:
        if search_clicked:
            # Don't show error if we already showed guidance
            if not (country_option == "other" and country_name):
                st.warning("No jobs found. Try adjusting the job title, country, or location.")
        else:
            st.info("👆 Click 'Search for Jobs' to find opportunities.")

    # ---------------------------
    # CONVERSION SECTION
    # ---------------------------
    if not st.session_state.paid:
        st.markdown("---")
        st.header("🏆 Unlock the Pro Career Suite")
        
        c1, c2, c3 = st.columns(3)
        c1.write("🎯 **ATS Optimization**\nGet the exact keywords missing from your CV.")
        c2.write("📝 **Bullet Point Rewrites**\nProfessional AI‑rewritten achievements.")
        c3.write("📑 **Executive PDF**\nDownloadable report for your records.")
        
        st.markdown("#### 🔒 Pro Preview: Missing Keywords We Found")
        with st.spinner("Analyzing your keyword gaps..."):
            real_preview = get_missing_keywords_preview(cv_text)
        st.info(f"`{real_preview}` (UPGRADE TO SEE ALL KEYWORDS + REWRITES)")
        
        col_left, col_right = st.columns(2)
        with col_left:
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
        
        st.subheader("🚀 Pro Job Matches (20+ jobs)")
        
        col_btn1p, col_btn2p, col_btn3p = st.columns([1, 2, 1])
        with col_btn2p:
            search_pro_clicked = st.button("🔍 Search for Jobs (Pro)", use_container_width=True, type="primary")
        
        if search_pro_clicked:
            if country_option == "other" and not country_name:
                st.error("Please enter your country name (e.g., Botswana)")
            else:
                with st.spinner("Searching for jobs..."):
                    pro_jobs = get_job_matches(cv_text, full_analysis, manual_query, country_option, country_name, location_refine, limit=20)
                    st.session_state.displayed_jobs_pro = pro_jobs
                display_pro_jobs = pro_jobs
        else:
            display_pro_jobs = st.session_state.displayed_jobs_pro
        
        if display_pro_jobs:
            for idx, job in enumerate(display_pro_jobs):
                with st.expander(f"**{job['title']}** at {job['company']}"):
                    st.markdown(f"📍 **Location:** {job.get('location', 'Not specified')}")
                    if job.get('description'):
                        st.markdown(f"📝 **Description:** {job['description'][:400]}...")
                    if st.button(f"🎯 Show Match Score", key=f"score_btn_pro_{idx}"):
                        match_score = score_job_match(cv_text, job['title'], job.get('description', ''))
                        st.write(f"**Match Score:** {match_score}%")
                    st.markdown(f"[Apply Now]({job['url']})")
        else:
            if search_pro_clicked:
                if not (country_option == "other" and country_name):
                    st.warning("No jobs found. Try adjusting job title or location.")
            else:
                st.info("👆 Click 'Search for Jobs (Pro)' to find opportunities.")

else:
    st.info("👆 Please upload your CV to begin.")

st.markdown("---")
st.caption("AI Career Intelligence – Powered by Gemini 2.5 Flash | No duplicates | Global coverage")