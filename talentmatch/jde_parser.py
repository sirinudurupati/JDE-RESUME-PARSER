"""Job description (JDE) -> structured requirements.

Nothing is invented: anything we are not confident about is added to
`flags` so HR can review it in the editor before matching.
"""
import re

from . import skills as sk
from .textutil import (BULLET_RE, NUMBER_WORDS, PREFERRED_RE, clean_line, edu_field,
                       edu_levels_in)

SECTION_HEADERS = [
    # keyword dumps, KPIs and application instructions repeat skills without saying how important
    # they are, so they must not override the real Required / Preferred sections
    ("other", re.compile(r"keywords?|key performance|kpi|application requirement|how to apply", re.I)),
    # soft skills can rarely be evidenced on a resume: treat as preferred, never as hard requirements
    ("preferred", re.compile(r"preferred|nice[- ]to[- ]have|good[- ]to[- ]have|bonus|desirable|"
                             r"additional skills|plus points|added advantage|soft skills", re.I)),
    ("responsibilities", re.compile(r"responsibilit|duties|what you.?ll do|key tasks|your role|"
                                    r"the role|day[- ]to[- ]day|what you will do|job duties|"
                                    r"roles? (?:&|and) responsibilit", re.I)),
    ("certifications", re.compile(r"certification|licen[sc]es?\b", re.I)),
    ("education", re.compile(r"education|academic", re.I)),
    ("required", re.compile(r"requirement|required|qualification|must[- ]have|looking for|"
                            r"what you.?ll bring|who you are|skills|mandatory|"
                            r"technical (?:skills|expertise)|competenc|experience$|"
                            r"what we expect|essential", re.I)),
    ("other", re.compile(r"about|benefit|perks|we offer|why join|compensation|salary|"
                         r"equal opportunity|how to apply|overview|summary|company|"
                         r"who we are|culture|location", re.I)),
]

CERT_PATTERNS = [
    # "a relevant Salesforce certification" -> "Salesforce certification"
    re.compile(r"\b[A-Z][\w+#.]*(?:\s+[A-Z][\w+#.]*){0,2}\s+certifications?\b"),
    re.compile(r"\bAWS\s+Certified\s+[A-Z][\w\- ]{2,40}", re.I),
    re.compile(r"\bAzure\s+(?:Fundamentals|Administrator|Developer|Solutions Architect|Data\s+\w+)\b[\w ]{0,20}", re.I),
    re.compile(r"\bGoogle\s+Cloud\s+(?:Certified|Professional)\s+[A-Z][\w\- ]{2,40}", re.I),
    re.compile(r"\bCertified\s+[A-Z][\w\-]*(?:\s+[A-Z][\w\-]*){0,4}", re.I),
    re.compile(r"\b(?:PMP|CISSP|CISM|CEH|CKA|CKAD|CCNA|CCNP|ITIL|CSM|PSM|CPA|SHRM-?CP|PHR|"
               r"Six Sigma(?: (?:Green|Black) Belt)?|Scrum Master)\b"),
]

_YEARS_RE = re.compile(
    r"(\d{1,2}(?:\.\d)?|" + "|".join(NUMBER_WORDS) + r")\s*\+?\s*(?:(?:-|to|–)\s*(\d{1,2})\s*\+?\s*)?"
    r"(?:years?|yrs?)\b", re.I)

TITLE_LABEL = re.compile(r"^\s*(?:job\s+title|position(?:\s+title)?|role|designation|title|"
                         r"opening|vacancy)\s*[:\-–]\s*(.+)$", re.I)
DEPT_LABEL = re.compile(r"^\s*(?:department|dept\.?|team|function|business\s+unit|division)\s*[:\-–]\s*(.+)$", re.I)
SKIP_TITLE = re.compile(r"^(?:job\s+description|jd|job\s+details?|job\s+posting|position\s+description|"
                        r"we are (?:hiring|looking)|about)\b", re.I)


def _header_of(line: str):
    """Return section key if `line` looks like a section heading, else None."""
    raw = line.strip()
    if not raw or len(raw) > 70:
        return None
    text = BULLET_RE.sub("", raw).strip().rstrip(":").strip()
    if not text or len(text.split()) > 8:
        return None
    if raw.endswith(".") or raw.endswith(","):
        return None
    looks_heading = raw.endswith(":") or text.isupper() or text.istitle() or len(text.split()) <= 4
    if not looks_heading:
        return None
    # a heading with an inline value ("Skills: Python, SQL") is handled by the caller
    for key, rx in SECTION_HEADERS:
        if rx.search(text):
            # "5+ years of experience in Python" is a requirement sentence, not a heading
            if re.search(r"\d", text) or len(text.split()) > 6:
                return None
            return key
    return None


def _split_inline(line: str):
    """'Required Skills: Python, SQL' -> (section_key, 'Python, SQL')."""
    m = re.match(r"^\s*([A-Za-z&/ '\-]{3,40}):\s*(\S.*)$", line)
    if not m:
        return None, None
    key = _header_of(m.group(1) + ":")
    return (key, m.group(2)) if key else (None, None)


