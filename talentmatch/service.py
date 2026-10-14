"""Orchestration: ingest files, run matching, keep results in sync with the job."""
import hashlib
import os
import uuid
from pathlib import Path

from . import config, storage
from .extract import ExtractionError, extract_text, inspect_file
from .jde_parser import parse_jde
from .resume_parser import parse_resume
from .scoring import score_candidate


def _ext(filename):
    return os.path.splitext(filename or "")[1].lower()


def safe_display_name(filename):
    return os.path.basename((filename or "file").replace("\\", "/"))[:150] or "file"


# --------------------------------------------------------------- jobs
def create_job_from_upload(filename, data):
    """-> (job_id, requirements). Raises ExtractionError on bad files."""
    text = extract_text(data, _ext(filename), config.JDE_EXTS)
    req = parse_jde(text)
    title = req["title"] or Path(safe_display_name(filename)).stem
    req["raw_text"] = text[:60000]
    job_id = storage.create_job(title, req, dict(config.DEFAULT_WEIGHTS), safe_display_name(filename))
    return job_id, req


def clean_requirements(payload: dict, previous: dict) -> dict:
    """Validate the HR-edited requirements. Unknown keys are dropped."""
    from . import skills as sk

    def s(v, n=200):
        return str(v or "").strip()[:n]

    skills, seen = [], set()
    import re
    gno = 0
    for item in payload.get("skills", []):
        raw = s(item.get("name"), 160).lower()
        level = "preferred" if item.get("level") == "preferred" else "mandatory"
        # "sql or mysql or postgresql" = alternatives: any ONE satisfies the requirement
        parts = [p.strip() for p in re.split(r"\s+or\s+", raw) if p.strip()]
        group = None
        if len(parts) > 1:
            gno += 1
            group = f"g{gno}"
        for name in parts:
            name = name[:80]
            if name in seen:
                continue
            seen.add(name)
            canon = sk.canonical(name)
            name = canon or name
            skills.append({"name": name, "display": sk.display(name) if canon else name,
                           "level": level, "confidence": "high", "group": group})
    years = payload.get("min_experience_years")
    try:
        years = float(years) if years not in (None, "") else None
        if years is not None and not (0 <= years <= 60):
            years = None
        if years == 0:
            years = None
    except (TypeError, ValueError):
        years = None
    try:
        max_years = float(payload.get("max_experience_years")) if payload.get("max_experience_years") not in (None, "") else None
        if max_years is not None and (years is None or max_years <= years or max_years > 60):
            max_years = None
    except (TypeError, ValueError):
        max_years = None
    rules = {}
    given = payload.get("experience_counting") or {}
    for k, default in config.DEFAULT_EXPERIENCE_COUNTING.items():
        try:
            rules[k] = min(1.0, max(0.0, float(given.get(k, default))))
        except (TypeError, ValueError):
            rules[k] = default
    edu = payload.get("education")
    education = None
    if edu and edu.get("min_level"):
        lvl = int(edu["min_level"])
        if lvl in (1, 2, 3, 4):
            education = {"min_level": lvl, "mandatory": bool(edu.get("mandatory", True)),
                         "field": s(edu.get("field"), 80) or None}
    certs = [{"name": s(c.get("name"), 100), "mandatory": bool(c.get("mandatory"))}
             for c in payload.get("certifications", []) if s(c.get("name"), 100)]
    return {
        "title": s(payload.get("title"), 120),
        "department": s(payload.get("department"), 120),
        "responsibilities": [s(r, 300) for r in payload.get("responsibilities", []) if s(r, 300)][:60],
        "skills": skills[:80],
        "min_experience_years": years,
        "max_experience_years": max_years,
        "experience_counting": rules,
        "experience_mandatory": bool(payload.get("experience_mandatory", True)),
        "education": education,
        "certifications": certs[:30],
        "flags": [],
        "raw_text": previous.get("raw_text", ""),
    }


# --------------------------------------------------------- candidates
def ingest_resume(job_id, filename, data):
    """Parse + store + score one resume. Returns a status dict (never raises)."""
    display = safe_display_name(filename)
    if len(data) > config.MAX_FILE_MB * 1024 * 1024:
        return {"filename": display, "status": "error",
                "message": f"File larger than {config.MAX_FILE_MB} MB."}
    try:
        text = extract_text(data, _ext(filename), config.RESUME_EXTS)
    except ExtractionError as e:
        return {"filename": display, "status": "error", "message": str(e)}
    except Exception:
        return {"filename": display, "status": "error", "message": "Could not read this file."}
    digest = hashlib.sha256(data).hexdigest()
    dup = storage.find_by_hash(job_id, digest)
    if dup:
        return {"filename": display, "status": "duplicate",
                "message": f"Identical file already uploaded as '{dup['filename']}'."}
    try:
        parsed = parse_resume(text)
        parsed["file_info"] = inspect_file(data, _ext(filename))
    except Exception:
        return {"filename": display, "status": "error", "message": "Resume could not be parsed."}
    note = None
    same = storage.find_by_email(job_id, parsed.get("email"))
    if same:
        note = f"Same email as existing candidate '{same['name'] or same['filename']}' - possible duplicate."
        parsed["flags"] = parsed.get("flags", []) + [note]
    stored = uuid.uuid4().hex + _ext(filename)
    (config.UPLOAD_DIR / stored).write_bytes(data)
    cid = storage.add_candidate(job_id, parsed, display, stored, digest)
    job = storage.get_job(job_id)
    result = score_candidate(job["requirements"], job["weights"], parsed)
    if note:
        result["needs_review"] = True
        result["review_reasons"].append("Possible duplicate (same email)")
    storage.save_result(cid, job_id, job["version"], result)
    return {"filename": display, "status": "ok", "candidate_id": cid,
            "name": parsed.get("name"), "overall": result["overall"], "message": note}


def rematch_job(job_id):
    job = storage.get_job(job_id)
    if not job:
        return 0
    n = 0
    for c in storage.list_candidates(job_id, full=True):
        old = c["parsed"]
        dup_flags = [f for f in old.get("flags", []) if "possible duplicate" in f.lower()]
        text = old["text"]
        file_info = old.get("file_info")
        try:                         # re-read the saved file so reader improvements apply too
            path = config.UPLOAD_DIR / c["stored_name"]
            if path.exists():
                raw = path.read_bytes()
                text = extract_text(raw, path.suffix, config.RESUME_EXTS)
                file_info = inspect_file(raw, path.suffix)
        except Exception:
            text = old["text"]
        try:                         # re-parse so parser improvements apply to saved resumes too
            parsed = parse_resume(text)
            parsed["file_info"] = file_info
            parsed["flags"] = parsed.get("flags", []) + dup_flags
            storage.update_parsed(c["id"], parsed)
        except Exception:
            parsed = old
        result = score_candidate(job["requirements"], job["weights"], parsed)
        if dup_flags:
            result["needs_review"] = True
            result["review_reasons"].append("Possible duplicate (same email)")
        storage.save_result(c["id"], job_id, job["version"], result)
        n += 1
    return n


def remove_file(stored_name):
    if not stored_name:
        return
    p = (config.UPLOAD_DIR / stored_name).resolve()
    if config.UPLOAD_DIR.resolve() in p.parents and p.exists():
        p.unlink()
