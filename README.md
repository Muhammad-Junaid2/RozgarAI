# RozgarAI — AI Career & Job Application Agent

An agentic AI system that takes a **CV + Job Description** and produces:
- ATS score with reasoning
- Matching / missing skills
- Job compatibility verdict
- Personalized interview questions + answer outlines
- A 4-week learning roadmap
- A tailored cover letter
- LinkedIn headline / about / suggestions

## Architecture

```
CV + Job Description
        ↓
  Career Manager Agent (orchestrator)
        ↓
  ┌─────────────┬──────────────┬───────────────┐
  CV Analyzer    Skills Agent    Job Match Agent
  ┌─────────────┴──────────────┴───────────────┐
        ↓
  Interview Agent
        ↓
  Roadmap Agent / Cover Letter Agent / LinkedIn Agent
        ↓
  Streamlit UI (tabs)
```

Each agent is a focused function in `agents.py` that calls the Gemini API with
a strict JSON-only prompt. The `career_manager_pipeline()` function is the
orchestrator that runs them in order and threads context between them.

## Files

- `app.py` — Streamlit UI
- `agents.py` — the 7 agents + orchestrator + Gemini wrapper
- `cv_utils.py` — PDF/DOCX/TXT text extraction
- `test_pipeline.py` — offline test suite (mock mode, no API key needed)
- `sample_data/` — sample CV + JD for testing
- `requirements.txt`, `.env.example`, `.gitignore`

## Local setup

```bash
git clone <your-repo-url>
cd rozgarai
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Get a free Gemini API key: https://aistudio.google.com/app/apikey

Either export it as an environment variable:
```bash
export GEMINI_API_KEY=your_key_here      # Windows: set GEMINI_API_KEY=your_key_here
```
or just paste it into the sidebar field when the app is running — either works.

Run:
```bash
streamlit run app.py
```

**No API key?** The app still runs in **MOCK MODE** with canned demo data so
you can try the full flow before spending any API credits.

## Running the test suite

```bash
python test_pipeline.py
```

This runs the whole 7-agent pipeline in mock mode and validates every
expected field is present, plus tests real PDF/DOCX/TXT extraction. No API
key or network access required — good to run before every push.

---

## Pushing to GitHub using the web UI (no terminal git needed)

1. Go to https://github.com and log in. Click the **+** icon (top right) →
   **New repository**.
2. Name it `rozgarai`, set it to Public (or Private), do **not** initialize
   with a README (you already have one), then click **Create repository**.
3. On the empty repo's page, click **uploading an existing file** (a link in
   the "Quick setup" box).
4. Drag and drop all your project files (`app.py`, `agents.py`, `cv_utils.py`,
   `requirements.txt`, `README.md`, `.gitignore`, `.env.example`,
   `sample_data/` folder, `test_pipeline.py`) into the upload area.
   - **Do NOT upload a `.env` file with your real API key.** The
     `.gitignore` protects you if you ever use terminal git, but the web
     uploader has no such protection — just don't drag `.env` in.
5. Scroll down, write a commit message like "Initial commit — RozgarAI", and
   click **Commit changes**.
6. Your code is now live at `https://github.com/<your-username>/rozgarai`.

**To update it later** (e.g. after fixing a bug):
1. Open the file on GitHub → click the pencil (✏️) icon to edit in-browser,
   **or** go to the repo's main page → **Add file → Upload files** to
   replace/add files.
2. Commit the change with a short message.

## Deploying on Streamlit Community Cloud

1. Go to https://share.streamlit.io and log in with your GitHub account.
2. Click **Create app** → **From existing repo**.
3. Select your `rozgarai` repository, branch `main`, and set the main file
   path to `app.py`.
4. Click **Advanced settings** → under **Secrets**, add:
   ```
   GEMINI_API_KEY = "your_key_here"
   ```
   This keeps your key out of the public repo entirely.
5. Click **Deploy**. Streamlit will install `requirements.txt` automatically
   and give you a public URL like `https://rozgarai-yourname.streamlit.app`.
6. Any time you push/upload new commits to the GitHub repo, the deployed app
   auto-redeploys.

That's it — you now have a live, shareable demo link for the hackathon.
