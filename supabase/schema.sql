-- Optional: the app creates these automatically on first start.
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
