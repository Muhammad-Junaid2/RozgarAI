"""
RozgarAI — AI Career & Job Application Agent
Streamlit front-end.
"""
from __future__ import annotations

import os
import streamlit as st

from cv_utils import CVExtractionError, extract_cv_text, truncate_text
from agents import career_manager_pipeline, AgentError, MOCK_MODE

st.set_page_config(page_title="RozgarAI — Career Agent", page_icon="🧭", layout="wide")

# --------------------------------------------------------------------------
# Sidebar
# --------------------------------------------------------------------------
with st.sidebar:
    st.title("🧭 RozgarAI")
    st.caption("AI Career & Job Application Agent")

    st.markdown(
        "**How it works**\n\n"
        "1. Upload your CV\n"
        "2. Paste the job description\n"
        "3. The Career Manager agent runs 6 specialist agents:\n"
        "   CV Analyzer → Skills → Job Match → Interview → Roadmap → "
        "Cover Letter / LinkedIn"
    )

st.title("RozgarAI — AI Career & Job Application Agent")
st.caption("Upload your CV + a job description. Get an ATS score, skill gap analysis, "
           "interview prep, a learning roadmap, and a tailored cover letter.")

# --------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------
col1, col2 = st.columns(2)

with col1:
    st.subheader("1. Your CV")
    cv_file = st.file_uploader("Upload CV (PDF, DOCX, or TXT)", type=["pdf", "docx", "txt"])
    cv_text_manual = st.text_area(
        "...or paste CV text directly",
        height=200,
        placeholder="Paste your CV text here if you'd rather not upload a file.",
    )

with col2:
    st.subheader("2. Job Description")
    jd_text = st.text_area(
        "Paste the job description",
        height=280,
        placeholder="Paste the full job description here...",
    )

run_button = st.button("🚀 Run Career Agent", type="primary", use_container_width=True)

# --------------------------------------------------------------------------
# Pipeline execution
# --------------------------------------------------------------------------
if run_button:
    cv_text = ""
    error = None

    if cv_file is not None:
        try:
            cv_text = extract_cv_text(cv_file.name, cv_file.read())
        except CVExtractionError as e:
            error = str(e)
    elif cv_text_manual.strip():
        cv_text = cv_text_manual.strip()
    else:
        error = "Please upload a CV file or paste your CV text."

    if not jd_text.strip() and not error:
        error = "Please paste a job description."

    if error:
        st.error(error)
    else:
        cv_text = truncate_text(cv_text)
        jd_text_clean = truncate_text(jd_text.strip())

        progress_bar = st.progress(0, text="Starting Career Manager agent...")
        steps_done = {"count": 0}
        TOTAL_STEPS = 7

        def on_progress(step_name: str):
            steps_done["count"] += 1
            pct = min(int(steps_done["count"] / TOTAL_STEPS * 100), 100)
            progress_bar.progress(pct, text=step_name)

        try:
            results = career_manager_pipeline(cv_text, jd_text_clean, progress_cb=on_progress)
            progress_bar.progress(100, text="Done!")
            st.session_state["results"] = results
        except AgentError as e:
            st.error(f"The agent pipeline failed: {e}")
        except Exception as e:  # noqa: BLE001
            st.error(f"Unexpected error: {e}")

# --------------------------------------------------------------------------
# Results display
# --------------------------------------------------------------------------
if "results" in st.session_state:
    r = st.session_state["results"]
    cv_analysis = r["cv_analysis"]
    skills = r["skills"]
    job_match = r["job_match"]
    interview = r["interview"]
    roadmap = r["roadmap"]
    cover_letter = r["cover_letter"]
    linkedin = r["linkedin"]

    st.divider()
    st.header("Results")

    tabs = st.tabs([
        "📊 ATS & CV",
        "🧩 Skills Gap",
        "🎯 Job Match",
        "🗣️ Interview Prep",
        "🗺️ Roadmap",
        "✉️ Cover Letter",
        "💼 LinkedIn",
    ])

    with tabs[0]:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("ATS Score", f"{cv_analysis.get('ats_score', '—')}/100")
        with c2:
            st.write(cv_analysis.get("score_reasoning", ""))

        st.subheader("Formatting Issues")
        for issue in cv_analysis.get("formatting_issues", []):
            st.markdown(f"- ⚠️ {issue}")

        st.subheader("Weak / Generic Keywords")
        st.write(", ".join(cv_analysis.get("weak_keywords", [])) or "None found.")

        st.subheader("Strong Sections")
        for s in cv_analysis.get("strong_sections", []):
            st.markdown(f"- ✅ {s}")

        st.subheader("Improvement Suggestions")
        for s in cv_analysis.get("improvement_suggestions", []):
            st.markdown(f"- 💡 {s}")

    with tabs[1]:
        st.metric("Skill Match", f"{skills.get('skill_match_percentage', '—')}%")
        st.write(skills.get("gap_summary", ""))

        c1, c2, c3 = st.columns(3)
        with c1:
            st.subheader("✅ Matching")
            for s in skills.get("matching_skills", []):
                st.markdown(f"- {s}")
        with c2:
            st.subheader("❌ Missing")
            for s in skills.get("missing_skills", []):
                st.markdown(f"- {s}")
        with c3:
            st.subheader("➕ Nice-to-have gaps")
            for s in skills.get("nice_to_have_gaps", []):
                st.markdown(f"- {s}")

    with tabs[2]:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.metric("Compatibility", f"{job_match.get('compatibility_score', '—')}/100")
            st.markdown(f"**Verdict:** {job_match.get('verdict', '—')}")
        with c2:
            st.write(job_match.get("reasoning", ""))

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("⚠️ Top Risks")
            for s in job_match.get("top_risks", []):
                st.markdown(f"- {s}")
        with c2:
            st.subheader("⚡ Quick Wins")
            for s in job_match.get("quick_wins", []):
                st.markdown(f"- {s}")

    with tabs[3]:
        for i, q in enumerate(interview.get("questions", []), start=1):
            with st.expander(f"{i}. [{q.get('type', '')}] {q.get('question', '')}"):
                st.markdown(q.get("personalized_answer_outline", ""))

    with tabs[4]:
        st.info(f"**Immediate next step:** {roadmap.get('immediate_next_step', '')}")
        for wk in roadmap.get("roadmap", []):
            st.subheader(f"Week {wk.get('week')}: {wk.get('focus')}")
            for t in wk.get("tasks", []):
                st.markdown(f"- {t}")
            st.caption(f"Resource: {wk.get('resource_hint', '')}")

    with tabs[5]:
        letter_text = cover_letter.get("cover_letter", "")
        st.text_area("Cover Letter", value=letter_text, height=400)
        st.download_button(
            "⬇️ Download Cover Letter (.txt)",
            data=letter_text,
            file_name="cover_letter.txt",
        )

    with tabs[6]:
        st.subheader("Headline Options")
        for h in linkedin.get("headline_options", []):
            st.markdown(f"- {h}")
        st.subheader("About Section")
        st.text_area("About", value=linkedin.get("about_section", ""), height=180)
        st.subheader("Profile Suggestions")
        for s in linkedin.get("suggestions", []):
            st.markdown(f"- {s}")
