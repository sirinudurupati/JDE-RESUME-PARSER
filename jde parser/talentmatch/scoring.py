"""Explainable resume-vs-job scoring.

overall = 100 * sum(w_i * s_i) / sum(w_i)    over categories that APPLY

* s_i in [0, 1] is each category's own score.
* A category applies only if the JOB defines something to score (e.g. no
  education requirement -> education is "not applicable" and its weight is
  redistributed proportionally, and this is shown to HR).
* If the job asks for something and the RESUME has no evidence, the category
  scores 0 and is marked "unverified" - never silently full marks.
* Protected / irrelevant attributes (age, gender, photo, ...) are never read.
"""
import re

from . import skills as sk
from .config import CATEGORY_LABELS, DEFAULT_EXPERIENCE_COUNTING, normalize_weights
from .textutil import content_stems, edu_levels_in, EDU_LEVELS

# credit multiplier when a skill is only named in a skills list, with no
# supporting project / job-history context
LISTED_ONLY_FACTOR = 0.8
MANDATORY_SKILL_WEIGHT = 2.0
PREFERRED_SKILL_WEIGHT = 1.0
PARTIAL_TEXT_CREDIT = 0.3
RESP_FULL_COVERAGE = 0.6          # keyword coverage that earns full credit for a duty
SOFT_SKILLS = {"communication", "leadership", "project management",
               "stakeholder management", "problem solving"}


def _pct(x):
    return round(x * 100, 1)


# ------------------------------------------------------------------ skills
def _match_skill(req, resume):
    """-> dict describing how the resume satisfies one required skill."""
    name = req["name"]
    have = resume.get("skills", {})
    text_low = resume.get("text", "").lower()
    out = {"name": name, "display": req.get("display") or sk.display(name),
           "level": req["level"], "status": "missing", "credit": 0.0,
           "via": None, "evidence": None, "unverified": False, "group": req.get("group")}
    canon = sk.canonical(name)
    if canon:
        credit, via = sk.best_relation(set(have), canon)
        if credit > 0 and via:
            info = have[via]
            factor = 1.0 if info.get("evidenced") else LISTED_ONLY_FACTOR
            out["credit"] = round(credit * factor, 4)
            out["via"] = sk.display(via)
            out["evidence"] = info.get("snippet")
            out["unverified"] = not info.get("evidenced")
            out["status"] = ("exact" if credit >= 1.0 else
                             "equivalent" if credit >= 0.8 else "related")
        return out
    # free-text requirement (not in the skill library)
    phrase = name.lower().strip()
    if phrase and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text_low):
        out.update(status="exact", credit=1.0, unverified=False)
        m = re.search(re.escape(phrase), text_low)
        ls = text_low.rfind("\n", 0, m.start()) + 1
        le = text_low.find("\n", m.start())
        out["evidence"] = resume["text"][ls: le if le != -1 else len(text_low)].strip()[:200]
        return out
    need = content_stems(phrase)
    if need:
        got = need & content_stems(text_low)
        if len(got) / len(need) >= 0.5 and got:
            out.update(status="partial", credit=PARTIAL_TEXT_CREDIT)
    return out


def _collapse_groups(items):
    """Skills sharing a `group` are alternatives ("SQL, MySQL or PostgreSQL"): any ONE satisfies
    the requirement, so the group is scored once, using the candidate's best member."""
    groups = {}
    for it in items:
        if it.get("group"):
            groups.setdefault(it["group"], []).append(it)
    out, done = [], set()
    for it in items:
        g = it.get("group")
        if not g or len(groups[g]) < 2:
            out.append(it)
        elif g not in done:
            done.add(g)
            members = groups[g]
            best = dict(max(members, key=lambda m: m["credit"]))
            best["display"] = " or ".join(m["display"] for m in members)
            best["alternatives"] = [m["display"] for m in members]
            best["level"] = "mandatory" if any(m["level"] == "mandatory" for m in members) else "preferred"
            out.append(best)
    return out


