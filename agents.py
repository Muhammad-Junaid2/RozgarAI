"""
agents.py
The "agentic" core of RozgarAI.

Each *_agent() function is a focused worker that takes plain text in and
returns a structured dict out. career_manager_pipeline() is the orchestrator
("Career Manager Agent") that runs them in the right order and passes
context between them, mirroring the architecture diagram:

    CV + JD -> Career Manager -> CV Analyzer / Skills / Job Match
            -> Interview Agent -> Roadmap / Cover Letter / LinkedIn

MOCK MODE:
If no Gemini API key is configured (or MOCK_MODE=1 is set), every agent
returns deterministic canned data instead of calling the network. This lets
the whole pipeline be exercised and unit-tested without an API key or
network access — useful in CI, or while wiring up the UI.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

MOCK_MODE = os.environ.get("MOCK_MODE", "").lower() in ("1", "true", "yes") or not os.environ.get(
    "GEMINI_API_KEY"
)

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


class AgentError(Exception):
    """Raised when an agent call fails and cannot be recovered."""


# --------------------------------------------------------------------------
# LLM call wrapper
# --------------------------------------------------------------------------

def _get_client():
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise AgentError("GEMINI_API_KEY is not set.")
    genai.configure(api_key=api_key)
    return genai


def _extract_json(raw: str) -> dict:
    """Best-effort JSON extraction in case the model wraps output in prose/fences."""
    raw = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", raw, re.DOTALL)
    if fence_match:
        raw = fence_match.group(1)
    else:
        brace_match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
        if brace_match:
            raw = brace_match.group(1)
    return json.loads(raw)


def call_llm_json(system_prompt: str, user_prompt: str, mock_fn: Callable[[], dict]) -> dict:
    """
    Call Gemini and expect a JSON object back. Falls back to mock_fn() in MOCK_MODE
    or if the real call fails, so the pipeline never crashes the UI outright —
    callers should still surface failures to the user rather than hide them.
    """
    if MOCK_MODE:
        return mock_fn()

    genai = _get_client()
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system_prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    try:
        response = model.generate_content(user_prompt)
        return _extract_json(response.text)
    except Exception as exc:  # noqa: BLE001 - surface as AgentError with context
        raise AgentError(f"Gemini call failed: {exc}") from exc


# --------------------------------------------------------------------------
# Agent 1: CV Analyzer Agent
# --------------------------------------------------------------------------

def cv_analyzer_agent(cv_text: str) -> dict:
    system = (
        "You are an expert ATS (Applicant Tracking System) resume auditor. "
        "You review resumes the way real ATS software and recruiters do: "
        "checking structure, keyword density, formatting, and clarity. "
        "Respond ONLY with a single JSON object, no prose, no markdown fences."
    )
    user = f"""Analyze this CV and return a JSON object with EXACTLY these keys:
{{
  "ats_score": <integer 0-100>,
  "score_reasoning": "<2-3 sentence explanation of the score>",
  "formatting_issues": ["<issue 1>", "<issue 2>", ...],
  "weak_keywords": ["<generic/weak phrase 1>", ...],
  "strong_sections": ["<section that is well written>", ...],
  "improvement_suggestions": ["<concrete, specific suggestion>", ...]
}}

CV TEXT:
---
{cv_text}
---
"""

    def mock():
        return {
            "ats_score": 78,
            "score_reasoning": "Mock mode: solid structure and relevant experience, but "
            "several bullet points are outcome-vague and a few standard ATS section "
            "headers are missing.",
            "formatting_issues": [
                "No dedicated 'Skills' section header (skills are buried in summary)",
                "Dates are inconsistently formatted (mix of 'Jan 2023' and '01/2023')",
            ],
            "weak_keywords": ["hard worker", "team player", "responsible for"],
            "strong_sections": ["Project descriptions", "Education"],
            "improvement_suggestions": [
                "Add a standalone 'Technical Skills' section near the top.",
                "Quantify achievements (e.g. 'reduced load time by 40%' instead of 'improved performance').",
                "Replace passive phrases like 'responsible for' with action verbs like 'built', 'led', 'shipped'.",
            ],
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Agent 2: Skills Agent
# --------------------------------------------------------------------------

def skills_agent(cv_text: str, jd_text: str) -> dict:
    system = (
        "You are a technical recruiter who specializes in mapping candidate skills "
        "to job requirements with precision. Respond ONLY with a single JSON object."
    )
    user = f"""Compare the CV against the Job Description. Return JSON with EXACTLY these keys:
{{
  "matching_skills": ["<skill present in both CV and JD>", ...],
  "missing_skills": ["<skill required by JD but absent/weak in CV>", ...],
  "nice_to_have_gaps": ["<skill mentioned as a plus in JD but missing>", ...],
  "skill_match_percentage": <integer 0-100>,
  "gap_summary": "<2-3 sentence plain-English summary of the gap>"
}}

