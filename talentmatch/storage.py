"""Persistence. SQLite by default (stdlib only); Postgres (e.g. Supabase) when DATABASE_URL is set.

Queries are written once with `?` placeholders; the Postgres path rewrites them to `%s`.
One short-lived connection per call."""
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

# Same tables for Postgres. RLS is switched on with no policies so that Supabase's public API
# (anon key) can never read candidate data; the app connects as the table owner, which bypasses RLS.
PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs(
  id BIGSERIAL PRIMARY KEY,
  title TEXT NOT NULL,
  requirements TEXT NOT NULL,
  weights TEXT NOT NULL,
  source_name TEXT,
  reviewed INTEGER NOT NULL DEFAULT 0,
  version INTEGER NOT NULL DEFAULT 1,
  created DOUBLE PRECISION NOT NULL,
  updated DOUBLE PRECISION NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates(
  id BIGSERIAL PRIMARY KEY,
  job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
  name TEXT, email TEXT, phone TEXT,
  filename TEXT NOT NULL,
  stored_name TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  parsed TEXT NOT NULL,
  created DOUBLE PRECISION NOT NULL,
  UNIQUE(job_id, file_hash)
);
CREATE TABLE IF NOT EXISTS results(
  candidate_id BIGINT PRIMARY KEY REFERENCES candidates(id) ON DELETE CASCADE,
  job_id BIGINT NOT NULL,
  job_version INTEGER NOT NULL,
  overall DOUBLE PRECISION NOT NULL,
  detail TEXT NOT NULL,
  matched_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cand_job ON candidates(job_id);
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE results ENABLE ROW LEVEL SECURITY;
"""


class _PgConn:
    """Gives a psycopg connection the tiny slice of the sqlite3 API this module uses."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql.replace("?", "%s"), params)

    def insert(self, sql, params):
        return self.execute(sql + " RETURNING id", params).fetchone()["id"]


class _LiteConn:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def insert(self, sql, params):
        return self.conn.execute(sql, params).lastrowid


@contextmanager
def db():
    url = config.database_url()
    if url:
        import psycopg
        from psycopg.rows import dict_row
        # prepare_threshold=None: Supabase's pooler (transaction mode) rejects prepared statements
        conn = psycopg.connect(url, row_factory=dict_row, prepare_threshold=None, connect_timeout=15)
        try:
            yield _PgConn(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield _LiteConn(conn)
        conn.commit()
    finally:
        conn.close()


def init():
    from . import filestore
    filestore.init()
    with db() as c:
        if config.database_url():
            for stmt in PG_SCHEMA.split(";"):
                if stmt.strip():
                    c.execute(stmt)
        else:
            c.conn.executescript(SCHEMA)


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
        return c.insert(
            "INSERT INTO jobs(title,requirements,weights,source_name,reviewed,version,created,updated)"
            " VALUES(?,?,?,?,0,1,?,?)",
            (title, json.dumps(requirements), json.dumps(weights), source_name, now, now))


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
        return c.insert(
            "INSERT INTO candidates(job_id,name,email,phone,filename,stored_name,file_hash,parsed,created)"
            " VALUES(?,?,?,?,?,?,?,?,?)",
            (job_id, parsed.get("name"), parsed.get("email"), parsed.get("phone"), filename,
             stored_name, file_hash, json.dumps(parsed), time.time()))


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
        c.execute("INSERT INTO results(candidate_id,job_id,job_version,overall,detail,matched_at)"
                  " VALUES(?,?,?,?,?,?) ON CONFLICT(candidate_id) DO UPDATE SET job_id=excluded.job_id,"
                  " job_version=excluded.job_version, overall=excluded.overall, detail=excluded.detail,"
                  " matched_at=excluded.matched_at",
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
        j = c.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"]
        a = c.execute("SELECT COUNT(*) AS n FROM candidates").fetchone()["n"]
        d = c.execute("SELECT COUNT(DISTINCT file_hash) AS n FROM candidates").fetchone()["n"]
    return {"jobs": j, "applicants": a, "distinct_resumes": d}


def pool_candidates(exclude_job_id):
    """One record per distinct resume file (newest copy) held by jobs other than `exclude_job_id`."""
    with db() as c:
        rows = c.execute(
            "SELECT * FROM candidates WHERE job_id != ? AND id IN "
            "(SELECT MAX(id) FROM candidates GROUP BY file_hash) ORDER BY id", (exclude_job_id,)).fetchall()
    return [dict(r) for r in rows]
