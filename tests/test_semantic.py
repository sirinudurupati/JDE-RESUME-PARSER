from talentmatch import filestore, skills as sk
from talentmatch.scoring import score_responsibilities, _match_skill
from talentmatch.textutil import content_stems


def resume(text, skills=()):
    return {"text": text, "skills": {s: {"evidenced": True, "snippet": None} for s in skills}}


def test_synonym_words_share_a_concept():
    assert content_stems("supervised junior developers") & content_stems("lead a team of developers")
    assert content_stems("shipped the release to production") & content_stems("deployment of releases")
    assert content_stems("troubleshot outages") & content_stems("debug production issues")
    assert content_stems("server-side services") & content_stems("backend services")
    assert content_stems("unrelated gardening") & content_stems("backend services") == set()


def test_duty_covered_by_different_wording():
    job = {"responsibilities": ["Lead a team of backend developers and debug production incidents"]}
    text = "Supervised 5 server-side engineers. Troubleshot and resolved live outages."
    score, items = score_responsibilities(job, resume(text))
    assert items[0]["status"] == "covered" and score > 0.9


def test_skill_aliases_with_different_words():
    for phrase, canon in [("relational databases", "sql"), ("Dockerized services", "docker"),
                          ("deployment pipelines", "ci/cd"), ("amazon web services", "aws"),
                          ("analytical skills", "problem solving")]:
        assert canon in sk.find_skills(phrase), phrase
    r = resume("Built web APIs", skills=["rest api"])
    m = _match_skill({"name": "rest api", "level": "mandatory"}, r)
    assert m["status"] == "exact"


def test_local_filestore_roundtrip(client):
    filestore.init()
    filestore.put("a.pdf", b"abc")
    assert filestore.get("a.pdf") == b"abc"
    assert filestore.get("../evil") is None
    filestore.delete("a.pdf")
    assert filestore.get("a.pdf") is None


def test_supabase_filestore_uses_storage_api(monkeypatch):
    calls = []

    class Resp:
        def __init__(self, body=b"data"): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=0):
        calls.append((req.get_method(), req.full_url, req.get_header("Authorization")))
        return Resp()

    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co/")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "KEY")
    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    filestore.put("r.pdf", b"1")
    assert filestore.get("r.pdf") == b"data"
    filestore.delete("r.pdf")
    assert calls == [("POST", "https://x.supabase.co/storage/v1/object/resumes/r.pdf", "Bearer KEY"),
                     ("GET", "https://x.supabase.co/storage/v1/object/resumes/r.pdf", "Bearer KEY"),
                     ("DELETE", "https://x.supabase.co/storage/v1/object/resumes/r.pdf", "Bearer KEY")]


def test_postgres_connection_rewrites_placeholders():
    from talentmatch.storage import _PgConn

    class Cur:
        def fetchone(self): return {"id": 7}

    class Conn:
        def execute(self, sql, params=()):
            self.sql = sql
            return Cur()

    raw = Conn()
    assert _PgConn(raw).insert("INSERT INTO jobs(a,b) VALUES(?,?)", (1, 2)) == 7
    assert raw.sql == "INSERT INTO jobs(a,b) VALUES(%s,%s) RETURNING id"
