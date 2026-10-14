"""Resume text -> structured candidate record.

Deliberately does NOT extract or use age, gender, religion, marital status,
photographs, nationality or similar attributes.
"""
import re
from datetime import date

from . import skills as sk
from .textutil import BULLET_RE, edu_field, edu_levels_in, EDU_LEVELS

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_MON = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
        r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?")
_DATE = rf"(?:(?:{_MON}|\d{{1,2}}[/.\-])[ ,]*)?(?:19|20)\d{{2}}"
_PRESENT = r"(?:present|current|currently|now|till\s+date|to\s+date|ongoing|date)"
RANGE_RX = re.compile(
    rf"(?<![\w/])({_DATE})\s*(?:-|–|—|to|until|till|through)\s*({_DATE}|{_PRESENT})(?![\w/])",
    re.I)

EMAIL_RX = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RX = re.compile(r"(?<![\w/])(\+?\d[\d\s().\-]{8,17}\d)(?![\w/])")
URL_RX = re.compile(r"(?:https?://)?(?:www\.)?(?:linkedin\.com|github\.com)/[\w\-./%]+", re.I)
NAME_BAD = re.compile(r"resume|curriculum|vitae|cv\b|@|\d|http|www\.|address|email|phone|mobile|"
                      r"profile|summary|objective|contact|developer|engineer|manager|analyst|"
                      r"consultant|designer|intern\b|student|experience|education|skills", re.I)


_HEAD_RULES = [
    # order matters: first match wins
    ("other", re.compile(r"soft skills|training|learning|declaration|languages?|hobbies|interests|references?|personal (?:details|information|profile)|extra[- ]?curricular|volunteer|strengths", re.I)),
    ("certifications", re.compile(r"certif|licen[sc]e|courses?(?![A-Za-z])", re.I)),
    ("other", re.compile(r"achievements?|awards?|honou?rs|publications?|accomplishments?", re.I)),
    ("education", re.compile(r"education|academic|qualification", re.I)),
    ("experience", re.compile(r"experience|internships?|employment|work history|career history|professional background", re.I)),
    ("projects", re.compile(r"projects?", re.I)),
    ("skills", re.compile(r"skills|competenc|technolog|tools|expertise|tech stack", re.I)),
    ("summary", re.compile(r"summary|objective|profile|about", re.I)),
]


def _section_of(line: str):
    """Return the section key if `line` looks like a section heading."""
    raw = BULLET_RE.sub("", line).strip()
    t = raw.rstrip(":").strip()
    if not t or len(t.split()) > 6 or len(t) > 55:
        return None
    if re.search(r"[|,.;()@\d]", t) or raw.endswith("."):
        return None
    if BULLET_RE.match(line):
        return None                      # bullets are content (e.g. "- Oracle Certified Professional")
    if not t.isupper() and not raw.endswith(":") and len(t.split()) > 3:
        return None                      # long Title Case lines are names/certs, not headings
    if not (t.isupper() or t.istitle() or raw.endswith(":") or len(t.split()) <= 2):
        return None
    for key, rx in _HEAD_RULES:
        if rx.search(t):
            return key
    return None


def split_sections(lines):
    """-> list of (section_key, [lines]) in order; first chunk is 'header'."""
    out = [("header", [])]
    for ln in lines:
        key = _section_of(ln) if ln.strip() else None
        if key:
            out.append((key, []))
        else:
            out[-1][1].append(ln)
    return out


