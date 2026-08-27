"""
education.py
------------
Extracts education records from resume text.

This is part of the extraction layer.  It operates preferentially on the
``education`` section produced by ``extractor.sections``, falling back to a
conservative scan of the full text when no education section is detected.

Design philosophy
-----------------
- Deterministic: only regex + line-position heuristics.  No ML.
- Conservative: prefer returning fewer confident records over many guessed ones.
- Consistent schema: every record always contains the same six keys.
- Section-aware: ``sections["education"]`` is preferred over full-text scan.

Output schema (per record)
--------------------------
{
    "degree":        str | None,   # e.g. "B.Tech in Computer Engineering"
    "institution":   str | None,   # e.g. "ABC University"
    "dates":         str | None,   # e.g. "2023 - 2027"
    "field_of_study": str | None,  # e.g. "Computer Engineering"
    "grade":         str | None,   # e.g. "CGPA: 9.2" (verbatim)
    "location":      str | None,   # reserved; extracted only when explicit
}

Public API
----------
extract_education(text, sections=None) -> list[dict[str, str | None]]
"""

from __future__ import annotations

import re
from copy import deepcopy

# ---------------------------------------------------------------------------
# Degree vocabulary
# ---------------------------------------------------------------------------
# Patterns are tried case-insensitively.  Order matters within alternatives
# (longer/more specific first).  Add new patterns by extending the list.
# ---------------------------------------------------------------------------

_DEGREE_PATTERNS: list[str] = [
    # ── Doctoral ────────────────────────────────────────────────────────
    r"Doctor\s+of\s+Philosophy",
    r"(?<![A-Za-z])Ph\.?D\.?(?![A-Za-z])",
    # ── Master's ─────────────────────────────────────────────────────────
    r"Master\s+of\s+(?:Technology|Engineering|Science|Arts|Commerce|Business\s+Administration|Computer\s+Applications|Computer\s+Science)",
    r"(?<![A-Za-z])M\.?Tech\.?(?![A-Za-z])",
    r"(?<![A-Za-z])M\.?E\.?(?![A-Za-z])",
    r"(?<![A-Za-z])M\.?Sc\.?(?![A-Za-z])",
    r"(?<![A-Za-z])M\.?C\.?A\.?(?![A-Za-z])",
    r"(?<![A-Za-z])M\.?B\.?A\.?(?![A-Za-z])",
    r"(?<![A-Za-z])M\.?S\.?(?![A-Za-z])",
    # ── Bachelor's ───────────────────────────────────────────────────────
    r"Bachelor\s+of\s+(?:Technology|Engineering|Science|Arts|Commerce|Business\s+Administration|Computer\s+Applications|Computer\s+Science|Information\s+Technology)",
    r"(?<![A-Za-z])B\.?Tech\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?E\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?Sc\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?C\.?A\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?B\.?A\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?C\.?S\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?Com\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?A\.?(?![A-Za-z])",
    r"(?<![A-Za-z])B\.?S\.?(?![A-Za-z])",
    # ── Diploma / Secondary ──────────────────────────────────────────────
    r"Diploma(?:\s+in\s+\w[\w\s]*)?",
    r"Higher\s+Secondary(?:\s+Certificate)?",
    r"(?<![A-Za-z])H\.?S\.?C\.?(?![A-Za-z])",
    r"(?<![A-Za-z])S\.?S\.?C\.?(?![A-Za-z])",
    r"Secondary\s+School\s+Certificate",
    r"10\+?2",
    r"12th(?:\s+(?:Grade|Standard|Class))?",
    r"10th(?:\s+(?:Grade|Standard|Class))?",
    r"Class\s+(?:XII|XII|X|XI)",
    r"Grade\s+(?:XII|XI|X)",
]

