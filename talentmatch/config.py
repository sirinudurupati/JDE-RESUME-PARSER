"""Central configuration. Everything overridable through environment variables."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("TM_DATA_DIR", BASE_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "talentmatch.db"

HOST = os.environ.get("TM_HOST", "127.0.0.1")   # localhost only by default (no login system)
PORT = int(os.environ.get("TM_PORT", "8080"))

MAX_FILE_MB = int(os.environ.get("TM_MAX_FILE_MB", "10"))
MAX_FILES_PER_REQUEST = int(os.environ.get("TM_MAX_FILES_PER_REQUEST", "100"))
MAX_REQUEST_MB = int(os.environ.get("TM_MAX_REQUEST_MB", "400"))

RESUME_EXTS = {".pdf", ".docx"}
JDE_EXTS = {".pdf", ".docx", ".txt"}

# Default category weights (percent). HR can change them per job in the UI.
DEFAULT_WEIGHTS = {
    "skills": 40,
    "experience": 25,
    "education": 15,
    "responsibilities": 15,
    "certifications": 5,
}
# How much of each month counts toward RELEVANT experience, by employment type.
# 1.0 = counts fully, 0.5 = half, 0 = ignored. HR can change these per job.
DEFAULT_EXPERIENCE_COUNTING = {
    "full_time": 1.0,
    "part_time": 0.5,
    "internship": 0.5,
    "trainee": 1.0,
    "unknown": 1.0,      # type not stated on the resume; counted, but flagged as uncertain
}
EXPERIENCE_TYPE_LABELS = {
    "full_time": "Full-time", "part_time": "Part-time / freelance", "internship": "Internship",
    "trainee": "Trainee", "unknown": "Type not stated",
}
CATEGORY_LABELS = {
    "skills": "Skills",
    "experience": "Relevant experience",
    "education": "Education",
    "responsibilities": "Responsibilities",
    "certifications": "Certifications",
}


def normalize_weights(weights):
    """Return a clean weights dict. Missing/invalid -> defaults; values are
    clipped at >= 0. They are NOT rescaled here (scoring normalises over the
    categories that actually apply)."""
    out = {}
    for key, default in DEFAULT_WEIGHTS.items():
        try:
            v = float((weights or {}).get(key, default))
        except (TypeError, ValueError):
            v = float(default)
        out[key] = max(0.0, v)
    if sum(out.values()) <= 0:
        return dict(DEFAULT_WEIGHTS)
    return out