def score_skills(job, resume):
    items = _collapse_groups([_match_skill(s, resume) for s in job.get("skills", [])])
    if not items:
        return None, items
    num = den = 0.0
    for it in items:
        w = MANDATORY_SKILL_WEIGHT if it["level"] == "mandatory" else PREFERRED_SKILL_WEIGHT
        num += w * it["credit"]
        den += w
    return num / den, items


# -------------------------------------------------------------- experience
GENERIC_TITLE_WORDS = {"senior", "junior", "lead", "associate", "developer", "engineer", "intern",
                       "trainee", "manager", "executive", "analyst", "specialist", "software", "full",
                       "stack", "and", "the", "of", "sr", "jr", "i", "ii", "iii", "admin", "consultant"}


def _title_tokens(title):
    return {t for t in re.findall(r"[a-z][a-z+#.]+", (title or "").lower())
            if t not in GENERIC_TITLE_WORDS and len(t) > 2}


def _entry_relevance(entry, job):
    """Judge one job-history entry on EVIDENCE (skills used, duties), not the title alone.

    -> dict(weight 1.0/0.5/0, evidence, note, uncertain)"""
    # evidence comes from the role's description, NOT from its title line
    body = entry.get("body", entry.get("text", ""))
    have = set(entry["skills"]) if "skills" in entry else set(sk.find_skills(body))
    tech = [s for s in job.get("skills", [])
            if sk.canonical(s["name"]) and sk.canonical(s["name"]) not in SOFT_SKILLS]
    mand = [s for s in tech if s["level"] == "mandatory"] or tech
    strong, related = [], []
    for s in tech:
        c = sk.canonical(s["name"])
        credit, via = sk.best_relation(have, c)
        if credit >= 0.8:
            strong.append(s)
        elif credit >= 0.4:
            related.append(s)
    strong_mand = [s for s in strong if s in mand]

    # duties: does the entry text cover the job's responsibilities?
    ent_stems = content_stems(body)
    duty_hits = []
    for d in job.get("responsibilities", []):
        plain = content_stems(d)
        if plain and len(plain & ent_stems) / len(plain) >= 0.5:
            duty_hits.append(d)

    title_match = bool(_title_tokens(job.get("title")) & _title_tokens(entry.get("job_title") or entry.get("title")))
    evidence = {"skills": [s.get("display") or sk.display(s["name"]) for s in strong],
                "related_skills": [s.get("display") or sk.display(s["name"]) for s in related],
                "duties": duty_hits[:2], "title_match": title_match}
    if mand and len(strong_mand) / len(mand) >= 1 / 3:
        return {"weight": 1.0, "evidence": evidence, "uncertain": False,
                "note": f"relevant - evidences {len(strong)} of the job's required skills"}
    if strong or related or duty_hits:
        why = []
        if strong:
            why.append("some required skills")
        if related:
            why.append("related skills")
        if duty_hits:
            why.append("similar duties")
        return {"weight": 0.5, "evidence": evidence, "uncertain": False,
                "note": "partly relevant - " + ", ".join(why)}
    if title_match:
        return {"weight": 0.0, "evidence": evidence, "uncertain": True,
                "note": "title resembles the job but no skills or duties support it - review"}
    return {"weight": 0.0, "evidence": evidence, "uncertain": False,
            "note": "no evidence of the required skills or duties"}


def _fmt(idx):
    y, m = divmod(idx - 1, 12)
    return f"{y}-{m + 1:02d}"


