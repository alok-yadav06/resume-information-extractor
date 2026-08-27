"""
contact.py
----------
Extracts contact and identity fields from cleaned resume text.

This is part of stage 4 of the pipeline (extraction layer).  It operates on
the *full* cleaned text, not on section-detected sub-strings, because contact
information often appears in a header block that precedes any labelled section.

Fields extracted in this module
--------------------------------
- Full Name  (heuristic, conservative)
- Email      (regex-based, robust)
- Phone      (regex-based, international formats + Indian)

LinkedIn and GitHub extraction are intentionally deferred to a later step
(they are "bonus" fields per the project spec).

All extraction is deterministic — no ML, no network calls, no external APIs.

Public API
----------
extract_email(text: str)        -> str | None
extract_phone(text: str)        -> str | None
extract_name(text: str)         -> str | None
extract_contact_info(text: str) -> dict[str, str | None]
    Returns {"name": ..., "email": ..., "phone": ...}
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Shared pre-compiled regexes for reuse in multiple functions
# ---------------------------------------------------------------------------

# Matches a bare email address.
# Local part: alphanumerics plus . _ + - (no consecutive dots, no leading dot)
# Domain: at least one label.TLD; TLD is 2–10 alpha chars.
# Email regex — captures the full address; trailing punctuation is stripped
# in extract_email() rather than using a negative lookahead, which was
# over-excluding addresses followed immediately by sentence punctuation.
_EMAIL_RE = re.compile(
    r"(?<![.\w])"               # not preceded by a word char or dot
    r"[a-zA-Z0-9]"             # must start with alphanumeric
    r"(?:[a-zA-Z0-9._%+\-]*)"
    r"@"
    r"[a-zA-Z0-9\-]+"          # domain label(s)
    r"(?:\.[a-zA-Z0-9\-]+)*"   # sub-domains
    r"\.[a-zA-Z]{2,10}"        # TLD (2-10 alpha chars)
    r"(?=[^a-zA-Z0-9]|$)",     # must end before a non-word char or EOL
    re.IGNORECASE,
)

# Characters that must be stripped from the end of a matched email
# (e.g. trailing . , ; ) from a sentence).
_EMAIL_TRAILING_PUNCT_RE = re.compile(r"[.,;:)>\]]+$")

# Matches a phone number.
#
# Strategy:
#   - Optional country code: +91, +1, 91 (followed by space/hyphen)
#   - Core number: 10 digits (Indian mobile) or 7–12 digit landline
#   - Separators tolerated within the number: space, hyphen, dot
#   - Parenthesised area codes tolerated: (022)
#
# False-positive guards (applied in extract_phone, not the regex itself):
#   - Must contain ≥10 digit characters total (after stripping separators)
#   - Must not be a pure 4-digit year (e.g. 2024)
#   - A candidate that is only digits and is ≤ 6 digits long is rejected
_PHONE_RE = re.compile(
    r"(?:"
    # Optional country code block: +91, +1, 91, +44 …
    r"(?:\+\d{1,3}[\s\-]?)?"
    r"(?:\(\d{1,4}\)[\s\-]?)?"  # optional area code in parens
    r")"
    # Core digits with optional separators
    r"\d[\d\s\-\.]{6,17}\d",
    re.MULTILINE,
)

# URL pattern — used to exclude URL lines from name candidates.
_URL_RE = re.compile(r"https?://|www\.", re.IGNORECASE)

# Recognises a line that is very likely an email (contains @).
_EMAIL_LINE_RE = re.compile(r"@")

# Known section-heading words that must never be selected as a name.
_HEADING_WORDS: frozenset[str] = frozenset({
    "summary", "objective", "profile", "skills", "education", "experience",
    "projects", "certifications", "achievements", "languages", "interests",
    "hobbies", "publications", "volunteering", "references", "qualifications",
    "overview", "about", "career", "professional", "contact", "details",
    "information", "background", "employment", "work", "history",
    "academic", "technical", "core", "competencies", "expertise",
    "internship", "internships", "activities",
})

# Common contact labels that appear as standalone lines or label prefixes.
_CONTACT_LABEL_RE = re.compile(
    r"^\s*(?:phone|mobile|cell|tel|telephone|email|e[\s\-]?mail|"
    r"linkedin|github|address|location|website|url|portfolio|"
    r"contact|dob|date\s+of\s+birth|nationality|gender)\s*[:\-]?\s*",
    re.IGNORECASE,
)

# Job-title indicator words — lines containing these are likely job titles.
_JOB_TITLE_WORDS: frozenset[str] = frozenset({
    "engineer", "developer", "analyst", "designer", "architect", "manager",
    "consultant", "specialist", "lead", "senior", "junior", "intern",
    "associate", "director", "head", "officer", "executive", "coordinator",
    "scientist", "researcher", "programmer", "technician", "administrator",
    "fresher", "graduate", "student", "candidate",
})

# How many lines from the top to inspect when looking for the name.
_NAME_SEARCH_WINDOW = 12


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _digit_count(s: str) -> int:
    """Return the number of digit characters in *s*."""
    return sum(1 for c in s if c.isdigit())


def _strip_label(line: str) -> str:
    """
    Remove a leading label prefix such as ``"Email:"`` or ``"Phone: "``
    from a line and return the remainder stripped.
    """
    return _CONTACT_LABEL_RE.sub("", line).strip()


def _looks_like_name(line: str) -> bool:
    """
    Return ``True`` if *line* is a plausible person-name candidate.

    Criteria (all must hold):
    1.  After stripping, the line is non-empty.
    2.  The line contains no ``@`` (email).
    3.  The line contains no URL prefix.
    4.  The line does not match a contact-label pattern.
    5.  After lower-casing, none of its tokens is a known section-heading word.
    6.  After lower-casing, none of its tokens is a job-title indicator word.
    7.  The line is predominantly alphabetic (≥ 60% alpha chars after strip).
    8.  The line is short enough to be a name (≤ 50 characters).
    9.  The line has at most 5 tokens (names are short; long lines are prose).
    10. The line contains at least 2 characters.
    """
    stripped = line.strip()
    if len(stripped) < 2:
        return False
    if len(stripped) > 50:
        return False
    if _EMAIL_LINE_RE.search(stripped):
        return False
    if _URL_RE.search(stripped):
        return False
    if _CONTACT_LABEL_RE.match(stripped):
        return False

    tokens = stripped.lower().split()
    if not tokens:
        return False
    # A realistic name has at least 2 parts (first + last).
    if len(tokens) < 2:
        return False
    if len(tokens) > 5:
        return False

    # Reject if any token is a known heading word.
    if set(tokens) & _HEADING_WORDS:
        return False

    # Reject if any token is a job-title word.
    if set(tokens) & _JOB_TITLE_WORDS:
        return False

    # Must be mostly alphabetic (allow hyphens and apostrophes for names).
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if alpha_count / len(stripped) < 0.6:
        return False

    return True


def _title_case_name(raw: str) -> str:
    """
    Apply title-case to *raw* in a name-safe way.

    Hyphens and apostrophes within tokens are handled so that
    ``"O'BRIAN"`` → ``"O'Brian"`` and ``"mary-jane"`` → ``"Mary-Jane"``.
    """
    def _title_token(token: str) -> str:
        # Handle hyphenated tokens.
        if "-" in token:
            return "-".join(part.capitalize() for part in token.split("-"))
        # Handle apostrophe (O'Brien).
        if "'" in token:
            parts = token.split("'")
            return "'".join(part.capitalize() for part in parts)
        return token.capitalize()

    return " ".join(_title_token(t) for t in raw.strip().split())


# ---------------------------------------------------------------------------
# Public extraction functions
# ---------------------------------------------------------------------------

def extract_email(text: str) -> str | None:
    """
    Extract the first valid email address from *text*.

    Parameters
    ----------
    text:
        Cleaned resume text (``str``).

    Returns
    -------
    str | None
        Lower-cased email address, or ``None`` if not found.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_email() expects a str, got {type(text).__name__!r}."
        )
    # Strip labels before searching (e.g. "Email: john@example.com")
    # We search the raw text — the regex handles adjacent chars via lookaheads.
    match = _EMAIL_RE.search(text)
    if match:
        email = match.group(0)
        # Strip trailing sentence punctuation that the lookahead may still include.
        email = _EMAIL_TRAILING_PUNCT_RE.sub("", email)
        return email.lower()
    return None