CV TEXT:
---
{cv_text}
---

JOB DESCRIPTION:
---
{jd_text}
---
"""

    def mock():
        return {
            "matching_skills": ["Python", "SQLite", "Tkinter", "Git", "OOP design"],
            "missing_skills": ["Django", "REST API design", "Docker", "CI/CD"],
            "nice_to_have_gaps": ["AWS", "PostgreSQL"],
            "skill_match_percentage": 62,
            "gap_summary": "Mock mode: strong desktop/Python fundamentals, but the JD leans "
            "heavily on web-backend and deployment skills that aren't yet demonstrated in the CV.",
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Agent 3: Job Match Agent
# --------------------------------------------------------------------------

def job_match_agent(cv_text: str, jd_text: str, cv_analysis: dict, skills: dict) -> dict:
    system = (
        "You are a hiring manager deciding whether to advance a candidate to interview. "
        "Use the analyst data you're given plus your own reading of the CV and JD. "
        "Respond ONLY with a single JSON object."
    )
    user = f"""Given the CV analysis and skills comparison below, produce a JSON object with EXACTLY these keys:
{{
  "compatibility_score": <integer 0-100>,
  "verdict": "<one of: 'Strong Match', 'Moderate Match', 'Weak Match'>",
  "reasoning": "<3-4 sentence explanation citing specifics>",
  "top_risks": ["<risk a recruiter would flag>", ...],
  "quick_wins": ["<change that would most improve the match this week>", ...]
}}

CV ANALYSIS (JSON): {json.dumps(cv_analysis)}
SKILLS COMPARISON (JSON): {json.dumps(skills)}

CV TEXT:
---
{cv_text}
---

JOB DESCRIPTION:
---
{jd_text}
---
"""

    def mock():
        return {
            "compatibility_score": 68,
            "verdict": "Moderate Match",
            "reasoning": "Mock mode: the candidate has strong Python fundamentals and a track "
            "record of shipping complete desktop applications, which shows initiative and "
            "end-to-end ownership. However, the role's emphasis on web backend frameworks and "
            "deployment tooling is not yet reflected in the CV, which will likely raise "
            "questions in early screening.",
            "top_risks": [
                "No visible backend web framework experience (Django/Flask/FastAPI)",
                "No deployment/CI-CD keywords for the ATS to match against",
            ],
            "quick_wins": [
                "Add a small REST API project to the CV, even a simple one.",
                "Mirror 2-3 exact keywords from the JD in the skills section.",
            ],
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Agent 4: Interview Agent
# --------------------------------------------------------------------------

def interview_agent(cv_text: str, jd_text: str, skills: dict) -> dict:
    system = (
        "You are a senior technical interviewer preparing a candidate for a real interview "
        "for this specific role. Questions must be realistic and tied to the JD and the "
        "candidate's actual background. Respond ONLY with a single JSON object."
    )
    user = f"""Produce a JSON object with EXACTLY these keys:
{{
  "questions": [
    {{
      "question": "<realistic interview question>",
      "type": "<one of: 'Technical', 'Behavioral', 'Situational'>",
      "personalized_answer_outline": "<a bullet-style outline of how THIS candidate, given their CV, should answer it>"
    }},
    ... (produce 6 questions total: 3 Technical, 2 Behavioral, 1 Situational)
  ]
}}

CV TEXT:
---
{cv_text}
---

JOB DESCRIPTION:
---
{jd_text}
---