def evaluate_experience(job, resume):
    """Full, explainable work-experience evaluation. Always returns a dict."""
    counting = dict(DEFAULT_EXPERIENCE_COUNTING)
    counting.update(job.get("experience_counting") or {})
    entries = resume.get("experience", [])
    dated = [e for e in entries if e.get("dates_ok")]
    warnings = []

    # ---- per-entry relevance and credit
    rows = []
    for e in entries:
        if not e.get("dates_ok"):
            rows.append({"company": e.get("company"), "job_title": e.get("job_title"), "title": e["title"],
                         "type": e.get("employment_type", "unknown"), "start": None, "end": None,
                         "months": None, "relevance_weight": None, "type_weight": None,
                         "counted_months": 0.0, "note": "dates unreadable or invalid - not counted",
                         "evidence": {}, "uncertain": True, "skills_used": e.get("skills", [])})
            continue
        rel = _entry_relevance(e, job)
        etype = e.get("employment_type", "unknown")
        tw = float(counting.get(etype, 1.0))
        rows.append({"company": e.get("company"), "job_title": e.get("job_title"), "title": e["title"],
                     "type": etype, "start": _fmt(e["start"]), "end": _fmt(e["end"]),
                     "months": e["end"] - e["start"] + 1, "relevance_weight": rel["weight"],
                     "type_weight": tw, "counted_months": 0.0, "note": rel["note"],
                     "evidence": rel["evidence"], "uncertain": rel["uncertain"],
                     "skills_used": e.get("skills", []), "_s": e["start"], "_e": e["end"],
                     "date_flags": e.get("date_flags", [])})

    # ---- credit each calendar month once, to the entry that earns the most for it
    credited = {}
    order = sorted([r for r in rows if r.get("_s") is not None],
                   key=lambda r: -(r["relevance_weight"] * r["type_weight"]))
    for r in order:
        eff = r["relevance_weight"] * r["type_weight"]
        for m in range(r["_s"], r["_e"] + 1):
            if m not in credited:
                credited[m] = eff
                r["counted_months"] += eff
    relevant_months = sum(credited.values())
    all_months = set()
    by_type = {}
    for r in rows:
        if r.get("_s") is not None:
            span = set(range(r["_s"], r["_e"] + 1))
            all_months |= span
            by_type.setdefault(r["type"], set()).update(span)
    for r in rows:
        r.pop("_s", None)
        r.pop("_e", None)
        r["counted_months"] = round(r["counted_months"], 1)

    # ---- requirement, difference, score
    req_years = job.get("min_experience_years")
    req_months = round(float(req_years) * 12) if req_years else None
    max_years = job.get("max_experience_years")
    max_months = round(float(max_years) * 12) if max_years else None
    total_months = len(all_months)
    info = {
        "required": req_years or None, "required_months": req_months,
        "max_years": max_years or None, "max_months": max_months,
        "total_months": total_months, "total_years": round(total_months / 12, 2),
        "relevant_months": round(relevant_months, 1), "relevant_years": round(relevant_months / 12, 2),
        "claimed_years": resume.get("claimed_years"),
        "by_type": {k: len(v) for k, v in by_type.items()},
        "counting": counting, "entries": rows,
        "overlaps": resume.get("overlaps", []), "gaps": resume.get("gaps", []),
        "stated_undated": resume.get("stated_experience", []),
        "mandatory": job.get("experience_mandatory", True), "usable_dates": bool(dated),
        "difference_months": None, "missing_months": None, "exceeds_max": False,
        "match_pct": None, "warnings": warnings,
    }
    if req_months:
        info["difference_months"] = round(relevant_months - req_months, 1)
        info["missing_months"] = round(max(0.0, req_months - relevant_months), 1)
        info["match_pct"] = round(min(100.0, relevant_months / req_months * 100), 1)
    if max_months and total_months > max_months:
        info["exceeds_max"] = True
        warnings.append(f"Total experience ({total_months / 12:.1f} yrs) is above the job's stated maximum "
                        f"({max_years:g} yrs) - shown for information, not penalised.")

    # ---- uncertainty warnings (never silently resolved)
    if not dated:
        warnings.append("No usable employment dates - experience could not be verified.")
    if info["stated_undated"]:
        warnings.append("Some roles state only a duration, not dates "
                        f"({sum(x['months'] for x in info['stated_undated']):g} months) - not counted.")
    if any(r["type"] == "unknown" and r["months"] for r in rows):
        warnings.append("Employment type (full-time/part-time/internship) not stated for some roles - "
                        "counted using the 'type not stated' rule.")
    for r in rows:
        for f in r.get("date_flags") or []:
            warnings.append(f"{(r['job_title'] or r['title'])[:40]}: {f}.")
        if r["uncertain"] and r["months"]:
            warnings.append(f"{(r['job_title'] or r['title'])[:40]}: {r['note']}.")
    if info["overlaps"]:
        warnings.append(f"{len(info['overlaps'])} overlapping role period(s): overlapping calendar months are "
                        "counted once.")
    info["warnings"] = list(dict.fromkeys(warnings))
    info["has_title_only"] = any(r["uncertain"] and r["months"] for r in rows)
    return info


