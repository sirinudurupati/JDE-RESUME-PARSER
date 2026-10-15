# siuru TalentMatch — JDE parser & resume matching

*Your idea finds life here.*

## Run
    pip install -r requirements.txt   # includes pdfplumber (PDF reading) and pypdf (fallback)
    python app.py            # http://localhost:8080
    python -m pytest -q      # tests

## Use
1. **Upload JDE** (PDF/DOCX/TXT) -> review/edit the extracted requirements and weights -> Save.
2. **Upload resumes** (PDF/DOCX; drop 50-100+ at once, or pick a folder). Sent in batches of 10 with progress.
3. Review the ranked table; open **Details** for the explanation; export CSV/Excel.

## Scoring
overall = 100 x sum(weight_i x score_i) / sum(weight_i), over categories that apply.
Defaults: skills 40, experience 25, education 15, responsibilities 15, certifications 5.
Change per job in "Review job requirements" (any totals are rescaled). Categories the job doesn't define
are excluded and shown as "not scored"; missing resume evidence scores 0 and is flagged.

## Config (env vars)
TM_PORT (8080), TM_HOST (127.0.0.1), TM_DATA_DIR, TM_MAX_FILE_MB (10), TM_MAX_FILES_PER_REQUEST (100).
Data (SQLite + uploaded files) lives in `data/`. No resume text leaves the machine; no external AI is used.
There is no login: keep it on localhost or put it behind your own authentication.

## ATS score
Every candidate also gets an **ATS score (0-100)**: how reliably an Applicant Tracking System can *read* the
resume (separate from the job-match score). It is an explainable checklist: readable text 15, contact details 15,
standard section headings 20, clear dates 10, single column 8, no tables 6, no text boxes/graphics 3,
contact not in header 3, clean characters 10, length 5, measurable results 5. Bands: 80+ Good, 60-79 Fair, <60 Poor.
Checks that can't be assessed (original file missing) are left out, not given full marks.
Each ATS is proprietary, so this is an estimate of parse-friendliness, not a copy of any one product.

### ATS score - MNC / enterprise model (the one shown in the table)
score = 50 x parsing quality + 50 x exact keyword match with the job.
Parsing (50): text 5, contact 6, headings 8, single column 4, no tables 3, no text boxes/header contact 3,
no photo/icons 4, each job parsed into company+title+dates 8, degree+year 4, newest-first 3, month+year dates 3, 1-2 pages 2.
Keywords (50): mandatory x2, preferred x1; only exact/equivalent terms count (a "related" skill does not match in an ATS).
Bands: 75+ Likely to pass, 55-74 Borderline, <55 At risk. "Knockout risks" list hard requirements an enterprise ATS
may auto-filter on (missing mandatory keyword/certification, experience or education below minimum) - warnings only.
Not-applicable checks (e.g. no work history for a fresher) are left out, not penalised.
The earlier plain readability score is still shown in the details.

## Deploying with Supabase
Supabase provides the **database (Postgres) and file storage**; it cannot run a Flask server, so the app itself runs on
a web host (Render's free plan is enough - no disk needed) and keeps all data in your Supabase project.

1. Create a Supabase project. Copy **Project Settings > Database > Connection string** (the *Transaction pooler* URI,
   port 6543) into `DATABASE_URL`, and **Project Settings > API** `Project URL` / `service_role` key into
   `SUPABASE_URL` / `SUPABASE_SERVICE_KEY`. Never put the service key in the repo or the browser.
2. Tables are created automatically on first start (row-level security is on, so the public API key can't read
   candidates). The private `resumes` bucket is created automatically too (`SUPABASE_BUCKET` to rename it).
   [supabase/schema.sql](supabase/schema.sql) is the same SQL if you prefer to run it yourself.
3. **Render:** New + > Blueprint > choose the repo/branch; enter `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
   and `TM_PASSWORD`. **Railway:** same variables plus `TM_ENV=production`.

| Variable | Value |
|---|---|
| `TM_ENV` | `production` (the app refuses to start without `TM_PASSWORD`) |
| `TM_PASSWORD` | the login password (user name is `TM_USER`, default `hr`) |
| `DATABASE_URL` | Supabase Postgres URI. Unset -> local SQLite in `TM_DATA_DIR` |
| `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` | resumes go to Supabase Storage. Unset -> local `TM_DATA_DIR/uploads` |

Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 180` (also in `Procfile`).
Health check: `/healthz`. Not Vercel: its 4.5 MB request limit is too small for resume batches.
Development/tests: `pip install -r requirements-dev.txt`.