def _parse_date(tok: str, today: date, is_end: bool):
    """-> (year, month, month_known) or None."""
    t = tok.strip().lower()
    if re.fullmatch(_PRESENT, t):
        return today.year, today.month, True
    m = re.search(rf"({_MON})[ ,]*((?:19|20)\d{{2}})", t)
    if m:
        return int(m.group(2)), MONTHS[m.group(1)[:3]], True
    m = re.fullmatch(r"(\d{1,2})[/.\-]\s*((?:19|20)\d{2})", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return int(m.group(2)), int(m.group(1)), True
    m = re.search(r"((?:19|20)\d{2})", t)
    if m:
        return int(m.group(1)), None, False
    return None


def parse_range(start_tok, end_tok, today):
    """-> dict(start_idx, end_idx, flags) in absolute month indices (inclusive) or None."""
    a = _parse_date(start_tok, today, False)
    b = _parse_date(end_tok, today, True)
    if not a or not b:
        return None
    flags = []
    sy, sm, sknown = a
    ey, em, eknown = b
    if not sknown or not eknown:
        flags.append("year-only dates: months assumed")
    if not sknown and not eknown and sy == ey:
        sm, em = 1, 12
    else:
        if not sknown:
            sm = 7
        if not eknown:
            em = 6
    s_idx, e_idx = sy * 12 + sm, ey * 12 + em
    cur = today.year * 12 + today.month
    if s_idx > cur:
        return {"invalid": "starts in the future"}
    if e_idx > cur:
        e_idx = cur
        flags.append("end date in the future: capped at today")
    if e_idx < s_idx:
        return {"invalid": "end date before start date"}
    return {"start": s_idx, "end": e_idx, "flags": flags}


def idx_to_str(i):
    y, m = divmod(i - 1, 12)
    return f"{y}-{m + 1:02d}"


def _is_header_line(ln: str) -> bool:
    c = ln.strip()
    return bool(c) and len(c) <= 80 and not BULLET_RE.match(ln) and not c.endswith((".", ";"))


ROLE_RX = re.compile(r"(?<![A-Za-z])(developer|engineer|intern(?:ship)?|analyst|manager|consultant|administrator|"
                     r"executive|trainee|lead|architect|designer|tester|scientist|specialist|associate|officer|"
                     r"head|director|programmer|assistant|coordinator|representative|apprentice|admin|"
                     r"scholar|researcher|technician|fellow)(?![A-Za-z])", re.I)
COMPANY_RX = re.compile(r"(?<![A-Za-z])(pvt|ltd|inc|llc|llp|corp|corporation|technologies|technology|solutions|"
                        r"labs?|systems|software|services|company|co\.|bank|university|institute|group|"
                        r"consulting|ai|analogy|infotech|softech)(?![A-Za-z])", re.I)
TYPE_RULES = [
    ("internship", re.compile(r"intern(?:ship)?(?![A-Za-z])|apprentice", re.I)),
    ("trainee", re.compile(r"trainee|graduate engineer trainee", re.I)),
    ("part_time", re.compile(r"part[- ]?time|freelanc|contract(?:or)?(?![A-Za-z])", re.I)),
    ("full_time", re.compile(r"full[- ]?time|permanent", re.I)),
]
EMPLOYMENT_TYPES = ["full_time", "part_time", "internship", "trainee", "unknown"]


def detect_employment_type(head: str) -> str:
    for key, rx in TYPE_RULES:
        if rx.search(head):
            return key
    return "unknown"


def split_title_company(pieces):
    """Heuristic split of header pieces into (job_title, company). Either may be None."""
    parts = []
    for p in pieces:
        p = BULLET_RE.sub("", p).strip(" •●-")
        for q in re.split(r"\s*\|\s*|\s+[-–—]\s+|\s+at\s+|\s+@\s+", p):
            q = q.strip(" ,;:-")
            if q:
                parts.append(q)
    title = next((p for p in parts if ROLE_RX.search(p) and not COMPANY_RX.search(p)), None) \
        or next((p for p in parts if ROLE_RX.search(p)), None)
    rest = [p for p in parts if p != title]
    company = next((p for p in rest if COMPANY_RX.search(p)), None) or (rest[0] if rest else None)
    if company and re.fullmatch(r"\d+\s*(?:months?|years?|yrs?)", company, re.I):
        company = None
    return title, company


def entry_details(text: str, head_pieces):
    """Skills used, duties and type for one job-history entry."""
    skills = sorted(sk.find_skills(text))
    duties = []
    for ln in text.split("\n"):
        if BULLET_RE.match(ln) and len(ln.strip()) > 12:
            duties.append(re.sub(r"\s+", " ", BULLET_RE.sub("", ln)).strip()[:220])
    title, company = split_title_company(head_pieces)
    return {"job_title": title, "company": company, "skills": skills,
            "responsibilities": duties[:8],
            "employment_type": detect_employment_type(" ".join(head_pieces)[:240])}


def overlaps_and_gaps(entries):
    """Informational only: which dated roles overlap, and unemployed gaps (never penalised)."""
    dated = [(i, e) for i, e in enumerate(entries) if e.get("dates_ok")]
    overlaps = []
    for a in range(len(dated)):
        for b in range(a + 1, len(dated)):
            (i, x), (j, y) = dated[a], dated[b]
            lo, hi = max(x["start"], y["start"]), min(x["end"], y["end"])
            if hi >= lo:
                overlaps.append({"a": x["title"][:60], "b": y["title"][:60], "months": hi - lo + 1})
    months = sorted(merged_months(entries))
    gaps = []
    for prev, cur in zip(months, months[1:]):
        if cur - prev > 2:                       # 2+ empty calendar months
            gaps.append({"from": idx_to_str(prev + 1), "to": idx_to_str(cur - 1), "months": cur - prev - 1})
    return overlaps, gaps


def parse_experience(lines, today):
    """Find dated entries. -> (entries, flags).

    Each date-range line starts an entry. Up to two short non-bullet lines directly
    above a date line are treated as that entry's title/company header."""
    flags, entries = [], []
    date_idx = [i for i, ln in enumerate(lines) if RANGE_RX.search(ln)]
    starts = []                      # first line index of each entry (incl. header)
    for n, i in enumerate(date_idx):
        floor = date_idx[n - 1] + 1 if n else 0
        h = i
        while h - 1 >= floor and i - h < 2 and _is_header_line(lines[h - 1]):
            h -= 1
        starts.append(h)
    for n, i in enumerate(date_idx):
        stop = starts[n + 1] if n + 1 < len(starts) else len(lines)
        header = [ln.strip() for ln in lines[starts[n]:i]]
        m = RANGE_RX.search(lines[i])
        rest = (lines[i][:m.start()] + " " + lines[i][m.end():]).strip(" |,-–@()")
        title = " | ".join(header + ([rest] if rest else [])) or "(untitled)"
        entry = {"title": title[:160], "text": "\n".join(lines[starts[n]:stop]),
                 "raw_dates": f"{m.group(1)} - {m.group(2)}"}
        body = "\n".join(lines[i + 1:stop])
        entry["body"] = body[:4000]
        entry.update(entry_details(body, header + ([rest] if rest else [])))
        pr = parse_range(m.group(1), m.group(2), today)
        if pr is None:
            flags.append(f"Could not read dates for '{title[:50]}'.")
            entry["dates_ok"] = False
        elif "invalid" in pr:
            flags.append(f"Dates for '{title[:50]}' look invalid ({pr['invalid']}); entry not counted.")
            entry["dates_ok"] = False
        else:
            entry.update(dates_ok=True, start=pr["start"], end=pr["end"], date_flags=pr["flags"])
            for f in pr["flags"]:
                flags.append(f"'{title[:50]}': {f}.")
        entries.append(entry)
    return entries, flags


def merged_months(entries, predicate=None):
    months = set()
    for e in entries:
        if e.get("dates_ok") and (predicate is None or predicate(e)):
            months.update(range(e["start"], e["end"] + 1))
    return months


def _find_name(lines):
    for ln in lines[:10]:
        t = ln.strip().strip("|,-")
        if not t or NAME_BAD.search(t) or _section_of(t):
            continue
        words = t.split()
        if 2 <= len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            return " ".join(w if w.isupper() is False else w.capitalize() for w in words)
    return None


def _find_phone(text):
    for m in PHONE_RX.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if 10 <= len(digits) <= 13 and not re.fullmatch(r"(?:19|20)\d{2}\D*(?:19|20)\d{2}", m.group(1)):
            return m.group(1).strip()
    return None


SCHOOL_RX = re.compile(r"\b(?:ssc|s\.s\.c|hsc|cbse|icse|isc|secondary|intermediate|high school|"
                       r"10th|12th|x{1,2}th|class\s*1[02]|matriculation|junior college|jr\.? college)\b", re.I)
YEAR_RX = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
CERT_JUNK_RX = re.compile(r"finalist|winner|runner|hackathon|champion|prize|rank\b|captain|"
                          r"^(?:learned|worked|gained|completed\s+[a-z ]*training\.?$)", re.I)
DURATION_RX = re.compile(r"\b(intern(?:ship)?|trainee|apprentice|engineer|developer|analyst|consultant|"
                         r"administrator|associate|executive|programmer|designer|tester)\b.*?"
                         r"(\d{1,2}(?:\.\d)?)\s*(months?|mos?|years?|yrs?)\b", re.I)


def parse_education(lines, today):
    """-> dict with highest degree, graduation year and per-degree list.
    School-level entries (10th/12th) are ignored for the 'highest' choice."""
    degrees = []
    for i, ln in enumerate(lines):
        if not ln.strip() or SCHOOL_RX.search(ln):
            continue
        lv = edu_levels_in(ln)
        if not lv:
            continue
        years = [int(y) for y in YEAR_RX.findall(ln)]
        j = i + 1
        while not years and j < len(lines) and j <= i + 2:
            if edu_levels_in(lines[j]):
                break
            years = [int(y) for y in YEAR_RX.findall(lines[j])]
            j += 1
        degrees.append({"rank": max(lv), "label": EDU_LEVELS[max(lv)],
                        "text": re.sub(r"\s+", " ", BULLET_RE.sub("", ln)).strip()[:140],
                        "year": max(years) if years else None})
    best = None
    for d in degrees:
        if best is None or (d["rank"], d["year"] or 0) > (best["rank"], best["year"] or 0):
            best = d
    year = best["year"] if best else None
    return {"degrees": degrees[:6], "highest": best,
            "graduation_year": year,
            "graduation_expected": bool(year and year > today.year)}


def parse_stated_durations(lines):
    """Roles that state a length ("Intern | Acme | 2 Months") but give no dates."""
    out = []
    for ln in lines:
        if RANGE_RX.search(ln) or len(ln) > 160:
            continue
        m = DURATION_RX.search(ln)
        if m:
            n = float(m.group(2))
            months = n * 12 if m.group(3).lower().startswith(("y",)) else n
            if 0 < months <= 120:
                out.append({"title": re.sub(r"\s+", " ", BULLET_RE.sub("", ln)).strip()[:140],
                            "months": round(months, 1)})
    return out


def clean_certifications(lines):
    out = []
    for l in lines:
        c = re.sub(r"\s+", " ", BULLET_RE.sub("", l)).strip(" ●•-")
        if 3 < len(c) < 140 and not CERT_JUNK_RX.search(c) and not (c.isupper() and _section_of(c)):
            out.append(c)
    return list(dict.fromkeys(out))[:15]


def parse_resume(text: str, today: date = None) -> dict:
    today = today or date.today()
    lines = [ln.rstrip() for ln in text.split("\n")]
    flags = []
    sections = split_sections(lines)
    by_sec = {}
    for key, ls in sections:
        by_sec.setdefault(key, []).extend(ls)

    name = _find_name(lines)
    emails = EMAIL_RX.findall(text)
    email = emails[0].lower() if emails else None
    phone = _find_phone(text)
    links = list(dict.fromkeys(m.group(0) for m in URL_RX.finditer(text)))[:3]
    if not name:
        flags.append("Candidate name could not be identified.")
    if not email and not phone:
        flags.append("No contact details found.")

    # ---- experience
    if "experience" in by_sec:
        exp_lines = by_sec["experience"]
    else:
        exp_lines = []
        for key, ls in sections:
            if key in ("header", "summary", "other", "skills", "projects"):
                exp_lines.extend(ls)
    entries, eflags = parse_experience(exp_lines, today)
    flags.extend(eflags)
    stated = parse_stated_durations([l for key, ls in sections if key not in ("education",) for l in ls])
    if not any(e.get("dates_ok") for e in entries):
        flags.append("No dated work experience found - treated as a fresher unless the resume says otherwise."
                     if not stated else
                     "Only stated durations (no dates) found for work/internships - not counted as verified experience.")
    months = merged_months(entries)
    # sum of individual durations vs merged -> overlap detection
    raw_total = sum(e["end"] - e["start"] + 1 for e in entries if e.get("dates_ok"))
    overlap_months = max(0, raw_total - len(months))
    if overlap_months:
        flags.append(f"Overlapping employment periods (~{overlap_months} months) counted once.")
    overlaps, gaps = overlaps_and_gaps(entries)

    claimed = None
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:total\s+|professional\s+|relevant\s+|work\s+)?experience", text, re.I)
    if m:
        claimed = float(m.group(1))

    # ---- skills (whole document) with evidence
    # blank out emails/URLs (same length) so "github.com/x" is not read as a GitHub skill
    skill_text = URL_RX.sub(lambda m: " " * len(m.group(0)),
                            EMAIL_RX.sub(lambda m: " " * len(m.group(0)), text))
    skill_pos = sk.find_skills(skill_text)
    ctx_text = "\n".join(e["text"] for e in entries) + "\n" + "\n".join(by_sec.get("projects", []))
    ctx_skills = set(sk.find_skills(ctx_text))
    skill_found = {}
    for canon, spans in skill_pos.items():
        s0 = spans[0][0]
        ls = text.rfind("\n", 0, s0) + 1
        le = text.find("\n", s0)
        snippet = text[ls: le if le != -1 else len(text)].strip()
        # prefer a snippet from experience/project context
        if canon in ctx_skills:
            for ln in (ctx_text.split("\n")):
                if canon in sk.find_skills(ln):
                    snippet = ln.strip()
                    break
        skill_found[canon] = {"evidenced": canon in ctx_skills, "snippet": re.sub(r"\s+", " ", snippet)[:200]}

    # ---- education
    edu_lines = by_sec.get("education", [])
    edu = parse_education(edu_lines or lines, today)
    hi = edu["highest"]
    education = {
        "highest_rank": hi["rank"] if hi else None,
        "highest_label": hi["label"] if hi else None,
        "field": edu_field(" ".join(edu_lines) if edu_lines else text),
        "labelled_section": bool(edu_lines),
        "lines": [d["text"] for d in edu["degrees"]][:5],
        "degrees": edu["degrees"],
        "graduation_year": edu["graduation_year"],
        "graduation_expected": edu["graduation_expected"],
    }
    if not hi:
        flags.append("No education qualification detected.")
    elif not edu_lines:
        flags.append("Education found outside a labelled section - verify.")
    if hi and not edu["graduation_year"]:
        flags.append("Graduation year could not be found.")

    certs = clean_certifications(by_sec.get("certifications", []))

    projects = [re.sub(r"\s+", " ", BULLET_RE.sub("", l)).strip()[:200]
                for l in by_sec.get("projects", []) if l.strip()][:15]

    return {
        "name": name, "email": email, "phone": phone, "links": links,
        "skills": skill_found,
        "experience": entries,
        "overlaps": overlaps, "gaps": gaps,
        "total_months": len(months),
        "total_years": round(len(months) / 12, 2),
        "claimed_years": claimed,
        "education": education,
        "certifications": certs,
        "projects": projects,
        "stated_experience": stated,
        "stated_months": round(sum(x["months"] for x in stated), 1),
        "profile": {
            "graduation_year": education["graduation_year"],
            "graduation_expected": education["graduation_expected"],
            "highest_education": (hi["label"] + (f" ({hi['text'][:60]})" if hi else "")) if hi else None,
            "experience_years": round(len(months) / 12, 2),
            "stated_months": round(sum(x["months"] for x in stated), 1),
            "fresher": not months and not stated,
            "roles": [e["title"] for e in entries if e.get("dates_ok")][:8],
            "certifications": certs,
        },
        "flags": list(dict.fromkeys(flags)),
        "text": text,
        "month_range": (idx_to_str(min(months)), idx_to_str(max(months))) if months else None,
    }
