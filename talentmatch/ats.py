"""ATS-readability score: how reliably an Applicant Tracking System can READ this resume.

This is NOT the job-match score. It is a transparent checklist (100 points) built from things
that are known to trip up parsers: scanned/image text, multi-column layouts, tables, text boxes,
contact details in headers, missing standard sections, unreadable dates, icons/garbled glyphs.

Every check reports points earned / possible, why, and how to fix it. Checks that cannot be
assessed (e.g. no file available) are marked "unknown" and left out of the denominator rather
than silently awarded full marks.

Honest limit: every commercial ATS (Workday, Greenhouse, Taleo...) parses differently and is
proprietary, so this is a well-founded estimate of parse-friendliness, not a replica of any one.
"""
import re

EMOJI_RX = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆↔-↪]")
PRIVATE_RX = re.compile("[-�]")
SPACED_RX = re.compile(r"(?<![A-Za-z])(?:[A-Za-z] ){4,}[A-Za-z](?![A-Za-z])")
NUMBER_LINE_RX = re.compile(r"\d")

BANDS = [(80, "Good"), (60, "Fair"), (0, "Poor")]


def band(score):
    return next(label for cut, label in BANDS if score >= cut)


def _check(key, label, got, possible, status, detail, fix=None):
    return {"key": key, "label": label, "points": round(got, 1), "max": possible,
            "status": status, "detail": detail, "fix": fix}


