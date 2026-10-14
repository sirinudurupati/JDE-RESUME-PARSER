"""MNC / enterprise-ATS profile.

Large employers run enterprise systems (Workday, Taleo, SuccessFactors, iCIMS ...). Their shared,
well-documented behaviour is modelled here:

  1. the resume is parsed into FIELDS (company, title, dates, degree, year ...) that pre-fill the
     application - so parse completeness matters more than looks;
  2. layout features (columns, tables, text boxes, header contact, photos/icons) are treated strictly;
  3. the ranking score is mostly KEYWORD driven: required terms from the job must literally appear,
     and "related" skills do not count.

    score = 50 x parse quality  +  50 x keyword match

Vendors do not publish their real formulas, so this is a transparent model of typical enterprise
behaviour, not a replica of any one product. Checks that cannot be assessed ("na") are left out of
the denominator instead of being given full marks.
"""
from .ats import EMOJI_RX, ats_report

MNC_BANDS = [(75, "Likely to pass"), (55, "Borderline"), (0, "At risk")]


def mnc_band(score):
    return next(label for cut, label in MNC_BANDS if score >= cut)


def _frac(base, key):
    c = base.get(key)
    return None if not c or c["status"] == "unknown" else c["points"] / c["max"]


def mnc_report(resume: dict, skill_items=None, knockouts=None) -> dict:
    base_report = ats_report(resume, skill_items)
    base = {c["key"]: c for c in base_report["checks"]}
    info = resume.get("file_info") or {}
    text = resume.get("text", "")
    exp = resume.get("experience", [])
    dated = [e for e in exp if e.get("dates_ok")]
    checks = []

    def add(key, label, mx, frac, detail, fix=None):
        if frac is None:
            checks.append({"key": key, "label": label, "max": mx, "points": 0, "status": "na",
                           "detail": detail, "fix": None})
        else:
            st = "pass" if frac >= 0.99 else "warn" if frac >= 0.5 else "fail"
            checks.append({"key": key, "label": label, "max": mx, "points": round(frac * mx, 1),
                           "status": st, "detail": detail, "fix": None if st == "pass" else fix})

    def b(key, field):
        return (base.get(key) or {}).get(field)

    add("text", "Text can be extracted", 5, _frac(base, "text"), b("text", "detail"), b("text", "fix"))
    add("contact", "Name, email and phone parsed", 6, _frac(base, "contact"), b("contact", "detail"), b("contact", "fix"))
    add("sections", "Standard headings (Experience / Education / Skills)", 8, _frac(base, "sections"),
        b("sections", "detail"), b("sections", "fix"))
    add("columns", "Single column", 4, _frac(base, "columns"), b("columns", "detail") or "Layout not checked (original file unavailable).",
        b("columns", "fix"))
    add("tables", "No tables", 3, _frac(base, "tables"), b("tables", "detail") or "Layout not checked (original file unavailable).",
        b("tables", "fix"))

    if info and info.get("textboxes") is not None:
        ok = info.get("textboxes") == 0 and not info.get("header_footer_contact")
        add("hidden", "No text boxes / header-footer contact", 3, 1.0 if ok else 0.0,
            "Everything is in the page body." if ok else
            "Text boxes or header/footer content found - enterprise ATS often skips them.",
            "Move all content into the main page body.")
    else:
        add("hidden", "No text boxes / header-footer contact", 3, None, "Original file not available.")

    emoji = len(EMOJI_RX.findall(text))
    if info:
        imgs = info.get("images") or 0
        frac = 0.0 if imgs else 0.5 if emoji else 1.0
        detail = "No images or icons." if frac == 1 else (
            (f"{imgs} image(s) found (photos/logos/icons can break parsing). " if imgs else "") +
            (f"{emoji} emoji/icon symbol(s) found." if emoji else ""))
        add("graphics", "No photo / graphics / icons", 4, frac, detail,
            "Remove photos, logos and icons; use plain text only.")
    else:
        add("graphics", "No photo / graphics / icons", 4, 0.5 if emoji else None,
            f"{emoji} emoji/icon symbol(s) found." if emoji else "Original file not available.",
            "Remove icons and emoji.")

    # work history must parse into company + title + dates (these pre-fill the application form)
    if exp:
        full = sum(1 for e in exp if e.get("company") and e.get("job_title") and e.get("dates_ok"))
        gaps = []
        if any(not e.get("company") for e in exp):
            gaps.append("company")
        if any(not e.get("job_title") for e in exp):
            gaps.append("job title")
        if any(not e.get("dates_ok") for e in exp):
            gaps.append("dates")
        add("workhist", "Each job parsed into company + title + dates", 8, full / len(exp),
            f"{full} of {len(exp)} roles parsed completely" + (f" (missing in some: {', '.join(gaps)})." if gaps else "."),
            "Write each role as Job Title, Company, then Mon YYYY - Mon YYYY, on clearly separate lines.")
    else:
        add("workhist", "Each job parsed into company + title + dates", 8, None,
            "No work history (fresher) - not applicable.")

    edu = resume.get("education", {})
    got = (2 if edu.get("highest_rank") else 0) + (2 if edu.get("graduation_year") else 0)
    add("education", "Degree and graduation year parsed", 4, got / 4,
        "Degree: " + (edu.get("highest_label") or "not found") + "; year: " +
        (str(edu["graduation_year"]) if edu.get("graduation_year") else "not found") + ".",
        "Write the degree and graduation year together, e.g. B.Tech Computer Science, 2024.")

    if len(dated) >= 2:
        starts = [e["start"] for e in dated]
        rev = all(a >= c for a, c in zip(starts, starts[1:]))
        add("chrono", "Reverse-chronological order (newest first)", 3, 1.0 if rev else 0.0,
            "Newest role first." if rev else "Roles are not listed newest-first.", "List the most recent role first.")
    else:
        add("chrono", "Reverse-chronological order (newest first)", 3, None, "Fewer than two dated roles - not applicable.")

    if dated:
        precise = sum(1 for e in dated if not e.get("date_flags"))
        add("dates", "Month + year dates", 3, precise / len(dated),
            f"{precise} of {len(dated)} roles have month-level dates.", "Use Mon YYYY or MM/YYYY for every role.")
    else:
        add("dates", "Month + year dates", 3, None, "No dated roles - not applicable.")

    pages = info.get("pages") or max(1, round(len(text.split()) / 550))
    add("length", "1-2 pages", 2, 1.0 if pages <= 2 else 0.5 if pages == 3 else 0.0, f"{pages} page(s).",
        "Keep the resume to 1-2 pages.")

    assessed = [c for c in checks if c["status"] != "na"]
    possible = sum(c["max"] for c in assessed)
    earned = sum(c["points"] for c in assessed)
    parse_score = round(earned / possible * 50, 1) if possible else 0.0

    # keyword part: exact / equivalent terms only - a related skill does not match in an ATS
    kw_items, hit_w, tot_w = [], 0.0, 0.0
    for it in (skill_items or []):
        w = 2.0 if it["level"] == "mandatory" else 1.0
        hit = it["status"] in ("exact", "equivalent")
        kw_items.append({"term": it["display"], "level": it["level"], "found": hit,
                         "related_only": it["status"] in ("related", "partial")})
        tot_w += w
        hit_w += w if hit else 0.0
    if tot_w:
        keyword_score = round(hit_w / tot_w * 50, 1)
        total = round(parse_score + keyword_score, 1)
    else:                                  # no keywords defined: parse quality alone, scaled, and said so
        keyword_score = None
        total = round(parse_score * 2, 1)

    return {"score": min(100.0, total), "band": mnc_band(total), "parse_score": parse_score,
            "keyword_score": keyword_score, "checks": checks, "keywords": kw_items,
            "knockouts": knockouts or [], "layout_assessed": base_report["layout_assessed"],
            "standard_score": base_report["score"],
            "issues": [c["label"] + ": " + c["detail"] for c in checks if c["status"] in ("fail", "warn")],
            "note": "Model of typical enterprise-ATS behaviour (Workday / Taleo / SuccessFactors / iCIMS style): "
                    "50% how cleanly the resume parses into fields + 50% exact keyword match with the job. "
                    "Vendors do not publish their real formulas, so treat it as an estimate."}