def score_experience(job, resume):
    info = evaluate_experience(job, resume)
    if not info["required_months"]:
        return None, info                      # job states no minimum: shown, not scored
    if not info["usable_dates"]:
        return 0.0, info
    return min(1.0, info["relevant_months"] / info["required_months"]), info


# --------------------------------------------------------------- education
def score_education(job, resume):
    req = job.get("education")
    if not req or not req.get("min_level"):
        return None, {"required": None}
    need = int(req["min_level"])
    have = resume.get("education", {}).get("highest_rank")
    info = {"required": EDU_LEVELS.get(need), "required_rank": need,
            "mandatory": bool(req.get("mandatory", True)),
            "candidate": EDU_LEVELS.get(have) if have else None,
            "field": resume.get("education", {}).get("field"),
            "required_field": req.get("field"),
            "lines": resume.get("education", {}).get("lines", [])}
    if not have:
        info["status"] = "unverified"
        return 0.0, info
    if have >= need:
        info["status"] = "met"
        return 1.0, info
    if have == need - 1:
        info["status"] = "one level below"
        return 0.5, info
    info["status"] = "below"
    return 0.0, info


# ---------------------------------------------------------- responsibilities
def score_responsibilities(job, resume):
    duties = [d for d in job.get("responsibilities", []) if d.strip()]
    if not duties:
        return None, []
    text = resume.get("text", "")
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    line_stems = [(l, content_stems(l), set(sk.find_skills(l))) for l in lines]
    all_stems = set().union(*[s for _, s, _ in line_stems]) if line_stems else set()
    have_skills = set(resume.get("skills", {}))
    results, total = [], 0.0
    for d in duties:
        d_skills = set(sk.find_skills(d))
        d_stems = content_stems(d)
        # skill words are judged through the ontology, not as plain words
        skill_words = set()
        for s in d_skills:
            for a in s.split():
                skill_words.add(a)
        plain = {w for w in d_stems if w not in skill_words}
        keys = len(plain) + len(d_skills)
        if keys == 0:
            continue
        hit = len(plain & all_stems)
        for s in d_skills:
            credit, _ = sk.best_relation(have_skills, s)
            hit += credit if credit >= 0.5 else 0
        coverage = hit / keys
        score = min(1.0, coverage / RESP_FULL_COVERAGE)
        # best supporting line
        best, best_line = 0, None
        for l, st, sks in line_stems:
            ov = len(plain & st) + len(d_skills & sks)
            if ov > best:
                best, best_line = ov, l
        status = "covered" if coverage >= 0.5 else "partial" if coverage >= 0.25 else "not evident"
        results.append({"text": d, "coverage": round(coverage, 2), "score": round(score, 3),
                        "status": status,
                        "evidence": best_line[:200] if best_line and status != "not evident" else None})
        total += score
    if not results:
        return None, []
    return total / len(results), results


# ---------------------------------------------------------- certifications
_CERT_NOISE = {"certified", "certification", "certificate", "professional", "the", "a", "of",
               "in", "and", "exam", "associate"}


def _cert_tokens(name):
    return {t for t in re.findall(r"[a-z0-9+#]+", name.lower()) if t not in _CERT_NOISE}