KNOWN SKILL GAPS (JSON): {json.dumps(skills.get("missing_skills", []))}
"""

    def mock():
        return {
            "questions": [
                {
                    "question": "Walk me through how you'd structure a REST API for the "
                    "inventory system you built.",
                    "type": "Technical",
                    "personalized_answer_outline": "- Reference your existing Inventory "
                    "Management System's SQLite schema\n- Map CRUD operations to REST "
                    "endpoints (GET/POST/PUT/DELETE)\n- Mention you'd add this as a learning "
                    "project if not done yet",
                },
                {
                    "question": "What's the difference between SQLite and PostgreSQL, and "
                    "when would you choose one over the other?",
                    "type": "Technical",
                    "personalized_answer_outline": "- You've used SQLite extensively (password "
                    "manager, inventory system)\n- Explain SQLite is file-based/great for "
                    "single-user desktop apps\n- PostgreSQL for concurrent, networked, "
                    "production web apps",
                },
                {
                    "question": "How would you add unit tests to an existing untested "
                    "codebase?",
                    "type": "Technical",
                    "personalized_answer_outline": "- Point to your 42 unit tests on the "
                    "password manager as proof of testing discipline\n- Describe starting "
                    "with critical paths, then edge cases",
                },
                {
                    "question": "Tell me about a project where you had to learn something "
                    "completely new to finish it.",
                    "type": "Behavioral",
                    "personalized_answer_outline": "- Use the attendance/matplotlib charting "
                    "feature as an example of a new library learned on the job\n- Structure "
                    "as Situation-Task-Action-Result",
                },
                {
                    "question": "Describe a time you had to debug something difficult under "
                    "time pressure.",
                    "type": "Behavioral",
                    "personalized_answer_outline": "- Pick a bug from one of your Tkinter/"
                    "SQLite dual-storage projects (sync bugs are a natural source)\n- Emphasize "
                    "systematic debugging, not guessing",
                },
                {
                    "question": "If a client asked for a feature you knew was a bad idea "
                    "technically, what would you do?",
                    "type": "Situational",
                    "personalized_answer_outline": "- Show you'd explain trade-offs clearly, "
                    "propose an alternative, but ultimately respect the client's decision "
                    "if they insist",
                },
            ]
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Agent 5: Roadmap Agent
# --------------------------------------------------------------------------

def roadmap_agent(skills: dict, job_match: dict) -> dict:
    system = (
        "You are a pragmatic career coach building a short, realistic upskilling plan. "
        "Prioritize the skills that will most move the compatibility score. "
        "Respond ONLY with a single JSON object."
    )
    user = f"""Based on the missing skills and quick wins below, build a 4-week learning roadmap.
Return JSON with EXACTLY these keys:
{{
  "roadmap": [
    {{"week": 1, "focus": "<theme>", "tasks": ["<task>", "<task>"], "resource_hint": "<what kind of resource to look for, no need for real URLs>"}},
    ... (4 weeks total)
  ],
  "immediate_next_step": "<the single most important thing to do today>"
}}

MISSING SKILLS (JSON): {json.dumps(skills.get("missing_skills", []))}
QUICK WINS (JSON): {json.dumps(job_match.get("quick_wins", []))}
"""

    def mock():
        return {
            "roadmap": [
                {
                    "week": 1,
                    "focus": "Django/Flask fundamentals",
                    "tasks": [
                        "Build a basic CRUD app with Flask",
                        "Learn routing, templates, and request handling",
                    ],
                    "resource_hint": "An official Flask quickstart tutorial",
                },
                {
                    "week": 2,
                    "focus": "REST API design",
                    "tasks": [
                        "Convert your existing Inventory Management System into a REST API",
                        "Learn REST conventions and status codes",
                    ],
                    "resource_hint": "A REST API design guide or short course",
                },
                {
                    "week": 3,
                    "focus": "Databases at web scale",
                    "tasks": [
                        "Migrate a project from SQLite to PostgreSQL",
                        "Learn basic indexing and query optimization",
                    ],
                    "resource_hint": "A PostgreSQL-for-beginners tutorial",
                },
                {
                    "week": 4,
                    "focus": "Deployment & CI/CD",
                    "tasks": [
                        "Containerize one project with Docker",
                        "Set up a simple GitHub Actions workflow",
                    ],
                    "resource_hint": "A 'Docker for Python developers' guide",
                },
            ],
            "immediate_next_step": "Rebuild your Inventory Management System's backend as a "
            "small Flask REST API this week — it directly closes your biggest gap.",
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Agent 6: Cover Letter Agent
# --------------------------------------------------------------------------

def cover_letter_agent(cv_text: str, jd_text: str) -> dict:
    system = (
        "You are an expert cover letter writer. Write in first person, concise, specific, "
        "no generic filler, 250-350 words. Respond ONLY with a single JSON object."
    )
    user = f"""Write a personalized cover letter for this CV and JD.
