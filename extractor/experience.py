"""
experience.py
-------------
Extracts work/professional experience records from resume text.

This is part of the extraction layer.  It operates preferentially on the
``experience`` section produced by ``extractor.sections``, falling back to a
conservative scan of the full text when no section is detected.

Design philosophy
-----------------
- Deterministic: regex + line-position heuristics only.  No ML.
- Conservative: prefer returning fewer confident records over many guessed ones.
- Consistent schema: every record always contains the same five keys.
- Section-aware: ``sections["experience"]`` is preferred over full-text scan.

Output schema (per record)
--------------------------
{
    "job_title":   str | None,       # e.g. "Software Engineer Intern"
    "company":     str | None,       # e.g. "ABC Technologies"
    "dates":       str | None,       # e.g. "June 2024 - August 2025"
    "location":    str | None,       # e.g. "Mumbai, India"  (optional)
    "description": list[str],        # cleaned bullet points
}

Public API
----------
extract_experience(text, sections=None) -> list[dict[str, ...]]
"""

from __future__ import annotations

import re
from copy import deepcopy

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------

# Full span: "June 2024 - August 2025", "Jan 2023 – Present", "2024 - 2025"
# Also "01/2023 - 05/2024"
_DATE_SPAN_RE = re.compile(
    r"(?:"
    # Month-name or abbreviated month + year, range to month/year or keyword
    r"(?:(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+)?"
    r"\d{4}"
    r"\s*[-–—to/]+\s*"
    r"(?:(?:January|February|March|April|May|June|July|August|September|October|November|December"
    r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+)?"
    r"(?:\d{4}|Present|Current|Ongoing|Now)"
    r")"
    r"|"
    # MM/YYYY - MM/YYYY
    r"(?:\d{1,2}/\d{4}\s*[-–—]+\s*(?:\d{1,2}/\d{4}|Present|Current))"
    r"|"
    # Bare "Present" / "Current"
    r"(?:^|\b)(?:Present|Current)(?:\b|$)",
    re.IGNORECASE | re.MULTILINE,
)

# A line that is *only* a date (nothing else meaningful)
_DATE_ONLY_LINE_RE = re.compile(
    r"^\s*(?:"
    r"(?:(?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+)?"
    r"\d{4}"
    r"(?:\s*[-–—to]+\s*"
    r"(?:(?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+)?"
    r"(?:\d{4}|Present|Current|Ongoing|Now))?"
    r"|"
    r"\d{1,2}/\d{4}\s*[-–—]+\s*(?:\d{1,2}/\d{4}|Present|Current)"
    r")\s*$",
    re.IGNORECASE,
)

# A standalone 4-digit year (used to grab single-year dates)
_YEAR_RE = re.compile(r"\b((?:19[5-9]\d|20[0-3]\d))\b")

# ---------------------------------------------------------------------------
# Bullet markers
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^\s*[-•*▪●►◦]\s+", re.UNICODE)

# ---------------------------------------------------------------------------
# Job-title vocabulary / heuristics
# ---------------------------------------------------------------------------

# Known job-title words (used as positive signals — NOT as a whitelist).
_JOB_TITLE_KEYWORDS: frozenset[str] = frozenset({
    # engineering
    "engineer", "developer", "programmer", "architect", "lead", "senior",
    "junior", "associate", "principal", "staff",
    # roles
    "analyst", "scientist", "researcher", "designer", "consultant",
    "specialist", "manager", "director", "head", "officer", "executive",
    "coordinator", "administrator", "technician",
    # common modifiers
    "intern", "trainee", "freelance", "contractor", "independent",
    "full", "stack", "backend", "frontend", "mobile", "android", "ios",
    "cloud", "devops", "sre", "qa", "test", "data", "ml", "ai",
    "software", "web", "product", "project", "business", "system",
    "network", "security", "embedded", "hardware",
})

# Words that strongly suggest a line is NOT a job title
_NOT_TITLE_WORDS: frozenset[str] = frozenset({
    "skills", "education", "experience", "projects", "certifications",
    "achievements", "languages", "summary", "objective", "references",
    "python", "java", "mysql", "docker", "kubernetes", "git",
    "b.tech", "m.tech", "mba", "bca", "mca", "b.sc", "m.sc",
    "cgpa", "gpa", "percentage",
})

# ---------------------------------------------------------------------------
# Company keywords (positive signal, not whitelist)
# ---------------------------------------------------------------------------

