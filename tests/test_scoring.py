from datetime import date

import pytest

from talentmatch.config import DEFAULT_WEIGHTS
from talentmatch.jde_parser import parse_jde
from talentmatch.resume_parser import parse_resume
from talentmatch.scoring import score_candidate

TODAY = date(2026, 6, 1)


def job(**kw):
    base = {"title": "Python Developer", "responsibilities": [],
            "skills": [{"name": "python", "level": "mandatory"},
                       {"name": "sql", "level": "mandatory"},
                       {"name": "fastapi", "level": "mandatory"},
                       {"name": "docker", "level": "preferred"}],
            "min_experience_years": 2, "experience_mandatory": True,
            "education": {"min_level": 2, "mandatory": True}, "certifications": []}
    base.update(kw)
    return base


def resume(text):
    return parse_resume(text, TODAY)


GOOD = """Jane Roe
jane@example.com
Skills
Python, SQL, FastAPI
Experience
Backend Developer
Foo Inc
Jan 2022 - Present
- Built APIs in Python and FastAPI with SQL databases
Education
B.Tech in Computer Science
"""


def test_weights_total_and_bounds():
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(GOOD))
    assert 0 <= r["overall"] <= 100
    pts = sum(c["points"] for c in r["categories"].values())
    assert pts == pytest.approx(r["overall"], abs=0.2)
    eff = sum(c["effective_weight"] for c in r["categories"].values() if c["applicable"])
    assert eff == pytest.approx(100, abs=0.1)


def test_default_weights_sum_100():
    assert sum(DEFAULT_WEIGHTS.values()) == 100


def test_category_math_by_hand():
    # skills 100% (all matched but docker pref missing -> (6+0)/(6+1)); verify formula
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(GOOD))
    sk = r["categories"]["skills"]
    # mandatory 3 skills: python, sql, fastapi, each listed AND evidenced? only python+fastapi+sql in bullet
    assert sk["score"] == pytest.approx(round(6 / 7 * 100, 1), abs=0.2)
    # no responsibilities / certs in job -> excluded, weights redistributed over skills/exp/edu = 80
    assert not r["categories"]["responsibilities"]["applicable"]
    assert r["categories"]["skills"]["effective_weight"] == pytest.approx(40 / 80 * 100, abs=0.1)


def test_empty_resume_is_zero_and_flagged():
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume("x"))
    assert r["overall"] == 0
    assert r["needs_review"]
    assert set(r["missing_mandatory"]) == {"Python", "SQL", "FastAPI"}


def test_missing_dates_not_assumed():
    txt = "Jane Roe\njane@example.com\nSkills\nPython, SQL, FastAPI\n10 years of experience in software\nEducation\nB.Tech\n"
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(txt))
    assert r["categories"]["experience"]["score"] == 0
    assert r["experience"]["claimed_years"] == 10
    assert r["needs_review"]
    assert any("dates" in x.lower() for x in r["review_reasons"])


def test_javascript_is_not_python():
    txt = GOOD.replace("Python, SQL, FastAPI", "JavaScript, TypeScript, Node.js").replace("Python and FastAPI", "JavaScript")
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(txt))
    assert "Python" in r["missing_mandatory"]


def test_related_skill_is_not_exact():
    txt = GOOD.replace("FastAPI", "Flask")
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(txt))
    item = next(i for i in r["skills"] if i["name"] == "fastapi")
    assert item["status"] == "related"
    assert 0 < item["credit"] < 0.6
    assert "FastAPI" in r["related_mandatory"] and "FastAPI" not in r["matched_mandatory"]


def test_specific_database_satisfies_sql():
    txt = GOOD.replace("SQL", "PostgreSQL")
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(txt))
    item = next(i for i in r["skills"] if i["name"] == "sql")
    assert item["status"] == "equivalent"


