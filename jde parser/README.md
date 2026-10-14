# siuru TalentMatch — JDE parser & resume matching

*Your idea finds life here.*

## Run
    pip install -r requirements.txt
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
