import pytest

from talentmatch.extract import ExtractionError, extract_text
from talentmatch.jde_parser import parse_jde
from talentmatch.resume_parser import parse_resume

from conftest import make_docx, make_pdf


def test_jde_fields(jd_text):
    r = parse_jde(jd_text)
    assert r["title"] == "Python Developer"
    assert r["department"] == "Engineering"
    mand = {s["name"] for s in r["skills"] if s["level"] == "mandatory"}
    pref = {s["name"] for s in r["skills"] if s["level"] == "preferred"}
    assert {"python", "sql", "fastapi", "git"} <= mand
    assert {"docker", "redis", "aws"} <= pref
    assert r["min_experience_years"] == 2
    assert r["education"]["min_level"] == 2 and r["education"]["mandatory"]
    assert r["certifications"][0]["name"].startswith("AWS Certified")
    assert len(r["responsibilities"]) == 4


def test_jde_flags_instead_of_inventing():
    r = parse_jde("Marketing Associate\nWe are a friendly team that likes cake and coffee every day.")
    assert r["min_experience_years"] is None
    assert r["education"] is None
    assert r["skills"] == []
    assert r["flags"]


def test_jde_number_words_and_preferred_experience():
    r = parse_jde("Job Title: Dev\nRequirements:\n- Two years of experience with Java\n")
    assert r["min_experience_years"] == 2


def test_resume_contact_and_name(resume_a):
    p = parse_resume(resume_a)
    assert p["name"] == "Aarav Mehta"
    assert p["email"] == "aarav.mehta@example.com"
    assert p["phone"].startswith("+91")
    assert p["education"]["highest_rank"] == 2
    assert p["total_months"] == 34


def test_extract_roundtrip_pdf_docx(jd_text):
    for ext, data in ((".pdf", make_pdf(jd_text)), (".docx", make_docx(jd_text)), (".txt", jd_text.encode())):
        t = extract_text(data, ext, {".pdf", ".docx", ".txt"})
        assert "Python Developer" in t


def test_extract_errors():
    allowed = {".pdf", ".docx"}
    with pytest.raises(ExtractionError):
        extract_text(b"not a pdf at all", ".pdf", allowed)
    with pytest.raises(ExtractionError):
        extract_text(b"PK\x03\x04garbage", ".docx", allowed)
    with pytest.raises(ExtractionError):
        extract_text(b"", ".pdf", allowed)
    with pytest.raises(ExtractionError):
        extract_text(b"hello", ".exe", allowed)
    with pytest.raises(ExtractionError):
        extract_text(make_pdf("hi"), ".pdf", allowed)      # too little text
