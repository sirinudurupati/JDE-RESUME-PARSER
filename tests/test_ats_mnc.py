from conftest import make_pdf
from talentmatch.ats_mnc import mnc_report
from talentmatch.extract import inspect_file
from talentmatch.resume_parser import parse_resume
from talentmatch.scoring import score_candidate
from talentmatch.config import DEFAULT_WEIGHTS

JOB = {"title": "Python Developer", "responsibilities": [],
       "skills": [{"name": "python", "level": "mandatory"}, {"name": "sql", "level": "mandatory"},
                  {"name": "fastapi", "level": "preferred"}, {"name": "docker", "level": "preferred"}],
       "min_experience_years": 1, "experience_mandatory": True,
       "education": {"min_level": 2, "mandatory": True}, "certifications": []}

GOOD = """Jane Roe
jane@example.com | +91 98765 43210
EXPERIENCE
Python Developer
Acme Technologies Pvt Ltd
Jan 2024 - Dec 2024
- Built Python APIs with SQL and FastAPI and cut latency by 30%
Software Intern
Beta Labs
Jan 2023 - Dec 2023
- Wrote Python scripts
EDUCATION
B.Tech in Computer Science, ABC University 2019 - 2023
SKILLS
Python, SQL, FastAPI, Docker
"""


def run(text, job=JOB, with_file=True):
    p = parse_resume(text)
    if with_file:
        p["file_info"] = inspect_file(make_pdf(text), ".pdf")
    return score_candidate(job, DEFAULT_WEIGHTS, p)


def test_score_is_parse_half_plus_keyword_half():
    m = run(GOOD)["ats_mnc"]
    assert 0 <= m["score"] <= 100
    assert abs(m["score"] - (m["parse_score"] + m["keyword_score"])) < 0.2
    assert m["parse_score"] <= 50 and m["keyword_score"] <= 50
    assert m["keyword_score"] == 50 and m["band"] == "Likely to pass" and m["knockouts"] == []


def test_missing_keywords_lower_score_even_when_resume_is_clean():
    other = GOOD.replace("Python", "Java").replace("SQL", "Oracle").replace("FastAPI", "Spring").replace("Docker", "Maven")
    a, b = run(GOOD)["ats_mnc"], run(other)["ats_mnc"]
    assert abs(a["parse_score"] - b["parse_score"]) < 3         # same clean layout
    assert b["keyword_score"] < a["keyword_score"] and b["score"] < a["score"]
    assert any("Mandatory keyword" in k for k in b["knockouts"])


def test_related_skill_does_not_count_as_keyword():
    job = dict(JOB, skills=[{"name": "fastapi", "level": "mandatory"}])
    m = run(GOOD.replace("FastAPI", "Flask"), job)["ats_mnc"]
    kw = m["keywords"][0]
    assert kw["found"] is False and kw["related_only"] is True and m["keyword_score"] == 0


def test_mandatory_keywords_weigh_double():
    job = dict(JOB, skills=[{"name": "python", "level": "mandatory"}, {"name": "docker", "level": "preferred"}])
    only_pref_missing = run(GOOD.replace("Docker", "Maven"), job)["ats_mnc"]["keyword_score"]
    only_mand_missing = run(GOOD.replace("Python", "Java"), job)["ats_mnc"]["keyword_score"]
    assert round(only_pref_missing, 1) == 33.3 and only_mand_missing == 16.7


def test_na_checks_not_given_full_marks_and_fresher_ok():
    fresher = "Jane Roe\njane@example.com | +91 98765 43210\nEDUCATION\nB.Tech Computer Science 2024\nSKILLS\nPython, SQL\n"
    m = run(fresher)["ats_mnc"]
    keys = {c["key"]: c for c in m["checks"]}
    assert keys["workhist"]["status"] == "na" and keys["chrono"]["status"] == "na"
    assert m["parse_score"] > 35                                  # a fresher is not punished for having no jobs


def test_no_job_keywords_scores_parsing_only_and_says_so():
    job = dict(JOB, skills=[])
    m = run(GOOD, job)["ats_mnc"]
    assert m["keyword_score"] is None and 0 < m["score"] <= 100


def test_parse_failures_reduce_parse_score():
    messy = "Jane\nMy Journey\nWorked at a place for a while doing stuff\nSchool: somewhere\n"
    m = run(messy)["ats_mnc"]
    assert m["parse_score"] < 25 and m["band"] == "At risk"


def test_reverse_chronological_check():
    oldest_first = GOOD.replace(
        "Python Developer\nAcme Technologies Pvt Ltd\nJan 2024 - Dec 2024\n- Built Python APIs with SQL and FastAPI and cut latency by 30%\n"
        "Software Intern\nBeta Labs\nJan 2023 - Dec 2023\n- Wrote Python scripts\n",
        "Software Intern\nBeta Labs\nJan 2023 - Dec 2023\n- Wrote Python scripts\n"
        "Python Developer\nAcme Technologies Pvt Ltd\nJan 2024 - Dec 2024\n- Built Python APIs with SQL and FastAPI and cut latency by 30%\n")
    keys = {c["key"]: c for c in run(oldest_first)["ats_mnc"]["checks"]}
    assert keys["chrono"]["status"] == "fail"
    assert {c["key"]: c for c in run(GOOD)["ats_mnc"]["checks"]}["chrono"]["status"] == "pass"


def test_deterministic_and_present_for_every_candidate():
    assert run(GOOD)["ats_mnc"] == run(GOOD)["ats_mnc"]
    assert mnc_report(parse_resume(GOOD))["score"] >= 0