_COMPANY_KEYWORDS_RE = re.compile(
    r"\b(?:technologies|technology|solutions|systems|software|services|"
    r"consulting|consultancy|corporation|corp|incorporated|inc|limited|ltd|"
    r"pvt|llc|labs|laboratory|studio|group|ventures|enterprises|"
    r"industries|international|global|digital|networks|analytics|"
    r"university|institute|research|lab)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Location signals
# ---------------------------------------------------------------------------

# Known city/country keywords that suggest a location line.
_LOCATION_SIGNAL_RE = re.compile(
    r"\b(?:mumbai|delhi|bangalore|bengaluru|hyderabad|chennai|pune|kolkata|"
    r"ahmedabad|jaipur|surat|lucknow|kanpur|nagpur|indore|bhopal|"
    r"new\s+york|los\s+angeles|san\s+francisco|chicago|seattle|boston|"
    r"london|paris|berlin|toronto|sydney|singapore|remote|india|usa|uk|"
    r"united\s+states|united\s+kingdom)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Education guard — lines matching these should never be job titles/companies
# ---------------------------------------------------------------------------

_DEGREE_GUARD_RE = re.compile(
    r"(?:b\.?tech|b\.?e\.|m\.?tech|mba|bca|mca|b\.?sc|m\.?sc|phd|ph\.d|"
    r"bachelor|master|doctor|diploma|hsc|ssc|10th|12th)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _blank_record() -> dict:
    return {
        "job_title":   None,
        "company":     None,
        "dates":       None,
        "location":    None,
        "description": [],
    }


def _record_key(rec: dict) -> tuple:
    return (
        (rec.get("job_title") or "").strip().lower(),
        (rec.get("company") or "").strip().lower(),
        (rec.get("dates") or "").strip().lower(),
    )


def _is_valid_record(rec: dict) -> bool:
    """
    A record is valid if it has a job_title, or both company and dates.
    An isolated company name with no job title and no dates is not a valid
    experience record and represents a false positive in fallback mode.
    """
    title = rec.get("job_title")
    company = rec.get("company")
    dates = rec.get("dates")
    if title:
        return True
    if company and dates:
        return True
    return False


def _extract_dates(line: str) -> str | None:
    """Return the first date span found in *line*, or None."""
    m = _DATE_SPAN_RE.search(line)
    return m.group(0).strip() if m else None


def _strip_bullet(line: str) -> str:
    """Remove a leading bullet marker and return the remainder stripped."""
    return _BULLET_RE.sub("", line).strip()


def _is_bullet_line(line: str) -> bool:
    return bool(_BULLET_RE.match(line))


def _looks_like_job_title(line: str) -> bool:
    """
    Return True if *line* is a plausible job title.

    Rules:
    1. Non-empty, 3–80 chars.
    2. Not a date-only line.
    3. Not a bullet line.
    4. Not a degree/education line.
    5. Not a skills-only line (too many commas / pipe chars).
    6. Contains at least one known job-title keyword (case-insensitive).
    7. At most 7 tokens (titles are short).
    8. Mostly alphabetic (≥55%).
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 3 or len(stripped) > 80:
        return False
    if _DATE_ONLY_LINE_RE.match(stripped):
        return False
    if _is_bullet_line(stripped):
        return False
    if _DEGREE_GUARD_RE.search(stripped):
        return False
    # Skills lines tend to be comma- or pipe-separated
    if stripped.count(",") > 2 or stripped.count("|") > 2:
        return False
    tokens = stripped.lower().split()
    if len(tokens) > 7:
        return False
    if not (set(tokens) & _JOB_TITLE_KEYWORDS):
        return False
    # Must not be dominated by known non-title words
    if set(tokens) & _NOT_TITLE_WORDS:
        return False
    alpha = sum(c.isalpha() or c == " " for c in stripped)
    if alpha / len(stripped) < 0.55:
        return False
    return True


def _looks_like_company(line: str) -> bool:
    """
    Return True if *line* is a plausible company name.

    Rules:
    1. Non-empty, 2–80 chars, ≤ 7 tokens.
    2. Not a date-only line.
    3. Not a bullet line.
    4. Not a degree/education line.
    5. Not a skills-only line.
    6. Mostly alphabetic (≥45%).
    7. Either contains a company keyword OR looks like a proper name
       (first letter of each word capitalised).
    """
    stripped = line.strip()
    if not stripped or len(stripped) < 2 or len(stripped) > 80:
        return False
    if _DATE_ONLY_LINE_RE.match(stripped):
        return False
    if _is_bullet_line(stripped):
        return False
    if _DEGREE_GUARD_RE.search(stripped):
        return False
    if stripped.count(",") > 2 or stripped.count("|") > 2:
        return False
    tokens = stripped.split()
    if len(tokens) > 7:
        return False
    alpha = sum(c.isalpha() for c in stripped)
    if len(stripped) == 0 or alpha / len(stripped) < 0.45:
        return False
    has_company_keyword = bool(_COMPANY_KEYWORDS_RE.search(stripped))
    has_title_casing = all(
        w[0].isupper() for w in tokens if w and w[0].isalpha()
    )
    return has_company_keyword or has_title_casing


def _looks_like_location(line: str) -> bool:
    """
    Return True if *line* is plausibly a location.
    Conservative — only fires on known city/country signals or "Remote".
    """
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    if _DATE_ONLY_LINE_RE.match(stripped):
        return False
    if _is_bullet_line(stripped):
        return False
    if _DEGREE_GUARD_RE.search(stripped):
        return False
    return bool(_LOCATION_SIGNAL_RE.search(stripped))


# ---------------------------------------------------------------------------
# Entry boundary detection
# ---------------------------------------------------------------------------

def _find_entry_boundaries(lines: list[str]) -> list[int]:
    """
    Return the line indices where a new experience entry starts.

    Strategy — two phases:

    Phase 1 — blank-line segmentation.
        Split *lines* into raw blocks at blank lines.  This handles the most
        common resume format where entries are separated by empty lines.
        Each block becomes a candidate entry.

    Phase 2 — intra-block splitting.
        If a single block contains more than one date span or more than one
        job-title-like line (after a date), further split it at the second
        title-after-date boundary.  This handles tightly-packed sections
        with no blank line between entries.

    Returns a sorted list of line indices.
    """
    # Phase 1: collect block start indices (blank-line separation)
    block_starts: list[int] = []
    in_blank = True  # treat the beginning as if preceded by a blank

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            in_blank = True
        else:
            if in_blank:
                block_starts.append(i)
                in_blank = False

    if not block_starts:
        return []

    # Phase 2: intra-block split — look for a second title-after-date in the block
    final_boundaries: list[int] = []

    for b_idx, start in enumerate(block_starts):
        end = block_starts[b_idx + 1] if b_idx + 1 < len(block_starts) else len(lines)
        block = lines[start:end]

        split_offsets = _intra_block_splits(block)
        final_boundaries.append(start)
        for offset in split_offsets:
            final_boundaries.append(start + offset)

    final_boundaries.sort()
    return final_boundaries


def _intra_block_splits(block: list[str]) -> list[int]:
    """
    Detect sub-entry boundaries within a single block (no blank lines).

    Returns a list of *relative* line offsets within *block* where a new
    entry should start.  Empty list → block is one entry.

    Trigger: a title-like line that occurs after a date line.
    """
    labels = _label_lines(block)
    splits: list[int] = []
    date_seen = False

    for i, label in enumerate(labels):
        if label == "date":
            date_seen = True
        elif label == "title" and date_seen:
            splits.append(i)
            date_seen = False  # reset for subsequent entries
        elif label == "blank":
            pass  # should not happen inside a block, but safe to skip

    return splits


def _label_lines(lines: list[str]) -> list[str]:
    """Classify each line as 'blank', 'bullet', 'date', 'title', or 'other'."""
    labels = []
    for line in lines:
        s = line.strip()
        if not s:
            labels.append("blank")
        elif _is_bullet_line(s):
            labels.append("bullet")
        elif _DATE_ONLY_LINE_RE.match(s):
            labels.append("date")
        elif _looks_like_job_title(s):
            labels.append("title")
        else:
            labels.append("other")
    return labels


# ---------------------------------------------------------------------------
# Per-group record extractor
# ---------------------------------------------------------------------------

def _parse_group(lines: list[str]) -> dict:
    """
    Parse a group of lines belonging to one experience entry into a record.

    Strategy
    --------
    Pass 1 — scan for unambiguous signals:
      - Date-only lines  → record["dates"]
      - Bullet lines     → record["description"]
      - Job-title lines  → candidate for job_title

    Pass 2 — from remaining non-date, non-bullet, non-title lines:
      - Location signals → record["location"]
      - Remaining clean lines → candidates for company / job_title

    Prefer the assignment: first title-looking line = job_title,
    next candidate = company.  If no title found but company found,
    promote company heuristically.
    """
    record = _blank_record()
    title_candidates: list[str] = []
    company_candidates: list[str] = []
    remaining: list[str] = []

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # ── Bullets → description ───────────────────────────────────────
        if _is_bullet_line(s):
            cleaned = _strip_bullet(s)
            if cleaned:
                record["description"].append(cleaned)
            continue

        # ── Date-only line ───────────────────────────────────────────────
        if _DATE_ONLY_LINE_RE.match(s):
            if record["dates"] is None:
                record["dates"] = _extract_dates(s) or s.strip()
            continue

        # ── Lines containing inline dates (e.g. "ABC Corp | 2024-2025") ─
        inline_date = _extract_dates(s)
        if inline_date:
            if record["dates"] is None:
                record["dates"] = inline_date
            # Strip the date from the line and process the rest
            remainder = _DATE_SPAN_RE.sub("", s).strip(" |—–-,")
            if remainder:
                remaining.append(remainder)
            continue

        # ── Job title ────────────────────────────────────────────────────
        if _looks_like_job_title(s):
            title_candidates.append(s)
            continue

        # ── Everything else (company, location, prose) ───────────────────
        remaining.append(s)

    # ── Assign from remaining ────────────────────────────────────────────
    for line in remaining:
        if _looks_like_location(line) and record["location"] is None:
            record["location"] = line
        elif _looks_like_company(line) and not _looks_like_job_title(line):
            company_candidates.append(line)
        elif _looks_like_job_title(line):
            title_candidates.append(line)

    # ── Populate record from candidates ──────────────────────────────────
    if title_candidates:
        record["job_title"] = title_candidates[0]
    if company_candidates:
        record["company"] = company_candidates[0]

    # ── If only one candidate and it looks like both, try to decide ──────
    if not record["job_title"] and not record["company"] and remaining:
        candidate = remaining[0]
        if _looks_like_job_title(candidate):
            record["job_title"] = candidate
        elif _looks_like_company(candidate):
            record["company"] = candidate

    return record


# ---------------------------------------------------------------------------
# Inline / pipe/dash-separated entry parser
# ---------------------------------------------------------------------------

_INLINE_SEP_RE = re.compile(r"\s*[|—–]\s*")


def _try_parse_inline(line: str) -> dict | None:
    """
    Handle compact single-line entries like:
    ``"Software Engineer | ABC Corp | 2024 - 2025"``
    """
    if "|" not in line and "—" not in line and "–" not in line:
        return None

    parts = [p.strip() for p in _INLINE_SEP_RE.split(line) if p.strip()]
    if len(parts) < 2:
        return None

    record = _blank_record()
    for part in parts:
        date = _extract_dates(part)
        if date and record["dates"] is None:
            record["dates"] = date
        elif _looks_like_job_title(part) and record["job_title"] is None:
            record["job_title"] = part
        elif _looks_like_location(part) and record["location"] is None:
            record["location"] = part
        elif _looks_like_company(part) and record["company"] is None:
            record["company"] = part

    return record if _is_valid_record(record) else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_experience(
    text: str,
    sections: dict[str, str] | None = None,
) -> list[dict]:
    """
    Extract work/professional experience records from resume text.

    Parameters
    ----------
    text:
        Full cleaned resume text (``str``).
    sections:
        Optional dict from ``extractor.sections.detect_sections``.
        If ``sections["experience"]`` exists, it is used as the primary source.

    Returns
    -------
    list[dict]
        List of experience records.  Each record has the keys:
        ``job_title``, ``company``, ``dates``, ``location``, ``description``.
        Returns ``[]`` for empty input or when nothing can be confidently extracted.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_experience() expects a str, got {type(text).__name__!r}."
        )

    # ── Choose source ────────────────────────────────────────────────────
    if sections and "experience" in sections and sections["experience"].strip():
        source = sections["experience"]
    elif text.strip():
        source = text
    else:
        return []

    lines = source.splitlines()
    non_empty = [l for l in lines if l.strip()]

    if not non_empty:
        return []

    # ── Attempt inline parsing for very short sections ───────────────────
    if len(non_empty) <= 2:
        results = []
        for line in non_empty:
            r = _try_parse_inline(line)
            if r and _is_valid_record(r):
                results.append(r)
        if results:
            return _deduplicate(results)

    # ── Find entry boundaries ────────────────────────────────────────────
    boundaries = _find_entry_boundaries(lines)

    if not boundaries:
        return []

    # ── Slice lines into groups and parse each ───────────────────────────
    records: list[dict] = []
    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
        group = lines[start:end]
        record = _parse_group(group)
        if _is_valid_record(record):
            records.append(record)

    # ── Fallback: try inline parsing on any line ─────────────────────────
    if not records:
        for line in non_empty:
            r = _try_parse_inline(line)
            if r and _is_valid_record(r):
                records.append(r)

    return _deduplicate(records)


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def _deduplicate(records: list[dict]) -> list[dict]:
    """Remove exact duplicates by (job_title, company, dates) key."""
    seen: set[tuple] = set()
    result: list[dict] = []
    for rec in records:
        key = _record_key(rec)
        if key not in seen:
            seen.add(key)
            result.append(deepcopy(rec))
    return result