def test_listed_only_skill_is_unverified_and_gets_less_credit():
    listed = "Jane Roe\njane@example.com\nSkills\nPython, SQL, FastAPI\nExperience\nClerk\nFoo\nJan 2022 - Present\n- Filing\nEducation\nB.Tech\n"
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(listed))
    py = next(i for i in r["skills"] if i["name"] == "python")
    assert py["unverified"] and py["credit"] == pytest.approx(0.8)
    assert r["needs_review"]


def test_unrelated_experience_not_counted():
    txt = ("Jane Roe\njane@example.com\nExperience\nBaker\nBread Co\nJan 2010 - Dec 2020\n"
           "- Baked bread daily\nEducation\nB.Tech\nSkills\nPython\n")
    r = score_candidate(job(), DEFAULT_WEIGHTS, resume(txt))
    assert r["experience"]["total_years"] > 9
    assert r["experience"]["relevant_years"] == 0
    assert r["categories"]["experience"]["score"] == 0


def test_overlapping_periods_counted_once():
    txt = ("Jane Roe\njane@example.com\nExperience\nDev A\nCo A\nJan 2022 - Dec 2022\n- Python work\n"
           "Dev B\nCo B\nJun 2022 - Dec 2022\n- Python work too\nEducation\nB.Tech\n")
    p = resume(txt)
    assert p["total_months"] == 12
    assert any("Overlapping" in f for f in p["flags"])


def test_present_end_uses_today():
    p = resume("Jane Roe\nExperience\nDev\nCo\nJan 2025 - Present\n- Python\n")
    assert p["total_months"] == 18     # Jan 2025 .. Jun 2026 inclusive


def test_year_only_dates_flagged():
    p = resume("Jane Roe\nExperience\nDev\nCo\n2019 - 2021\n- Python\n")
    assert p["total_months"] == 24
    assert any("year-only" in f for f in p["flags"])


def test_invalid_date_range_not_counted():
    p = resume("Jane Roe\nExperience\nDev\nCo\nMar 2022 - Jan 2021\n- Python\n")
    assert p["total_months"] == 0
    assert any("invalid" in f.lower() for f in p["flags"])


def test_education_levels():
    j = job(education={"min_level": 3, "mandatory": True})
    r = score_candidate(j, DEFAULT_WEIGHTS, resume(GOOD))
    assert r["education"]["status"] == "one level below"
    assert r["categories"]["education"]["score"] == 50


def test_certifications_matching():
    j = job(certifications=[{"name": "AWS Certified Cloud Practitioner", "mandatory": True},
                            {"name": "PMP", "mandatory": False}])
    txt = GOOD + "Certifications\nAWS Certified Cloud Practitioner\n"
    r = score_candidate(j, DEFAULT_WEIGHTS, resume(txt))
    assert r["categories"]["certifications"]["score"] == pytest.approx(66.7, abs=0.1)


def test_deterministic():
    a = score_candidate(job(), DEFAULT_WEIGHTS, resume(GOOD))
    b = score_candidate(job(), DEFAULT_WEIGHTS, resume(GOOD))
    assert a == b


def test_custom_weights_change_score():
    w = dict(DEFAULT_WEIGHTS, skills=0, experience=100, education=0)
    r = score_candidate(job(), w, resume(GOOD))
    assert r["categories"]["skills"]["applicable"] is False
    assert r["overall"] == r["categories"]["experience"]["score"]


def test_zero_weights_fall_back_to_defaults():
    r = score_candidate(job(), {k: 0 for k in DEFAULT_WEIGHTS}, resume(GOOD))
    assert 0 < r["overall"] <= 100


def test_job_with_nothing_scorable_is_zero_not_100():
    r = score_candidate({"title": "x", "skills": [], "responsibilities": [], "certifications": []},
                        DEFAULT_WEIGHTS, resume(GOOD))
    assert r["overall"] == 0


def test_protected_traits_ignored():
    a = resume(GOOD)
    b = resume(GOOD + "\nAge: 25\nGender: Female\nMarital status: Single\nReligion: X\n")
    ra = score_candidate(job(), DEFAULT_WEIGHTS, a)
    rb = score_candidate(job(), DEFAULT_WEIGHTS, b)
    assert ra["overall"] == rb["overall"]


