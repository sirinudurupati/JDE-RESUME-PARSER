from datetime import date

from talentmatch.jde_parser import parse_jde
from talentmatch.resume_parser import parse_resume

TODAY = date(2026, 6, 1)


def test_graduation_year_from_highest_degree_ignores_school():
    t = ("Jane Roe\njane@example.com\nEDUCATION\nMaster of Computer Applications (MCA) 2024 - 2026\n"
         "Bachelor of Computer Applications (BCA) 2021 - 2024\nSenior Secondary (XII) CBSE 2019 - 2020\n")
    p = parse_resume(t, TODAY)
    assert p["profile"]["graduation_year"] == 2026
    assert p["profile"]["highest_education"].startswith("Master")


def test_graduation_year_on_next_line_and_expected():
    t = "Jane Roe\nEDUCATION\nB.Tech in Computer Science\nXYZ Institute | 2021 - 2027\n"
    p = parse_resume(t, TODAY)
    assert p["profile"]["graduation_year"] == 2027 and p["profile"]["graduation_expected"]


def test_missing_graduation_year_is_flagged_not_guessed():
    p = parse_resume("Jane Roe\nEDUCATION\nBachelor of Business Administration\n", TODAY)
    assert p["profile"]["graduation_year"] is None
    assert any("Graduation year" in f for f in p["flags"])


def test_internship_section_and_fresher():
    t = ("Jane Roe\nINTERNSHIP\nFull Stack Developer Intern - KodNest July 2025 - Jan 2026\n- Built apps\n"
         "EDUCATION\nB.Tech 2025\n")
    p = parse_resume(t, TODAY)
    assert p["profile"]["experience_years"] == 0.58 and not p["profile"]["fresher"]
    f = parse_resume("Jane Roe\nEDUCATION\nB.Tech 2025\n", TODAY)
    assert f["profile"]["fresher"]


def test_duration_only_role_is_stated_not_counted():
    t = "Jane Roe\nPROJECTS\nFrontend Developer Intern | RoboWaves IT | 2 Months\n- Built a blog\n"
    p = parse_resume(t, TODAY)
    assert p["profile"]["stated_months"] == 2 and p["profile"]["experience_years"] == 0
    assert any("stated durations" in f for f in p["flags"])


def test_headings_and_certification_cleanup():
    t = ("Jane Roe\nACADEMIC BACKGROUND\nB.Tech 2024\nACHIEVEMENTS & CERTIFICATIONS\n"
         "- Oracle Cloud Certified Professional\n- Hackathon Finalist 2025\nSOFT SKILLS\nCommunication\n")
    p = parse_resume(t, TODAY)
    assert p["profile"]["graduation_year"] == 2024
    assert p["profile"]["certifications"] == ["Oracle Cloud Certified Professional"]


def test_jde_styled_unicode_and_certification_requirement():
    from talentmatch.extract import extract_text
    raw = ("Salesforce – Admin / Developer\n• Apex, Lightning Web Components (LWC), SOQL\n"
           "• APIs and integration fundamentals\n"
           "\U0001d5e0\U0001d5ee\U0001d5ff: Practical knowledge of the above and a relevant Salesforce certification\n")
    text = extract_text(raw.encode("utf-8"), ".txt", {".txt"})
    r = parse_jde(text)
    names = {s["name"] for s in r["skills"]}
    assert {"apex", "lwc", "soql", "rest api"} <= names
    assert r["certifications"] and r["certifications"][0]["mandatory"]
    assert r["title"].startswith("Salesforce")
