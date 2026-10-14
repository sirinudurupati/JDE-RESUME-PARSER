"""SQLite persistence (stdlib only). One short-lived connection per call."""
import json
import sqlite3
import time
from contextlib import contextmanager

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,
  requirements TEXT NOT NULL,
  weights TEXT NOT NULL,
  source_name TEXT,
  reviewed INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created REAL NOT NULL,
  updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  name TEXT, email TEXT, phone TEXT,
  filename TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  parsed TEXT NOT NULL,
  created REAL NOT NULL,
  UNIQUE(job_id, file_hash)
);
CREATE TABLE IF NOT EXISTS results(
  candidate_id INTEGER PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
  job_id INTEGER NOT NULL,
  job_version INTEGER NOT NULL,
  overall REAL NOT NULL,
  detail TEXT NOT NULL,
  matched_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cand_job ON candidates(job_id);
"""


@contextmanager
def db():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init():
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript(SCHEMA)


# ----------------------------------------------------------------- jobs
def _job(row, with_counts=None):
    d = {"id": row["id"], "title": row["title"], "requirements": json.loads(row["requirements"]),
         "weights": json.loads(row["weights"]), "source_name": row["source_name"],
         "reviewed": bool(row["reviewed"]), "version": row["version"],
         "created": row["created"], "updated": row["updated"]}
    return d


def create_job(title, requirements, weights, source_name):
    now = time.time()
    with db() as c:
        cur = c.execute(
            "INSERT INTO jobs(title,requirements,weights,source_name,reviewed,version,created,updated)"
            " VALUES(?,?,?,?,0,1,?,?)",
            (title, json.dumps(requirements), json.dumps(weights), source_name, now, now))
        return cur.lastrowid


def get_job(job_id):
    with db() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return _job(row) if row else None


def list_jobs():
    with db() as c:
        rows = c.execute(
            "SELECT j.*, (SELECT COUNT(*) FROM candidates WHERE job_id=j.id) AS n "
            "FROM jobs j ORDER BY j.updated DESC").fetchall()
    out = []
    for r in rows:
        j = _job(r)
        j["candidate_count"] = r["n"]
        out.append(j)
    return out


def update_job(job_id, title, requirements, weights):
    with db() as c:
        c.execute("UPDATE jobs SET title=?, requirements=?, weights=?, reviewed=1, "
                  "version=version+1, updated=? WHERE id=?",
                  (title, json.dumps(requirements), json.dumps(weights), time.time(), job_id))


def delete_job(job_id):
    """Returns stored file names that the caller must delete from disk."""
    with db() as c:
        names = [r["stored_name"] for r in
                 c.execute("SELECT stored_name FROM candidates WHERE job_id=?", (job_id,))]
        c.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return names


# ----------------------------------------------------------- candidates
def add_candidate(job_id, parsed, filename, stored_name, file_hash):
    with db() as c:
        cur = c.execute(
            "INSERT INTO candidates(job_id,name,email,phone,filename,stored_name,file_hash,parsed,created)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, parsed.get("name"), parsed.get("email"), parsed.get("phone"), filename,
             stored_name, file_hash, json.dumps(parsed), time.time()))
        return cur.lastrowid


def update_parsed(cid, parsed):
    with db() as c:
        c.execute("UPDATE candidates SET name=?, email=?, phone=?, parsed=? WHERE id=?",
                  (parsed.get("name"), parsed.get("email"), parsed.get("phone"), json.dumps(parsed), cid))


def find_by_hash(job_id, file_hash):
    with db() as c:
        r = c.execute("SELECT id, filename FROM candidates WHERE job_id=? AND file_hash=?",
                      (job_id, file_hash)).fetchone()
    return dict(r) if r else None


def find_by_email(job_id, email):
    if not email:
        return None
    with db() as c:
        r = c.execute("SELECT id, name, filename FROM candidates WHERE job_id=? AND email=?",
                      (job_id, email)).fetchone()
    return dict(r) if r else None


def get_candidate(cid):
    with db() as c:
        r = c.execute("SELECT c.*, r.overall, r.detail, r.job_version FROM candidates c "
                      "LEFT JOIN results r ON r.candidate_id=c.id WHERE c.id=?", (cid,)).fetchone()
    return _cand(r, full=True) if r else None


def _cand(r, full=False):
    d = {"id": r["id"], "job_id": r["job_id"], "name": r["name"], "email": r["email"],
         "phone": r["phone"], "filename": r["filename"], "created": r["created"],
         "stored_name": r["stored_name"],
         "overall": r["overall"], "job_version": r["job_version"],
         "result": json.loads(r["detail"]) if r["detail"] else None}
    if full:
        d["parsed"] = json.loads(r["parsed"])
    return d


def list_candidates(job_id, full=False):
    with db() as c:
        rows = c.execute("SELECT c.*, r.overall, r.detail, r.job_version FROM candidates c "
                         "LEFT JOIN results r ON r.candidate_id=c.id WHERE c.job_id=? "
                         "ORDER BY COALESCE(r.overall,-1) DESC, c.id", (job_id,)).fetchall()
    return [_cand(r, full=full) for r in rows]


def save_result(candidate_id, job_id, job_version, result):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO results(candidate_id,job_id,job_version,overall,detail,matched_at)"
                  " VALUES(?,?,?,?,?,?)",
                  (candidate_id, job_id, job_version, result["overall"], json.dumps(result), time.time()))


def delete_candidate(cid):
    with db() as c:
        r = c.execute("SELECT stored_name FROM candidates WHERE id=?", (cid,)).fetchone()
        if not r:
            return None
        c.execute("DELETE FROM candidates WHERE id=?", (cid,))
    return r["stored_name"]


def counts():
    with db() as c:
        j = c.execute("SELECT COUNT(*) n FROM jobs").fetchone()["n"]
        a = c.execute("SELECT COUNT(*) n FROM candidates").fetchone()["n"]
    return {"jobs": j, "applicants": a}
