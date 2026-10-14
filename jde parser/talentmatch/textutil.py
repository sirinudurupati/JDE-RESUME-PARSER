"""Small shared text helpers (education levels, tokenising, bullets)."""
import re

BULLET_RE = re.compile(r"^\s*(?:[-*•●▪◦‣⁃–—>]|\d{1,2}[.)])\s+")

EDU_LEVELS = {1: "Diploma", 2: "Bachelor's degree", 3: "Master's degree", 4: "Doctorate"}

_EDU_PATTERNS = [
    (4, re.compile(r"\b(?:ph\.?\s?d\.?|doctorate|doctoral)\b", re.I)),
    (3, re.compile(r"\b(?:master'?s?(?:\s+(?:of|in|degree)\b)|masters\b|master'?s\b|m\.?\s?tech\b|"
                   r"m\.?\s?sc\b|m\.?\s?eng\b|m\.?\s?c\.?a\b|mba\b|m\.?\s?e\.\s|post[- ]?graduate)", re.I)),
    (2, re.compile(r"\b(?:bachelor'?s?|b\.?\s?tech\b|b\.?\s?e\.\s|b\.?\s?sc\b|b\.?\s?eng\b|"
                   r"b\.?\s?c\.?a\b|b\.?\s?com\b|b\.?\s?a\.\s|undergraduate|b\.?\s?s\.\s|"
                   r"degree\s+in|university\s+degree|college\s+degree|engineering\s+degree)", re.I)),
    (1, re.compile(r"\b(?:diploma|associate'?s?\s+degree)\b", re.I)),
]

FIELDS = ["computer science", "information technology", "software engineering", "data science",
          "computer engineering", "electronics", "electrical engineering", "mathematics",
          "statistics", "information systems", "engineering", "business administration"]

PREFERRED_RE = re.compile(
    r"\b(?:preferred|nice[- ]to[- ]have|good[- ]to[- ]have|bonus|desirable|a plus|is a plus|"
    r"an advantage|advantageous|optional|would be (?:a )?(?:plus|nice|great)|ideally)\b", re.I)


def edu_levels_in(text: str):
    """All education ranks mentioned in text."""
    return sorted({rank for rank, rx in _EDU_PATTERNS if rx.search(text)})


def edu_field(text: str):
    low = text.lower()
    for f in FIELDS:
        if f in low:
            return f.title()
    return None


STOPWORDS = set("""a an the and or of to in on for with by at from as is are be been being this that these
those it its we you your our their they he she i will would should can could may might must shall
have has had do does did not no yes if then than so such other any all each every more most also
including include includes etc using use used within across into over under per via about able
good strong excellent team teams work working works role candidate candidates job position company
experience experienced years year month months ability knowledge understanding skills skill plus
responsible responsibilities responsibility required requirement requirements preferred need needs
new high level well based related relevant various multiple key
""".split())

GENERIC_VERBS = set("""build develop design implement create maintain ensure support manage write participate
contribute collaborate drive deliver provide perform handle lead help improve""".split())


def stem(word: str) -> str:
    w = word.lower()
    for suf in ("ations", "ation", "ments", "ment", "ities", "ity", "ing", "ies", "ied", "ers",
                "er", "ed", "es", "s"):
        if len(w) > len(suf) + 3 and w.endswith(suf):
            w = w[: -len(suf)]
            if suf in ("ies", "ied"):
                w += "y"
            break
    return w


def content_stems(text: str):
    """Set of meaningful word stems from text (stopwords/generic verbs removed)."""
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9+#]*", text):
        lw = w.lower()
        if lw in STOPWORDS or lw in GENERIC_VERBS or len(lw) < 3:
            continue
        out.add(stem(lw))
    return out


def clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", BULLET_RE.sub("", line)).strip()


NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
                "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15}
