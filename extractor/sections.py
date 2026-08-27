"""
sections.py
-----------
Detects logical section boundaries within cleaned resume text and splits the
document into named blocks.

This is stage 3 of the pipeline:

    parser → cleaner → sections → (contact, skills, education, experience)

The module only *splits* the text — it does not extract any field values.

Design
------
- A curated alias table maps every known heading variant to a canonical name
  (e.g. "TECHNICAL SKILLS" → "skills").
- The detector scans every line, strips trailing punctuation/whitespace, and
  does a case-insensitive lookup in the alias table.
- Lines that match an alias AND meet a short set of structural sanity checks
  (short enough, no sentence-ending words mid-line) are treated as headings.
- Text between two consecutive headings is the content of the first section.
- Duplicate canonical sections are combined in document order.

Public API
----------
detect_sections(text: str) -> dict[str, str]
    Returns a mapping of canonical section name → section body text.
    Only sections that were actually found are included.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Alias table
# ---------------------------------------------------------------------------
# Maps every recognised heading variant (lower-cased, stripped) to a canonical
# section name.  Adding a new alias only requires editing this dict — nothing
# else in the module needs to change.
# ---------------------------------------------------------------------------

SECTION_ALIASES: dict[str, str] = {
    # ── Summary / Objective ──────────────────────────────────────────────
    "summary":                      "summary",
    "professional summary":         "summary",
    "career summary":               "summary",
    "profile":                      "summary",
    "professional profile":         "summary",
    "about me":                     "summary",
    "about":                        "summary",
    "overview":                     "summary",
    "objective":                    "objective",
    "career objective":             "objective",
    "professional objective":       "objective",
    "job objective":                "objective",

    # ── Skills ───────────────────────────────────────────────────────────
    "skills":                       "skills",
    "technical skills":             "skills",
    "skill set":                    "skills",
    "core skills":                  "skills",
    "key skills":                   "skills",
    "technical proficiencies":      "skills",
    "technologies":                 "skills",
    "technologies & tools":         "skills",
    "technologies and tools":       "skills",
    "tools & technologies":         "skills",
    "tools and technologies":       "skills",
    "technical expertise":          "skills",
    "areas of expertise":           "skills",
    "competencies":                 "skills",
    "core competencies":            "skills",
    "programming skills":           "skills",
    "programming languages":        "skills",
    "technical stack":              "skills",
    "tech stack":                   "skills",
    "expertise":                    "skills",

    # ── Education ────────────────────────────────────────────────────────
    "education":                    "education",
    "educational background":       "education",
    "educational qualifications":   "education",
    "academic background":          "education",
    "academic qualifications":      "education",
    "academic history":             "education",
    "qualifications":               "education",
    "degrees":                      "education",

    # ── Experience ───────────────────────────────────────────────────────
    "experience":                   "experience",
    "work experience":              "experience",
    "professional experience":      "experience",
    "employment history":           "experience",
    "work history":                 "experience",
    "job history":                  "experience",
    "career history":               "experience",
    "relevant experience":          "experience",
    "industry experience":          "experience",
    "internship":                   "experience",
    "internships":                  "experience",
    "internship experience":        "experience",

    # ── Projects ─────────────────────────────────────────────────────────
    "projects":                     "projects",
    "personal projects":            "projects",
    "academic projects":            "projects",
    "project experience":           "projects",
    "notable projects":             "projects",
    "key projects":                 "projects",
    "side projects":                "projects",
    "open source projects":         "projects",
    "open-source projects":         "projects",

    # ── Certifications ───────────────────────────────────────────────────
    "certifications":               "certifications",
    "certificates":                 "certifications",
    "professional certifications":  "certifications",
    "licenses":                     "certifications",
    "licenses & certifications":    "certifications",
    "licenses and certifications":  "certifications",
    "credentials":                  "certifications",

    # ── Achievements / Awards ────────────────────────────────────────────
    "achievements":                 "achievements",
    "awards":                       "achievements",
    "honors":                       "achievements",
    "honours":                      "achievements",
    "awards & achievements":        "achievements",
    "awards and achievements":      "achievements",
    "accomplishments":              "achievements",
    "recognition":                  "achievements",

    # ── Languages ────────────────────────────────────────────────────────
    "languages":                    "languages",
    "language skills":              "languages",
    "spoken languages":             "languages",
    "foreign languages":            "languages",

    # ── Interests / Hobbies ──────────────────────────────────────────────
    "interests":                    "interests",
    "hobbies":                      "interests",
    "hobbies & interests":          "interests",
    "hobbies and interests":        "interests",
    "extracurricular activities":   "interests",
    "activities":                   "interests",

    # ── Publications / Research ──────────────────────────────────────────
    "publications":                 "publications",
    "research":                     "publications",
    "research experience":          "publications",
    "papers":                       "publications",
    "conference papers":            "publications",

    # ── Volunteering / Leadership ────────────────────────────────────────
    "volunteering":                 "volunteering",
    "volunteer experience":         "volunteering",
    "leadership":                   "volunteering",
    "community service":            "volunteering",

    # ── References ───────────────────────────────────────────────────────
    "references":                   "references",
    "professional references":      "references",
}

# Pre-build a set of canonical names for quick membership checks.
CANONICAL_SECTIONS: frozenset[str] = frozenset(SECTION_ALIASES.values())

# ---------------------------------------------------------------------------
# Heuristics for false-positive reduction
# ---------------------------------------------------------------------------

# A heading line should be short enough to be a label, not a sentence.
# 60 characters is a generous upper bound that allows long headings like
# "AWARDS, HONORS & EXTRACURRICULAR ACTIVITIES" without trapping sentences.
_MAX_HEADING_LENGTH: int = 60

# Words that strongly suggest the line is part of a sentence, not a heading.
# These are checked as whole words (case-insensitive) in the candidate line.
_SENTENCE_INDICATORS: frozenset[str] = frozenset({
    "the", "and", "with", "have", "has", "had", "was", "were",
    "is", "are", "be", "been", "will", "would", "can", "could",
    "should", "my", "our", "your", "their", "its", "in", "on",
    "at", "for", "of", "to", "from", "by", "an", "a",
})

# Regex that strips trailing punctuation characters that often appear after
# headings in resumes (e.g.  "SKILLS:" → "SKILLS").
_TRAILING_PUNCT_RE = re.compile(r"[\s:.\-–—|]+$")

# Pre-compiled set of all known aliases (lower-cased) for O(1) lookup.
_ALIAS_LOOKUP: frozenset[str] = frozenset(SECTION_ALIASES.keys())


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise_heading_candidate(line: str) -> str:
    """
    Strip trailing punctuation/whitespace from *line* and return lower-cased.

    This lets us match "SKILLS:"  →  "skills"  and  "Education —"  →  "education".
    """
    stripped = _TRAILING_PUNCT_RE.sub("", line).strip()
    return stripped.lower()


def _is_heading(line: str) -> bool:
    """
    Return ``True`` if *line* should be treated as a section heading.

    Rules (all must hold):
    1. The line is not empty after stripping.
    2. The line is at most ``_MAX_HEADING_LENGTH`` characters (raw).
    3. After normalisation, the line matches a known alias exactly.
    4. The line does not contain sentence-indicator words — this prevents
       a sentence like "I have experience in Python" from being treated as
       an "experience" heading.
    """
    raw = line.strip()
    if not raw:
        return False

    if len(raw) > _MAX_HEADING_LENGTH:
        return False

    normalised = _normalise_heading_candidate(raw)
    if normalised not in _ALIAS_LOOKUP:
        return False

    # Sentence-indicator check: split into words and intersect with indicators.
    words = set(normalised.split())
    if words & _SENTENCE_INDICATORS:
        return False

    return True


def _resolve_canonical(line: str) -> str:
    """
    Return the canonical section name for a line known to be a heading.

    Assumes ``_is_heading(line)`` is ``True``.
    """
    normalised = _normalise_heading_candidate(line.strip())
    return SECTION_ALIASES[normalised]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_sections(text: str) -> dict[str, str]:
    """
    Split cleaned resume text into named section blocks.

    Parameters
    ----------
    text:
        The normalised text produced by ``extractor.cleaner.clean_text``.
        Must be a ``str``.

    Returns
    -------
    dict[str, str]
        Mapping of canonical section name → section body text.
        Only sections that were *actually detected* are included in the
        returned dictionary.  The values are stripped of leading/trailing
        whitespace.

        If the same canonical section appears more than once, its contents
        are joined in document order with a blank line between them.

        Returns an empty dict for empty / whitespace-only input.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.

    Examples
    --------
    >>> text = "SKILLS\\nPython\\nJava\\n\\nEDUCATION\\nB.Tech"
    >>> detect_sections(text)
    {'skills': 'Python\\nJava', 'education': 'B.Tech'}
    """
    if not isinstance(text, str):
        raise TypeError(
            f"detect_sections() expects a str, got {type(text).__name__!r}."
        )

    if not text.strip():
        return {}

    lines = text.splitlines()

    # ── Pass 1: classify every line as a heading or body text ────────────
    # Build a list of (line_index, canonical_name) for all heading lines.
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if _is_heading(line):
            headings.append((i, _resolve_canonical(line)))

    # No recognisable headings found → return empty dict.
    if not headings:
        return {}

    # ── Pass 2: slice body text between consecutive headings ─────────────
    # We iterate over adjacent heading pairs and collect the lines in between.
    sections: dict[str, list[str]] = {}

    for idx, (heading_line_no, canonical) in enumerate(headings):
        # Body runs from the line *after* the heading …
        body_start = heading_line_no + 1
        # … to the line *before* the next heading (or end of document).
        if idx + 1 < len(headings):
            body_end = headings[idx + 1][0]
        else:
            body_end = len(lines)

        body_lines = lines[body_start:body_end]
        # Strip blank lines at the top and bottom of the block, but keep
        # internal blank lines (they separate sub-entries within a section).
        body_text = "\n".join(body_lines).strip()

        # Combine duplicate sections in document order.
        if canonical in sections:
            if body_text:
                sections[canonical].append(body_text)
        else:
            sections[canonical] = [body_text] if body_text else [""]

    # ── Pass 3: flatten lists into strings ───────────────────────────────
    result: dict[str, str] = {}
    for canonical, blocks in sections.items():
        combined = "\n\n".join(block for block in blocks if block)
        result[canonical] = combined

    return result