def _num(s: str) -> float:
    s = s.lower()
    return float(NUMBER_WORDS[s]) if s in NUMBER_WORDS else float(s)


def parse_jde(text: str) -> dict:
    lines = [ln.rstrip() for ln in text.split("\n")]
    flags = []

    # ---- title / department
    title = dept = None
    for ln in lines[:25]:
        if title is None and (m := TITLE_LABEL.match(ln)):
            title = m.group(1).strip(" -:")
        if dept is None and (m := DEPT_LABEL.match(ln)):
            dept = m.group(1).strip(" -:")
    title_conf = "high"
    if not title:
        for ln in lines[:12]:
            t = ln.strip()
            if not t or SKIP_TITLE.match(t) or len(t) > 80 or _header_of(t):
                continue
            title = re.sub(r"\s*[|(].*$", "", t).strip() or t
            title_conf = "low"
            break
    if not title:
        flags.append("Job title could not be identified - please enter it.")
    elif title_conf == "low":
        flags.append(f"Job title '{title}' was guessed from the first line - please confirm.")
    if not dept:
        flags.append("Department not found - add it if relevant.")

    # ---- walk lines tracking sections
    section = None
    responsibilities, skill_items = [], {}
    free_skill_items = {}
    education_hits, cert_items = [], []
    exp_hits = []

    def add_skill(name, level, conf, source):
        cur = skill_items.get(name)
        new = {"name": name, "level": level, "confidence": conf, "source": source}
        if cur is None:
            skill_items[name] = new
        elif cur["source"] == "responsibilities" and source != "responsibilities":
            skill_items[name] = new          # an explicit requirement beats a duty mention
        elif source != "responsibilities" and level == "mandatory" and cur["level"] == "preferred":
            skill_items[name] = new

    group_no = [0]
    for raw in lines:
        if not raw.strip():
            continue
        key, rest = _split_inline(raw)
        if key:
            section, line = key, rest
        else:
            h = _header_of(raw)
            if h:
                section = h
                continue
            line = raw
        text_line = clean_line(line)
        if not text_line or section == "other":
            continue
        if TITLE_LABEL.match(text_line) or DEPT_LABEL.match(text_line):
            continue
        is_pref = section == "preferred" or bool(PREFERRED_RE.search(text_line))
        level = "preferred" if is_pref else "mandatory"

        # responsibilities
        if section == "responsibilities":
            responsibilities.append(text_line)

        # experience years
        for m in _YEARS_RE.finditer(text_line):
            if re.search(r"experience|exp\b|background|worked|working|hands[- ]on", text_line, re.I):
                hi = float(m.group(2)) if m.group(2) else None
                exp_hits.append((_num(m.group(1)), level, text_line, hi))
                break

        # education
        if section == "education" or re.search(r"degree|bachelor|master|b\.?tech|m\.?tech|diploma|"
                                               r"ph\.?d|b\.?sc|m\.?sc|\bmba\b|graduate", text_line, re.I):
            lv = edu_levels_in(text_line)
            if lv and section != "responsibilities":
                education_hits.append((min(lv), level, text_line))

        # certifications
        if section == "certifications":
            for part in re.split(r"[;,•]|\bor\b|\band\b(?=\s+[A-Z])", text_line):
                part = part.strip(" .")
                if 2 < len(part) < 70:
                    cert_items.append({"name": part, "level": level})
        else:
            for rx in CERT_PATTERNS:
                m = rx.search(text_line)
                if m:
                    name = m.group(0).strip(" .,")
                    if len(name) > 3 and not re.fullmatch(r"certified", name, re.I):
                        cert_items.append({"name": name, "level": level})
                    break

        # skills
        if section in ("required", "preferred", "responsibilities", "education", None):
            found = sk.find_skills(text_line)
            for canon in found:
                if section == "responsibilities":
                    # mentioned only in duties: keep, but ask HR to confirm the level
                    add_skill(canon, "mandatory", "medium", "responsibilities")
                else:
                    add_skill(canon, level, "high" if section else "medium",
                              section or "unsectioned")
            # "SQL, MySQL, PostgreSQL, or similar" / "Power BI or Tableau": any ONE of them will do
            if section != "responsibilities" and len(found) >= 2:
                body = text_line.split(":", 1)[1] if re.match(r"^[A-Za-z &/]{2,30}:", text_line) else text_line
                chunks = [c.strip() for c in re.split(r"[;,]", body) if c.strip()]
                if (chunks and all(len(c.split()) <= 4 for c in chunks)
                        and re.search(r"(?<![A-Za-z])or(?![A-Za-z])", body, re.I)):
                    group_no[0] += 1
                    for canon in sk.find_skills(body):
                        if canon in skill_items and skill_items[canon]["source"] != "responsibilities":
                            skill_items[canon]["group"] = f"g{group_no[0]}"
            # sentence form: "TensorFlow or PyTorch", "such as AWS, Azure, or Google Cloud".
            # Skills linked only by commas / "or" form one alternatives chain ("and" breaks it).
            if section != "responsibilities" and len(found) >= 2:
                spans = sorted((v[0][0], v[0][1], canon) for canon, v in found.items())
                chain = [spans[0]]
                chains = []
                for prev, cur in zip(spans, spans[1:]):
                    link = text_line[prev[1]:cur[0]]
                    if re.fullmatch(r"\s*,?\s*(?:or\s+)?", link):
                        chain.append(cur)
                        if "or" in link:
                            chain.append(None)           # marks "contains or"
                    else:
                        chains.append(chain)
                        chain = [cur]
                chains.append(chain)
                for ch in chains:
                    members = [c for c in ch if c]
                    if None in ch and len(members) >= 2:
                        if not any(skill_items.get(m[2], {}).get("group") for m in members):
                            group_no[0] += 1
                            for m in members:
                                if m[2] in skill_items and skill_items[m[2]]["source"] != "responsibilities":
                                    skill_items[m[2]]["group"] = f"g{group_no[0]}"
            # free-text skill lists, e.g. "Skills: stakeholder communication, API testing"
            listy = section in ("required", "preferred") or (section is None and BULLET_RE.match(raw))
            if listy and (key or re.match(r"^[\w+#./ \-]+(?:,|;|/)", text_line)):
                if "," in text_line or ";" in text_line:
                    for item in re.split(r"[;,]", text_line):
                        item = re.sub(r"^(?:and|or|with|including|etc\.?)\s+", "", item.strip(" ."), flags=re.I)
                        words = item.split()
                        if (1 <= len(words) <= 3 and len(item) >= 3
                                and not sk.find_skills(item)
                                and not re.search(r"year|degree|experience|ability|knowledge|"
                                                  r"understanding|bachelor|master|certif|qualification|"
                                                  r"project|similar|equivalent|etc|preferred|and$|or$",
                                                  item, re.I)):
                            free_skill_items.setdefault(
                                item.lower(), {"name": item.lower(), "level": level,
                                               "confidence": "low", "source": section})

    for name, item in free_skill_items.items():
        if name not in skill_items:
            skill_items[name] = item

    # ---- experience
    min_years, exp_level, max_years = None, "mandatory", None
    if exp_hits:
        mand = [h for h in exp_hits if h[1] == "mandatory"]
        pick = (mand or exp_hits)[0]
        min_years, exp_level = pick[0], pick[1]
        if pick[3] and pick[3] > pick[0]:
            max_years = pick[3]
        distinct = {h[0] for h in exp_hits}
        if len(distinct) > 1:
            flags.append("Several different experience figures found ("
                         + ", ".join(f"{v:g}" for v in sorted(distinct))
                         + " years) - the first mandatory one was used; please confirm.")
    else:
        flags.append("No minimum years of experience found - experience will not be scored "
                     "unless you enter it.")

    # ---- education
    education = None
    if education_hits:
        mand = [h for h in education_hits if h[1] == "mandatory"]
        rank, lvl, src = (mand or education_hits)[0]
        education = {"min_level": rank, "mandatory": lvl == "mandatory",
                     "field": edu_field(text) if edu_field(src) is None else edu_field(src),
                     "source": src[:160]}
    else:
        flags.append("No education requirement found - education will not be scored unless you add one.")

    # ---- certifications (dedupe)
    certs, seen = [], set()
    for c in cert_items:
        k = re.sub(r"[^a-z0-9]", "", c["name"].lower())
        if k and k not in seen:
            seen.add(k)
            certs.append({"name": c["name"], "mandatory": c["level"] == "mandatory"})

    # ---- skills: flags
    skill_list = sorted(skill_items.values(), key=lambda s: (s["level"] != "mandatory", s["name"]))
    if not skill_list:
        flags.append("No skills could be extracted - add the required skills manually.")
    for s in skill_list:
        if s["confidence"] == "low":
            flags.append(f"Skill '{s['name']}' is free text (not in the skill library) - "
                         "confirm it and whether it is mandatory.")
        elif s["source"] == "responsibilities":
            flags.append(f"'{sk.display(s['name'])}' appears only in the responsibilities - "
                         "confirm whether it is mandatory or preferred.")
    if not responsibilities:
        flags.append("No responsibilities section found - responsibilities will not be scored "
                     "unless you add them.")

    for s in skill_list:
        s["display"] = sk.display(s["name"]) if sk.canonical(s["name"]) == s["name"] else s["name"]

    return {
        "title": title or "",
        "department": dept or "",
        "responsibilities": responsibilities,
        "skills": [{"name": s["name"], "display": s["display"], "level": s["level"],
                    "confidence": s["confidence"], "group": s.get("group")} for s in skill_list],
        "min_experience_years": min_years,
        "max_experience_years": max_years,
        "experience_mandatory": exp_level == "mandatory",
        "education": education,
        "certifications": certs,
        "flags": list(dict.fromkeys(flags)),
    }
