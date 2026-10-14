"""Work-experience evaluation: total vs relevant, overlaps, types, uncertainty."""
from datetime import date

import pytest

from talentmatch.config import DEFAULT_WEIGHTS
from talentmatch.jde_parser import parse_jde
from talentmatch.resume_parser import parse_resume
from talentmatch.scoring import evaluate_experience, score_candidate

TODAY = date(2026, 6, 1)

JOB = {"title": "Python Developer", "responsibilities": ["Backend development of REST APIs"],
       "skills": [{"name": "python", "level": "mandatory"}, {"name": "fastapi", "level": "preferred"},
                  {"name": "sql", "level": "preferred"}, {"name": "rest api", "level": "preferred"}],
       "min_experience_years": 3, "experience_mandatory": True, "education": None, "certifications": []}

PROFILE_EXAMPLE = """Jane Roe
jane@example.com
EXPERIENCE
Python Developer
Acme Technologies Pvt Ltd
Jan 2020 - Dec 2021
- Built backend services in Python and SQL
Software Trainee - Python
Beta Solutions
Jan 2022 - Dec 2022
- Developed Python scripts and REST APIs
Sales Executive
Gamma Retail Ltd
Jan 2023 - Dec 2024
- Handled customer accounts and sales targets
"""


def exp(text, job=JOB):
    return evaluate_experience(job, parse_resume(text, TODAY))


def test_spec_example_total_5_relevant_3_match_100():
    r = score_candidate(JOB, DEFAULT_WEIGHTS, parse_resume(PROFILE_EXAMPLE, TODAY))
    e = r["experience"]
    assert e["total_months"] == 60 and e["total_years"] == 5.0
    assert e["relevant_months"] == 36 and e["relevant_years"] == 3.0
    assert e["required_months"] == 36
    assert e["match_pct"] == 100 and e["missing_months"] == 0 and e["difference_months"] == 0
    assert r["categories"]["experience"]["score"] == 100
    sales = next(x for x in e["entries"] if x["job_title"] == "Sales Executive")
    assert sales["relevance_weight"] == 0 and sales["counted_months"] == 0
    assert sales["company"] == "Gamma Retail Ltd"
    py = next(x for x in e["entries"] if x["job_title"] == "Python Developer")
    assert py["company"].startswith("Acme") and py["months"] == 24 and "python" in py["skills_used"]


def test_formula_30_of_36_is_83_3():
    text = PROFILE_EXAMPLE.replace("Dec 2022", "Jun 2022")           # trainee 6 months -> 30 relevant
    e = exp(text)
    assert e["relevant_months"] == 30
    assert e["match_pct"] == pytest.approx(83.3, abs=0.05)
    assert e["missing_months"] == 6


def test_same_title_unrelated_duties_is_not_relevant_but_flagged():
    text = ("Jane Roe\nEXPERIENCE\nPython Developer\nShop Co\nJan 2020 - Dec 2022\n"
            "- Managed store shelves and billing\n")
    r = score_candidate(JOB, DEFAULT_WEIGHTS, parse_resume(text, TODAY))
    assert r["experience"]["relevant_months"] == 0
    assert r["experience"]["total_months"] == 36
    assert r["experience"]["has_title_only"] and r["needs_review"]


def test_overlapping_jobs_not_double_counted():
    text = ("Jane Roe\nEXPERIENCE\nPython Developer\nA Ltd\nJan 2022 - Dec 2022\n- Python backend\n"
            "Python Developer\nB Ltd\nJul 2022 - Dec 2023\n- Python backend\n")
    e = exp(text)
    assert e["total_months"] == 24                      # Jan 2022 .. Dec 2023
    assert e["relevant_months"] == 24
    assert e["overlaps"] and e["overlaps"][0]["months"] == 6


def test_current_job_uses_today():
    e = exp("Jane Roe\nEXPERIENCE\nPython Developer\nA Ltd\nJan 2025 - Present\n- Python backend\n")
    assert e["total_months"] == 18                      # Jan 2025 .. Jun 2026


def test_career_gap_reported_not_penalised():
    text = ("Jane Roe\nEXPERIENCE\nPython Developer\nA Ltd\nJan 2020 - Dec 2020\n- Python\n"
            "Python Developer\nB Ltd\nJan 2022 - Dec 2022\n- Python\n")
    e = exp(text)
    assert e["total_months"] == 24 and e["relevant_months"] == 24
    assert e["gaps"] and e["gaps"][0]["months"] == 12


def test_internship_counts_half_and_is_configurable():
    text = ("Jane Roe\nEXPERIENCE\nPython Developer Intern\nA Ltd\nJan 2025 - Dec 2025\n- Python backend\n")
    assert exp(text)["relevant_months"] == 6            # default internship = 0.5
    job = dict(JOB, experience_counting={"internship": 1.0})
    assert exp(text, job)["relevant_months"] == 12
    job0 = dict(JOB, experience_counting={"internship": 0.0})
    assert exp(text, job0)["relevant_months"] == 0
    assert exp(text)["entries"][0]["type"] == "internship"


def test_part_time_and_full_time_labelled():
    text = ("Jane Roe\nEXPERIENCE\nPython Developer (Part-time)\nA Ltd\nJan 2025 - Dec 2025\n- Python backend\n")
    e = exp(text)
    assert e["entries"][0]["type"] == "part_time" and e["relevant_months"] == 6
    assert e["by_type"] == {"part_time": 12}


def test_missing_dates_are_uncertain_not_invented():
    e = exp("Jane Roe\nSkills\nPython\n8 years of experience as a developer\n")
    assert e["total_months"] == 0 and e["relevant_months"] == 0 and not e["usable_dates"]
    assert e["claimed_years"] == 8
    assert any("No usable employment dates" in w for w in e["warnings"])


def test_no_requirement_still_reports_but_is_not_scored():
    job = dict(JOB, min_experience_years=None)
    p = parse_resume(PROFILE_EXAMPLE, TODAY)
    r = score_candidate(job, DEFAULT_WEIGHTS, p)
    assert r["experience"]["relevant_months"] == 36 and r["experience"]["match_pct"] is None
    assert not r["categories"]["experience"]["applicable"]


def test_exceeding_max_is_information_only():
    job = dict(JOB, min_experience_years=1, max_experience_years=3)
    r = score_candidate(job, DEFAULT_WEIGHTS, parse_resume(PROFILE_EXAMPLE, TODAY))
    assert r["experience"]["exceeds_max"] and r["categories"]["experience"]["score"] == 100


def test_jde_experience_range_extracted():
    r = parse_jde("Job Title: Dev\nRequirements:\n- 3-5 years of experience in Python backend work\n")
    assert r["min_experience_years"] == 3 and r["max_experience_years"] == 5
    r2 = parse_jde("Job Title: Dev\nRequirements:\n- 4+ years of experience in Python\n")
    assert r2["min_experience_years"] == 4 and r2["max_experience_years"] is None


def test_result_is_json_serialisable_and_deterministic():
    import json
    p = parse_resume(PROFILE_EXAMPLE, TODAY)
    a = score_candidate(JOB, DEFAULT_WEIGHTS, p)
    b = score_candidate(JOB, DEFAULT_WEIGHTS, p)
    assert a == b
    json.dumps(a)
    for key in ("total_months", "relevant_months", "required_months", "missing_months",
                "match_pct", "entries", "overlaps", "warnings"):
        assert key in a["experience"]