Return JSON with EXACTLY this key:
{{"cover_letter": "<the full cover letter text, ready to send>"}}

CV TEXT:
---
{cv_text}
---

JOB DESCRIPTION:
---
{jd_text}
---
"""

    def mock():
        return {
            "cover_letter": (
                "Dear Hiring Manager,\n\n"
                "[MOCK MODE OUTPUT] I'm writing to apply for the Python Developer role. "
                "Over the past year I've shipped several complete Python applications — "
                "a Jazzy's Store mobile app built with Kivy and SQLite, a password manager "
                "with PBKDF2 encryption and 42 unit tests, and an inventory management "
                "system with a live KPI dashboard. Each project follows the same discipline: "
                "modular architecture, tested code, and clear documentation.\n\n"
                "I'm now focused on extending that foundation into web backend development, "
                "and I'm confident the same rigor I've applied to desktop applications will "
                "translate quickly to your stack.\n\n"
                "I'd welcome the chance to discuss how I can contribute to your team.\n\n"
                "Sincerely,\nJunaid"
            )
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Agent 7: LinkedIn Agent
# --------------------------------------------------------------------------

def linkedin_agent(cv_text: str) -> dict:
    system = (
        "You are a LinkedIn branding expert. Respond ONLY with a single JSON object."
    )
    user = f"""Based on this CV, return JSON with EXACTLY these keys:
{{
  "headline_options": ["<option 1>", "<option 2>", "<option 3>"],
  "about_section": "<a 4-6 sentence 'About' section for LinkedIn, first person>",
  "suggestions": ["<specific profile improvement>", ...]
}}

CV TEXT:
---
{cv_text}
---
"""

    def mock():
        return {
            "headline_options": [
                "Python Developer | Building Production-Ready Desktop & Mobile Apps",
                "Python Developer | SQLite, Tkinter, Kivy | Learning Web Backend",
                "Software Developer specializing in Python applications | Faisalabad, PK",
            ],
            "about_section": (
                "[MOCK MODE] I build complete, production-ready Python applications — from "
                "encrypted password managers to inventory systems with live dashboards. My "
                "focus is on modular architecture, tested code, and shipping things that "
                "actually work end to end. I'm currently expanding into web backend "
                "development to round out my skill set. Open to Python developer roles."
            ),
            "suggestions": [
                "Add your GitHub link to the Contact Info section.",
                "Post a short write-up of one project (e.g. the password manager) as a "
                "LinkedIn article to show depth.",
                "List each project individually in the 'Projects' section, not just in "
                "the About text.",
            ],
        }

    return call_llm_json(system, user, mock)


# --------------------------------------------------------------------------
# Career Manager Agent (orchestrator)
# --------------------------------------------------------------------------

def career_manager_pipeline(cv_text: str, jd_text: str, progress_cb=None) -> dict[str, Any]:
    """
    Runs the full agent pipeline in order, matching the architecture diagram.
    progress_cb(step_name: str) is called before each step, if provided —
    useful for driving a Streamlit progress bar.
    """

    def step(name: str, fn, *args):
        if progress_cb:
            progress_cb(name)
        return fn(*args)

    cv_analysis = step("Analyzing CV structure & ATS score", cv_analyzer_agent, cv_text)
    skills = step("Comparing skills against job description", skills_agent, cv_text, jd_text)
    job_match = step(
        "Scoring job compatibility", job_match_agent, cv_text, jd_text, cv_analysis, skills
    )
    interview = step("Generating interview questions", interview_agent, cv_text, jd_text, skills)
    roadmap = step("Building learning roadmap", roadmap_agent, skills, job_match)
    cover_letter = step("Drafting cover letter", cover_letter_agent, cv_text, jd_text)
    linkedin = step("Writing LinkedIn suggestions", linkedin_agent, cv_text)

    return {
        "cv_analysis": cv_analysis,
        "skills": skills,
        "job_match": job_match,
        "interview": interview,
        "roadmap": roadmap,
        "cover_letter": cover_letter,
        "linkedin": linkedin,
    }