def test_ranking_follows_scores():
    j = parse_jde(open("tests/samples/jd_python.txt", encoding="utf-8").read())
    strong = open("tests/samples/resume_a.txt", encoding="utf-8").read()
    weak = "Sam Lee\nsam@example.com\nSkills\nJavaScript, React\nExperience\nWeb Dev\nCo\nJan 2023 - Present\n- Built React UIs\nEducation\nDiploma in IT\n"
    s = score_candidate(j, DEFAULT_WEIGHTS, resume(strong))["overall"]
    w = score_candidate(j, DEFAULT_WEIGHTS, resume(weak))["overall"]
    assert s > w


def test_alternative_skill_group_needs_only_one():
    j = job(skills=[{"name": "sql", "level": "mandatory", "group": "g1"},
                    {"name": "mysql", "level": "mandatory", "group": "g1"},
                    {"name": "postgresql", "level": "mandatory", "group": "g1"},
                    {"name": "python", "level": "mandatory"}])
    txt = GOOD.replace("Python, SQL, FastAPI", "Python, MySQL").replace("SQL databases", "MySQL databases")
    r = score_candidate(j, DEFAULT_WEIGHTS, resume(txt))
    assert r["missing_mandatory"] == []                     # one of the three is enough
    assert len([i for i in r["skills"] if i["level"] == "mandatory"]) == 2
    grp = next(i for i in r["skills"] if i.get("alternatives"))
    assert grp["display"] == "SQL or MySQL or PostgreSQL" and grp["status"] in ("exact", "equivalent")


def test_jde_or_list_becomes_group_and_editor_roundtrip():
    from talentmatch.service import clean_requirements
    r = parse_jde("Job Title: DS\nRequirements:\n- Database: SQL, MySQL, PostgreSQL, or similar\n- Python\n")
    groups = {s["name"]: s["group"] for s in r["skills"]}
    assert groups["sql"] and groups["sql"] == groups["mysql"] == groups["postgresql"]
    assert groups["python"] is None
    cleaned = clean_requirements({"title": "DS", "skills": [{"name": "SQL or MySQL", "level": "mandatory"},
                                                            {"name": "Python", "level": "mandatory"}]}, {})
    g = {s["name"]: s["group"] for s in cleaned["skills"]}
    assert g["sql"] == g["mysql"] and g["sql"] and g["python"] is None


def test_free_text_junk_is_dropped():
    r = parse_jde("Job Title: DS\nRequired Skills:\n- Libraries: Pandas, NumPy, and educational qualifications, similar tools\n")
    names = {s["name"] for s in r["skills"]}
    assert not any("qualification" in n or "similar" in n for n in names)


def test_sentence_style_alternatives_and_edge_cases():
    r = parse_jde("Job Title: X\nPreferred Skills:\n- Experience with TensorFlow or PyTorch.\n"
                  "- Familiarity with cloud platforms such as AWS, Azure, or Google Cloud.\n"
                  "- HTML/CSS, Python, SQL and Docker or Kubernetes\n")
    g = {s["name"]: s["group"] for s in r["skills"]}
    assert g["tensorflow"] and g["tensorflow"] == g["pytorch"]
    assert g["aws"] and g["aws"] == g["azure"] == g["gcp"]
    assert g["docker"] and g["docker"] == g["kubernetes"]
    assert g["python"] is None and g["sql"] is None and g["html"] is None      # "and" breaks the chain


def test_keyword_dump_and_soft_skills_do_not_become_mandatory():
    r = parse_jde("Job Title: DS\nPREFERRED SKILLS\n- Spark\nSOFT SKILLS\n- Strong communication\n"
                  "RESUME PARSER SKILL KEYWORDS\nPython, Spark, communication, SQL\n")
    lvl = {s["name"]: s["level"] for s in r["skills"]}
    assert lvl["spark"] == "preferred" and lvl["communication"] == "preferred"
    assert "python" not in lvl and "sql" not in lvl      # only appeared in the keyword dump