def ats_report(resume: dict, skill_items=None) -> dict:
    text = resume.get("text", "")
    info = resume.get("file_info") or {}
    have_file = bool(info)
    checks = []
    words = len(text.split())
    pages = info.get("pages") or max(1, round(words / 550)) if text else 1

    # 1. text can be extracted (15)
    chars = len(text.strip())
    per_page = chars / max(1, info.get("pages") or 1)
    if chars < 150:
        checks.append(_check("text", "Readable text", 0, 15, "fail",
                             "Almost no text could be extracted - the file is probably a scanned image.",
                             "Export the resume as a text-based PDF or DOCX (not a photo/scan)."))
    elif per_page < 1200 and chars < 1500:
        checks.append(_check("text", "Readable text", 9, 15, "warn",
                             f"Only {chars} characters extracted - the resume is very short or partly image-based.",
                             "Make sure all content is real text, not pictures."))
    else:
        checks.append(_check("text", "Readable text", 15, 15, "pass", f"{chars} characters of text extracted."))

    # 2. contact details (15)
    got = (5 if resume.get("name") else 0) + (5 if resume.get("email") else 0) + (5 if resume.get("phone") else 0)
    missing = [n for n, v in (("name", resume.get("name")), ("email", resume.get("email")),
                              ("phone", resume.get("phone"))) if not v]
    checks.append(_check("contact", "Contact details found", got, 15, "pass" if not missing else "warn" if got >= 10 else "fail",
                         "Name, email and phone all detected." if not missing else
                         "Not detected: " + ", ".join(missing) + ".",
                         None if not missing else "Put name, email and phone as plain text at the top of page 1."))

    # 3. standard sections (20)
    secs = set(resume.get("sections", []))
    has_work = "experience" in secs                 # a recognised heading, not just dates somewhere
    has_alt = "projects" in secs or bool(resume.get("experience"))
    parts = [("Work experience / internships" if has_work or has_alt else "Work experience / internships",
              7 if has_work else 4 if has_alt else 0, 7, has_work or has_alt,
              "Add a heading such as 'Work Experience' or 'Internship'."),
             ("Education", 6 if "education" in secs else 0, 6, "education" in secs,
              "Add a clear 'Education' heading."),
             ("Skills", 7 if "skills" in secs else 0, 7, "skills" in secs,
              "Add a 'Skills' heading with a plain list of skills.")]
    got = sum(p[1] for p in parts)
    absent = [p[0] for p in parts if p[1] == 0]
    note = " (roles or projects found, but no standard work-experience heading)" if (not has_work and has_alt) else ""
    checks.append(_check("sections", "Standard section headings", got, 20,
                         "pass" if got == 20 else "warn" if got >= 13 else "fail",
                         ("Experience, Education and Skills headings all recognised." if got == 20 else
                          ("Missing or non-standard headings: " + ", ".join(absent) + "." if absent else "") + note),
                         None if got == 20 else parts[[p[1] == 0 or p[1] < p[2] for p in parts].index(True)][4]))

    # 4. dates (10)
    exp = resume.get("experience", [])
    if exp:
        ok = sum(1 for e in exp if e.get("dates_ok") and not e.get("date_flags"))
        share = ok / len(exp)
        checks.append(_check("dates", "Clear employment dates", 10 * share, 10,
                             "pass" if share == 1 else "warn" if share >= 0.5 else "fail",
                             f"{ok} of {len(exp)} roles have clear 'Mon YYYY - Mon YYYY' dates.",
                             None if share == 1 else "Write dates as 'Jan 2023 - Mar 2024' (month + year) on every role."))
    else:
        yr = resume.get("education", {}).get("graduation_year")
        checks.append(_check("dates", "Clear employment dates", 10 if yr else 5, 10, "pass" if yr else "warn",
                             "No work history; graduation year is clear." if yr else
                             "No work history and no clear graduation year.",
                             None if yr else "Show the graduation year next to the degree."))

    # 5. layout (20): single column 8, no tables 6, no heavy graphics/text boxes 3, contact not in header 3
    if have_file and info.get("multi_column") is not None:
        mc = info["multi_column"]
        checks.append(_check("columns", "Single-column layout", 0 if mc else 8, 8, "fail" if mc else "pass",
                             "Looks like a multi-column layout - many ATS read columns in the wrong order."
                             if mc else "Single-column reading order.",
                             "Use one column; avoid sidebars." if mc else None))
        t = info.get("tables") or 0
        checks.append(_check("tables", "No tables", 0 if t else 6, 6, "fail" if t else "pass",
                             f"{t} table(s) found - table cells can be scrambled or skipped." if t else "No tables.",
                             "Replace tables with plain headings and bullet lines." if t else None))
        img, tb = info.get("images") or 0, info.get("textboxes") or 0
        bad = img > 3 or tb > 0
        checks.append(_check("graphics", "No text boxes / heavy graphics", 0 if tb else 3 if img > 3 else 3, 3,
                             "fail" if bad else "pass",
                             (f"{tb} text box(es) found - ATS often skips text boxes. " if tb else "") +
                             (f"{img} images found - icons/graphics may hide text. " if img > 3 else "")
                             or ("Contains " + str(img) + " small image(s); fine." if img else "No text boxes or heavy graphics."),
                             "Put everything in normal paragraphs; remove text boxes/graphics." if bad else None))
        hf = bool(info.get("header_footer_contact"))
        checks.append(_check("header", "Contact details not in header/footer", 0 if hf else 3, 3,
                             "fail" if hf else "pass",
                             "Contact details sit in the page header/footer, which many ATS ignore." if hf else
                             "Contact details are in the page body.",
                             "Move contact details into the main body." if hf else None))
    else:
        checks.append(_check("layout", "Layout (columns, tables, text boxes)", 0, 20, "unknown",
                             "The original file was not available, so layout could not be assessed.", None))

    # 6. clean characters (10)
    emoji = len(EMOJI_RX.findall(text))
    odd = len(PRIVATE_RX.findall(text))
    spaced = len(SPACED_RX.findall(text))
    loss = min(10, (3 if emoji else 0) + (2 if odd > 10 else 0) + min(5, spaced * 2))
    issues = []
    if emoji:
        issues.append(f"{emoji} emoji/icon symbol(s)")
    if odd > 10:
        issues.append(f"{odd} private-use/garbled glyphs (usually fancy bullets)")
    if spaced:
        issues.append(f"{spaced} spaced-out word(s) like 'N o v'")
    checks.append(_check("chars", "Clean characters", 10 - loss, 10, "pass" if not loss else "warn",
                         ("Found " + "; ".join(issues) + ".") if issues else "No emoji, garbled glyphs or spaced-out text.",
                         "Use plain text bullets and no emoji/icons." if issues else None))

    # 7. length (5)
    if pages <= 2 and 200 <= words <= 1300:
        checks.append(_check("length", "Sensible length", 5, 5, "pass", f"{pages} page(s), about {words} words."))
    elif pages <= 3 and words <= 1800:
        checks.append(_check("length", "Sensible length", 3, 5, "warn",
                             f"{pages} page(s), about {words} words.", "Aim for 1-2 pages."))
    else:
        checks.append(_check("length", "Sensible length", 1, 5, "fail",
                             f"{pages} page(s), about {words} words.", "Shorten to 1-2 pages."))

    # 8. measurable achievements (5)
    bullets = [l for l in text.split("\n") if re.match(r"^\s*[-*•●▪>]", l) and len(l.strip()) > 20]
    numeric = sum(1 for l in bullets if NUMBER_LINE_RX.search(l))
    pts = 5 if numeric >= 3 else 3 if numeric >= 1 else 0
    checks.append(_check("metrics", "Measurable results", pts, 5, "pass" if pts == 5 else "warn" if pts else "fail",
                         f"{numeric} bullet(s) contain numbers or percentages.",
                         None if pts == 5 else "Add numbers to bullets (e.g. 'reduced load time by 30%')."))

    known = [c for c in checks if c["status"] != "unknown"]
    possible = sum(c["max"] for c in known)
    earned = sum(c["points"] for c in known)
    score = round(earned / possible * 100, 1) if possible else 0.0

    # keyword view (informational - the job-match score already covers skills)
    keyword = None
    if skill_items:
        hits = [i["display"] for i in skill_items if i["status"] in ("exact", "equivalent")]
        miss = [i["display"] for i in skill_items if i["status"] not in ("exact", "equivalent")]
        keyword = {"found": len(hits), "total": len(skill_items),
                   "pct": round(len(hits) / len(skill_items) * 100, 1), "missing": miss}
    return {"score": score, "band": band(score), "checks": checks, "assessed_points": possible,
            "layout_assessed": have_file and info.get("multi_column") is not None,
            "keywords": keyword,
            "issues": [c["label"] + ": " + c["detail"] for c in checks if c["status"] in ("fail", "warn")],
            "note": "Estimate of how parse-friendly the file is for typical ATS software; each ATS differs."}