def score_certifications(job, resume):
    certs = job.get("certifications", [])
    if not certs:
        return None, []
    lines = [set(re.findall(r"[a-z0-9+#]+", l.lower()))
             for l in resume.get("text", "").split("\n")]
    out, num, den = [], 0.0, 0.0
    for c in certs:
        toks = _cert_tokens(c["name"])
        found = bool(toks) and any(toks <= l for l in lines)
        w = MANDATORY_SKILL_WEIGHT if c.get("mandatory") else PREFERRED_SKILL_WEIGHT
        num += w * (1.0 if found else 0.0)
        den += w
        out.append({"name": c["name"], "mandatory": bool(c.get("mandatory")), "found": found})
    return num / den, out


# ------------------------------------------------------------------ overall
def score_candidate(job: dict, weights: dict, resume: dict) -> dict:
    """Pure function: (requirements, weights, parsed resume) -> full explainable result."""
    weights = normalize_weights(weights)
    s_skill, skill_items = score_skills(job, resume)
    s_exp, exp_info = score_experience(job, resume)
    s_edu, edu_info = score_education(job, resume)
    s_resp, resp_items = score_responsibilities(job, resume)
    s_cert, cert_items = score_certifications(job, resume)
    raw = {"skills": s_skill, "experience": s_exp, "education": s_edu,
           "responsibilities": s_resp, "certifications": s_cert}

    applicable = {k: v for k, v in raw.items() if v is not None and weights[k] > 0}
    total_w = sum(weights[k] for k in applicable)
    cats = {}
    overall = 0.0
    for k in raw:
        used = k in applicable
        eff = (weights[k] / total_w * 100) if used and total_w else 0.0
        cats[k] = {"label": CATEGORY_LABELS[k], "score": _pct(raw[k]) if raw[k] is not None else None,
                   "weight": weights[k], "effective_weight": round(eff, 2),
                   "applicable": used,
                   "points": round((raw[k] or 0) * eff, 2) if used else 0.0,
                   "note": None if used else (
                       "weight set to 0" if raw[k] is not None else "not specified in the job - excluded")}
        if used:
            overall += raw[k] * eff
    overall = round(max(0.0, min(100.0, overall)), 1)

    mand = [i for i in skill_items if i["level"] == "mandatory"]
    pref = [i for i in skill_items if i["level"] == "preferred"]
    matched_m = [i for i in mand if i["status"] in ("exact", "equivalent")]
    related_m = [i for i in mand if i["status"] in ("related", "partial")]
    missing_m = [i for i in mand if i["status"] == "missing"]
    matched_p = [i for i in pref if i["status"] in ("exact", "equivalent")]
    missing_p = [i for i in pref if i["status"] in ("missing", "related", "partial")]

    # ---- review reasons & verification suggestions
    review, verify = [], []
    if exp_info.get("required") and not exp_info.get("usable_dates", True):
        review.append("No usable employment dates - experience cannot be verified")
        verify.append("Ask for exact employment dates; experience was scored 0 because it is unverified"
                      + (f" (resume claims {exp_info['claimed_years']:g} years)." if exp_info.get("claimed_years") else "."))
    if edu_info.get("status") == "unverified":
        review.append("Education not detected")
        verify.append("Confirm the candidate's highest qualification.")
    if exp_info.get("has_title_only"):
        review.append("A role title resembles the job but the resume gives no supporting skills or duties")
    if matched_m and sum(1 for i in matched_m if i["unverified"]) * 2 >= len(matched_m):
        review.append("Most matched mandatory skills are only listed, not shown in work history")
    if not resume.get("name"):
        review.append("Candidate name not detected")
    if not resume.get("email") and not resume.get("phone"):
        review.append("No contact details found")
    if any(e.get("dates_ok") is False for e in resume.get("experience", [])):
        review.append("Some employment dates unreadable or invalid")
    if len(resume.get("text", "")) < 150:
        review.append("Very little text extracted from the resume")

    for i in missing_m:
        verify.append(f"Mandatory skill not evident: {i['display']} - ask whether they have it.")
    for i in related_m:
        verify.append(f"{i['display']} (mandatory): only related experience"
                      + (f" ({i['via']})" if i["via"] else "") + " - assess transferability.")
    for i in matched_m:
        if i["unverified"]:
            verify.append(f"{i['display']} is only listed in the skills section - ask for a project example.")
    if edu_info.get("status") in ("one level below", "below") and edu_info.get("mandatory"):
        verify.append(f"Education below the required {edu_info['required']}.")
    if exp_info.get("required") and exp_info.get("usable_dates", True) \
            and exp_info["relevant_years"] < exp_info["required"]:
        verify.append(f"Relevant experience {exp_info['relevant_years']:.1f} yrs vs "
                      f"{exp_info['required']:g} required - probe the gap.")
    for c in cert_items:
        if c["mandatory"] and not c["found"]:
            verify.append(f"Mandatory certification not found: {c['name']}.")

    # ---- reasons
    reasons = []
    if skill_items:
        reasons.append(
            f"Skills {cats['skills']['score']:.0f}%: {len(matched_m)} of {len(mand)} mandatory skills "
            f"matched" + (f" ({', '.join(i['display'] for i in matched_m)})" if matched_m else "")
            + ("; missing " + ", ".join(i["display"] for i in missing_m) if missing_m else "")
            + ("; related only: " + ", ".join(i["display"] for i in related_m) if related_m else "")
            + (f"; {len(matched_p)} of {len(pref)} preferred matched" if pref else "") + ".")
    else:
        reasons.append("No skills were defined in the job, so skills could not be scored.")
    if exp_info.get("required"):
        if exp_info.get("usable_dates"):
            miss = exp_info["missing_months"]
            reasons.append(
                f"Experience {cats['experience']['score']:.0f}%: relevant {exp_info['relevant_months']:g} months "
                f"(= {exp_info['relevant_years']:.1f} yrs) / required {exp_info['required_months']} months "
                f"(= {exp_info['required']:g} yrs) = {exp_info['match_pct']:g}%"
                + (f"; {miss:g} months short" if miss else "; requirement met")
                + f". Total experience is {exp_info['total_months']} months "
                  f"({exp_info['total_years']:.1f} yrs), but unrelated roles are not counted and "
                  f"overlapping months are counted once.")
        else:
            reasons.append("Experience 0%: no usable dates, so no experience could be verified.")
    if edu_info.get("required"):
        reasons.append(f"Education {cats['education']['score']:.0f}%: required {edu_info['required']}; "
                       f"candidate {edu_info.get('candidate') or 'not detected'}.")
    if resp_items:
        cov = sum(1 for r in resp_items if r["status"] == "covered")
        reasons.append(f"Responsibilities {cats['responsibilities']['score']:.0f}%: "
                       f"{cov} of {len(resp_items)} duties clearly evidenced in the resume.")
    if cert_items:
        reasons.append(f"Certifications {cats['certifications']['score']:.0f}%: "
                       f"{sum(1 for c in cert_items if c['found'])} of {len(cert_items)} found.")
    na = [CATEGORY_LABELS[k] for k, c in cats.items() if not c["applicable"]]
    if na:
        reasons.append("Not scored (excluded and weights redistributed): " + ", ".join(na) + ".")

    return {
        "overall": overall,
        "categories": cats,
        "skills": skill_items,
        "matched_mandatory": [i["display"] for i in matched_m],
        "related_mandatory": [i["display"] for i in related_m],
        "missing_mandatory": [i["display"] for i in missing_m],
        "matched_preferred": [i["display"] for i in matched_p],
        "missing_preferred": [i["display"] for i in missing_p],
        "profile": resume.get("profile"),
        "experience": exp_info,
        "education": edu_info,
        "responsibilities": resp_items,
        "certifications": cert_items,
        "reasons": reasons,
        "verify": list(dict.fromkeys(verify)),
        "needs_review": bool(review),
        "review_reasons": review,
        "disclaimer": "Estimate of job alignment to support a human decision - not proof of "
                      "qualification. Missing mandatory items are shown separately; no candidate "
                      "is rejected automatically.",
    }