# Combined into one big alternation for efficiency; each group is non-capturing.
_DEGREE_COMBINED_RE = re.compile(
    r"(?:" + "|".join(f"(?:{p})" for p in _DEGREE_PATTERNS) + r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Institution signals
# ---------------------------------------------------------------------------

# Lines containing these keywords (whole-word, case-insensitive) are strong
# institution candidates.
_INSTITUTION_KEYWORDS_RE = re.compile(
    r"\b(?:university|universities|institute|institution|college|school|academy|"
    r"polytechnic|faculty|campus|vidyalaya|vidyapeeth|mahavidyalaya|iit|nit|"
    r"iiit|bits|iim|mit|deemed)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

# Captures spans like:
#   2023 - 2027  |  2023–2027  |  Aug 2023 - May 2027  |  2023 - Present
_DATE_SPAN_RE = re.compile(
    r"(?:"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?\d{4}"
    r"\s*[-–—to]+\s*"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?(?:\d{4}|Present|Ongoing|Current)"
    r")",
    re.IGNORECASE,
)

# A single year (4 digits, 1950–2035)
_YEAR_RE = re.compile(r"\b((?:19[5-9]\d|20[0-3]\d))\b")

# ---------------------------------------------------------------------------
# Grade / score patterns
# ---------------------------------------------------------------------------

_GRADE_RE = re.compile(
    r"(?:"
    r"CGPA\s*[:\-]?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?"
    r"|GPA\s*[:\-]?\s*\d+(?:\.\d+)?(?:\s*/\s*\d+(?:\.\d+)?)?"
    r"|Percentage\s*[:\-]?\s*\d+(?:\.\d+)?\s*%?"
    r"|Score\s*[:\-]?\s*\d+(?:\.\d+)?\s*%?"
    r"|Marks\s*[:\-]?\s*\d+(?:\.\d+)?\s*%?"
    r"|\d+(?:\.\d+)?\s*%"          # bare percentage  e.g.  91%
    r")",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Field-of-study separator patterns
# ---------------------------------------------------------------------------
# Matches "in X", "- X", "(X)", "– X", ", X" that follow a degree token.
# X is captured in group 1.
_FIELD_OF_STUDY_RE = re.compile(
    r"(?:\bin\b\s+|\s*[\-–(,]\s*)([A-Za-z][A-Za-z\s&/\-\.]{2,50})",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Lines to skip when looking for institutions
# ---------------------------------------------------------------------------
_SKIP_LINE_RE = re.compile(
    r"^\s*(?:"
    r"CGPA|GPA|Percentage|Score|Marks|Grade|Location|City|"
    r"Summary|Profile|Skills|Experience|Projects|Achievements|"
    r"Certifications|Languages|Interests|References|Contact|"
    r"Phone|Email|Mobile|LinkedIn|GitHub|Address"
    r")\b",
    re.IGNORECASE,
)

# A line that looks like it is mainly a date
_DATE_ONLY_LINE_RE = re.compile(
    r"^\s*(?:"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+)?"
    r"\d{4}\s*(?:[-–—to]\s*(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\.?\s+)?(?:\d{4}|Present|Ongoing|Current))?"
    r"\s*$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helper: blank record
# ---------------------------------------------------------------------------

def _blank_record() -> dict[str, str | None]:
    return {
        "degree": None,
        "institution": None,
        "dates": None,
        "field_of_study": None,
        "grade": None,
        "location": None,
    }


def _record_key(rec: dict[str, str | None]) -> tuple[str, str]:
    """Normalised key used for deduplication."""
    deg = (rec.get("degree") or "").strip().lower()
    inst = (rec.get("institution") or "").strip().lower()
    return (deg, inst)


def _is_valid_record(rec: dict[str, str | None]) -> bool:
    """A record must have a degree to be included.

    Institution-only records (degree=None) are too unreliable — a plain
    sentence that happens to look 'institution-like' would create a false
    positive.  Requiring a degree is the conservative approach.
    """
    deg = rec.get("degree") or ""
    if not deg or len(deg.strip()) < 3:
        return False
    return True


# ---------------------------------------------------------------------------
# Core parsing helpers
# ---------------------------------------------------------------------------

def _extract_degree_from_line(line: str) -> tuple[str | None, str | None]:
    """
    Attempt to extract a degree token and optional field-of-study from *line*.

    Returns
    -------
    (degree_text, field_of_study) — either or both may be None.
    """
    m = _DEGREE_COMBINED_RE.search(line)
    if not m:
        return None, None

    # Full matched degree token
    degree_token = m.group(0).strip()

    # Try to find field of study after the degree token
    remainder = line[m.end():]
    fos_match = _FIELD_OF_STUDY_RE.match(remainder)
    field_of_study: str | None = None
    if fos_match:
        fos_raw = fos_match.group(1).strip().rstrip(")")
        # Discard if it looks like a date
        if not _YEAR_RE.search(fos_raw) and len(fos_raw) > 1:
            field_of_study = fos_raw

    # Build full degree text (token + " in <field>" if present)
    if field_of_study:
        degree_text = f"{degree_token} in {field_of_study}"
    else:
        # Check if the original line has "in <something>" before the remainder
        in_match = re.search(
            r"\bin\s+([A-Za-z][A-Za-z\s&/\-\.]{2,50})", line, re.IGNORECASE
        )
        if in_match:
            fos_candidate = in_match.group(1).strip().rstrip(")")
            if not _YEAR_RE.search(fos_candidate):
                field_of_study = fos_candidate
                degree_text = f"{degree_token} in {field_of_study}"
            else:
                degree_text = degree_token
        else:
            degree_text = degree_token

    return degree_text, field_of_study


def _extract_grade_from_line(line: str) -> str | None:
    m = _GRADE_RE.search(line)
    return m.group(0).strip() if m else None


def _extract_dates_from_line(line: str) -> str | None:
    m = _DATE_SPAN_RE.search(line)
    if m:
        return m.group(0).strip()
    # Single year fallback
    m2 = _YEAR_RE.search(line)
    if m2:
        return m2.group(0)
    return None


def _is_institution_candidate(line: str) -> bool:
    """
    Return True if *line* looks like it could be an institution name.

    Does NOT require institution keywords — a clean capitalised line near a
    degree is also acceptable.
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 3 or len(stripped) > 120:
        return False
    if _SKIP_LINE_RE.match(stripped):
        return False
    if _GRADE_RE.search(stripped):
        return False
    if _DATE_ONLY_LINE_RE.match(stripped):
        return False
    if _DEGREE_COMBINED_RE.search(stripped):
        return False  # degree lines are not institutions
    # Must not be a long sentence (institutions rarely exceed 8 words)
    words = stripped.split()
    if len(words) > 8:
        return False
    # Must be mostly alphabetic
    alpha = sum(c.isalpha() for c in stripped)
    if alpha / len(stripped) < 0.45:
        return False
    return True


def _institution_confidence(line: str) -> int:
    """Higher = more likely to be an institution.  Used to break ties."""
    score = 0
    if _INSTITUTION_KEYWORDS_RE.search(line):
        score += 3
    # Title-case words are a good signal
    words = line.strip().split()
    if all(w[0].isupper() for w in words if w and w[0].isalpha()):
        score += 1
    return score


# ---------------------------------------------------------------------------
# Entry grouper
# ---------------------------------------------------------------------------

def _group_lines_into_entries(lines: list[str]) -> list[list[str]]:
    """
    Heuristically group a list of clean lines into individual education entries.

    A new entry is started whenever a degree pattern is detected.
    Lines before the first degree are collected and associated with it if
    they contain institution-like content.

    Returns
    -------
    list of groups, where each group is a list of related lines.
    """
    groups: list[list[str]] = []
    current: list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Blank lines are entry boundaries only when the current group
            # already has content and the NEXT non-blank line starts a new entry.
            # We defer the decision — just mark with a sentinel.
            if current:
                current.append("")  # keep blank for structure awareness
            continue

        has_degree = bool(_DEGREE_COMBINED_RE.search(stripped))

        if has_degree and current:
            # Check if the current group already has a degree; if so, start new.
            existing_has_degree = any(
                _DEGREE_COMBINED_RE.search(l) for l in current if l.strip()
            )
            if existing_has_degree:
                groups.append(current)
                current = []

        current.append(stripped)

    if current:
        groups.append(current)

    # Remove empty-only groups
    return [g for g in groups if any(l.strip() for l in g)]


# ---------------------------------------------------------------------------
# Per-group record extractor
# ---------------------------------------------------------------------------

def _parse_group(group: list[str]) -> dict[str, str | None]:
    """
    Extract a single education record from a group of related lines.
    """
    record = _blank_record()
    institution_candidates: list[tuple[int, str]] = []  # (confidence, text)
    degree_found = False

    for line in group:
        stripped = line.strip()
        if not stripped:
            continue

        # ── Grade / Score ────────────────────────────────────────────────
        grade = _extract_grade_from_line(stripped)
        if grade and record["grade"] is None:
            record["grade"] = grade
            continue  # grade-only lines; skip other extraction for this line

        # ── Dates ────────────────────────────────────────────────────────
        dates = _extract_dates_from_line(stripped)
        if _DATE_ONLY_LINE_RE.match(stripped) and dates:
            if record["dates"] is None:
                record["dates"] = dates
            continue  # date-only line; skip further processing

        # ── Degree ───────────────────────────────────────────────────────
        degree_text, fos = _extract_degree_from_line(stripped)
        if degree_text:
            if not degree_found:
                record["degree"] = degree_text
                if fos and record["field_of_study"] is None:
                    record["field_of_study"] = fos
                degree_found = True
            # Even after degree found, extract dates from the same line
            if dates and record["dates"] is None:
                record["dates"] = dates
            continue

        # ── If not a grade / date-only / degree line, check institution ──
        if _is_institution_candidate(stripped):
            conf = _institution_confidence(stripped)
            institution_candidates.append((conf, stripped))
        # Also pull dates inline (e.g. "ABC University, 2020-2024")
        if dates and record["dates"] is None:
            record["dates"] = dates

    # Choose the best institution candidate
    if institution_candidates:
        # Sort by confidence descending, then take first
        institution_candidates.sort(key=lambda x: x[0], reverse=True)
        record["institution"] = institution_candidates[0][1]

    return record


# ---------------------------------------------------------------------------
# Inline / single-line formats  (Format E, F)
# ---------------------------------------------------------------------------

# Handles: "B.Tech, Computer Engineering — ABC University, 2023–2027"
# or:      "B.Tech | Computer Engineering | ABC University | 2023-2027"
_INLINE_SEP_RE = re.compile(r"[,|—–\-]{1,2}")


def _try_parse_inline(line: str) -> dict[str, str | None] | None:
    """
    Try to parse a single condensed line into a full education record.
    Returns None if the line doesn't look like an inline record.
    """
    if not _DEGREE_COMBINED_RE.search(line):
        return None

    # Split by common delimiters
    parts = [p.strip() for p in _INLINE_SEP_RE.split(line) if p.strip()]
    if len(parts) < 2:
        return None

    record = _blank_record()
    degree_done = False

    for part in parts:
        if not degree_done:
            deg, fos = _extract_degree_from_line(part)
            if deg:
                record["degree"] = deg
                record["field_of_study"] = fos
                degree_done = True
                continue

        if _GRADE_RE.search(part) and record["grade"] is None:
            record["grade"] = _extract_grade_from_line(part)
            continue

        dates = _extract_dates_from_line(part)
        if dates and record["dates"] is None:
            record["dates"] = dates
            continue

        if _is_institution_candidate(part) and record["institution"] is None:
            record["institution"] = part

    return record if _is_valid_record(record) else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_education(
    text: str,
    sections: dict[str, str] | None = None,
) -> list[dict[str, str | None]]:
    """
    Extract education records from resume text.

    Parameters
    ----------
    text:
        Full cleaned resume text (``str``).
    sections:
        Optional dict from ``extractor.sections.detect_sections``.
        If ``sections["education"]`` exists, it is used as the primary source.

    Returns
    -------
    list[dict[str, str | None]]
        List of education records.  Each record has the keys:
        ``degree``, ``institution``, ``dates``, ``field_of_study``,
        ``grade``, ``location``.
        Returns ``[]`` for empty input or when nothing can be confidently extracted.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_education() expects a str, got {type(text).__name__!r}."
        )

    # ── Choose input source ──────────────────────────────────────────────
    if sections and "education" in sections and sections["education"].strip():
        source = sections["education"]
    elif text.strip():
        source = text
    else:
        return []

    lines = [ln.strip() for ln in source.splitlines()]

    # ── Try inline / single-line formats first ───────────────────────────
    # If the entire section is one or two lines that contain a degree, handle inline.
    non_empty = [l for l in lines if l]
    inline_records: list[dict[str, str | None]] = []
    if len(non_empty) <= 3:
        for line in non_empty:
            r = _try_parse_inline(line)
            if r and _is_valid_record(r):
                inline_records.append(r)
        if inline_records:
            return _deduplicate(inline_records)

    # ── Group lines into entries and parse each group ────────────────────
    groups = _group_lines_into_entries(lines)
    records: list[dict[str, str | None]] = []

    for group in groups:
        record = _parse_group(group)
        if _is_valid_record(record):
            records.append(record)

    # ── Post-process: inline single-line detection for compact groups ────
    # Some formats cram everything on one line inside a larger section.
    if not records:
        for line in non_empty:
            r = _try_parse_inline(line)
            if r and _is_valid_record(r):
                records.append(r)

    return _deduplicate(records)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(
    records: list[dict[str, str | None]],
) -> list[dict[str, str | None]]:
    """
    Remove records that are exact duplicates by (degree, institution) key.
    Preserves document order.  First occurrence wins.
    """
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str | None]] = []
    for rec in records:
        key = _record_key(rec)
        if key not in seen:
            seen.add(key)
            result.append(deepcopy(rec))
    return result