def extract_phone(text: str) -> str | None:
    """
    Extract the first plausible phone number from *text*.

    The function applies a regex to find number-like patterns, then filters
    candidates through a set of sanity checks before accepting one.

    Parameters
    ----------
    text:
        Cleaned resume text (``str``).

    Returns
    -------
    str | None
        Phone number string preserving original formatting, or ``None``.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_phone() expects a str, got {type(text).__name__!r}."
        )

    # Pre-process: strip label prefixes from each line so that
    # "Phone: +91 9876543210" does not confuse the regex.
    processed_lines = [_strip_label(ln) for ln in text.splitlines()]
    processed_text = "\n".join(processed_lines)

    for match in _PHONE_RE.finditer(processed_text):
        candidate = match.group(0).strip()

        # Count actual digits.
        digits = _digit_count(candidate)

        # Must have at least 7 digits (shortest realistic landline).
        if digits < 7:
            continue

        # Reject pure 4-digit years (1900–2099 range).
        digits_only = re.sub(r"\D", "", candidate)
        if len(digits_only) == 4 and 1900 <= int(digits_only) <= 2099:
            continue

        # Reject short digit-only strings that look like PINs, IDs, etc.
        if len(digits_only) < 7:
            continue

        # Reject single percentage-style numbers (e.g. "95", "9.5")
        # by checking the context character immediately after the match.
        end_pos = match.end()
        if end_pos < len(processed_text):
            next_char = processed_text[end_pos]
            if next_char in "%/":
                continue

        # Passed all checks — return as found (preserves formatting).
        return candidate.strip()

    return None


def extract_name(text: str) -> str | None:
    """
    Extract the candidate's full name from the top of the resume.

    This is a heuristic function — name extraction is inherently less
    deterministic than email/phone because there is no universal format.

    Strategy
    --------
    1.  Inspect the first ``_NAME_SEARCH_WINDOW`` non-empty lines of the text.
    2.  For each line, apply ``_looks_like_name()`` which filters out emails,
        URLs, contact labels, section headings, and job-title keywords.
    3.  The first line that passes all filters is accepted as the name.
    4.  The returned name is title-cased (``"ALICE JOHNSON"`` → ``"Alice Johnson"``).
    5.  If no line passes, return ``None``.

    Parameters
    ----------
    text:
        Cleaned resume text (``str``).

    Returns
    -------
    str | None
        Title-cased name string, or ``None`` if no confident candidate found.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_name() expects a str, got {type(text).__name__!r}."
        )

    # Collect the first _NAME_SEARCH_WINDOW non-empty lines.
    non_empty_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            non_empty_lines.append(stripped)
        if len(non_empty_lines) >= _NAME_SEARCH_WINDOW:
            break

    for line in non_empty_lines:
        if _looks_like_name(line):
            return _title_case_name(line)

    return None


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------

def extract_contact_info(text: str) -> dict[str, str | None]:
    """
    Run all three contact extractors and return a combined result dict.

    Parameters
    ----------
    text:
        Cleaned resume text (``str``).  For empty/whitespace-only input all
        fields will be ``None``.

    Returns
    -------
    dict with keys: ``"name"``, ``"email"``, ``"phone"``.
    Each value is either a ``str`` or ``None``.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.

    Examples
    --------
    >>> extract_contact_info("Alice Johnson\\nalice@example.com\\n+91 9876543210")
    {'name': 'Alice Johnson', 'email': 'alice@example.com', 'phone': '+91 9876543210'}

    >>> extract_contact_info("")
    {'name': None, 'email': None, 'phone': None}
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_contact_info() expects a str, got {type(text).__name__!r}."
        )

    return {
        "name":  extract_name(text),
        "email": extract_email(text),
        "phone": extract_phone(text),
    }
