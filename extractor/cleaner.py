"""
cleaner.py
----------
Normalises raw extracted text so that all downstream modules receive a
consistent, well-formed string.

This module sits between the parser and every extraction module.  It does
*not* extract information — it only makes the text uniform.

Operations (in order)
---------------------
1.  Unicode NFC normalisation            – unifies accented / composite chars.
2.  Non-breaking & special whitespace    – replaced with ordinary spaces.
3.  Control-character removal            – strips invisible junk bytes while
                                           keeping \\n and \\t.
4.  Line-ending normalisation            – \\r\\n and \\r → \\n.
5.  Per-line strip                       – removes leading/trailing spaces on
                                           every line without losing the line.
6.  Intra-line whitespace collapse       – collapses runs of spaces/tabs
                                           inside a line to a single space,
                                           while preserving meaningful content.
7.  Excessive blank-line reduction       – at most two consecutive blank lines
                                           are kept (one is usually enough for
                                           section separation).
8.  Document-level strip                 – removes leading/trailing whitespace
                                           from the complete output.

What is intentionally preserved
--------------------------------
- Original casing  (do NOT lowercase — extraction relies on case signals).
- Punctuation      (emails, URLs, phone numbers, C++, Node.js, B.Tech, …).
- Newlines         (section structure depends on line boundaries).
- Single tabs      (some parsers emit tab-separated columns).
- Hyphens, dots, slashes, +, @ inside tokens.

Public API
----------
clean_text(text: str) -> str
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Unicode categories that represent "special whitespace" we want to replace
# with a plain space — but that are NOT ordinary ASCII space (0x20).
# Reference: https://www.unicode.org/reports/tr44/#GC_Values_Table
# ---------------------------------------------------------------------------
_SPECIAL_WHITESPACE_RE = re.compile(
    r"[\u00a0"          # NO-BREAK SPACE
    r"\u2000-\u200b"    # EN QUAD … ZERO WIDTH SPACE
    r"\u2028\u2029"     # LINE/PARAGRAPH SEPARATOR (treat as newline later)
    r"\u202f"           # NARROW NO-BREAK SPACE
    r"\u205f"           # MEDIUM MATHEMATICAL SPACE
    r"\u3000"           # IDEOGRAPHIC SPACE
    r"\ufeff"           # BOM / ZERO WIDTH NO-BREAK SPACE
    r"]"
)

# Control characters (C0 and C1 ranges) except \t (0x09) and \n (0x0A).
# We handle \r separately in step 4.
_CONTROL_CHAR_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]"
)

# One or more spaces/tabs inside a line (not newlines) → single space.
_MULTI_SPACE_RE = re.compile(r"[ \t]+")

# Three or more consecutive blank lines → two blank lines (one visual gap).
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _normalise_unicode(text: str) -> str:
    """
    Apply Unicode NFC normalisation.

    NFC decomposes and then re-composes characters, ensuring that é (U+00E9)
    and e + ́ (U+0065 + U+0301) are treated identically.  This avoids regex
    mismatches on accented names or degree strings.
    """
    return unicodedata.normalize("NFC", text)


def _replace_special_whitespace(text: str) -> str:
    """
    Replace non-breaking spaces and other exotic whitespace with a plain
    ASCII space so that later steps can treat all horizontal whitespace
    uniformly.

    Unicode line/paragraph separators (U+2028, U+2029) are also converted
    to newlines here so they participate in line-ending normalisation.
    """
    # Line/paragraph separators → newline first (before the rest become spaces)
    text = text.replace("\u2028", "\n").replace("\u2029", "\n")
    return _SPECIAL_WHITESPACE_RE.sub(" ", text)


def _remove_control_characters(text: str) -> str:
    """
    Strip invisible control characters that PDF/DOCX parsers sometimes
    embed (null bytes, form feeds already handled elsewhere, etc.).

    Keeps: printable characters, \\n (newline), \\t (tab).
    """
    return _CONTROL_CHAR_RE.sub("", text)


def _normalise_line_endings(text: str) -> str:
    """
    Convert all variants of line endings to Unix-style ``\\n``.

    Order matters:
    - Replace ``\\r\\n`` first (Windows) to avoid leaving a stray ``\\n``.
    - Then replace remaining ``\\r`` (old Mac).
    - Form-feed ``\\f`` (page separator inserted by the PDF parser) is
      converted to a blank line so section boundaries remain visible.
    """
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = text.replace("\f", "\n\n")   # PDF page break → blank-line gap
    return text


def _strip_lines(text: str) -> str:
    """
    Remove leading and trailing spaces/tabs from every individual line.

    This does NOT remove the lines themselves — empty lines after stripping
    remain as empty lines, preserving section separation.
    """
    return "\n".join(line.strip() for line in text.split("\n"))


def _collapse_intra_line_whitespace(text: str) -> str:
    """
    Collapse runs of spaces and/or tabs *within* a line to a single space.

    Operates line by line so that newlines are never touched.

    Example: ``"John     Doe"``  →  ``"John Doe"``
    Example: ``"+91 98765 43210"``  →  ``"+91 98765 43210"``  (already OK)
    """
    lines = text.split("\n")
    collapsed = [_MULTI_SPACE_RE.sub(" ", line) for line in lines]
    return "\n".join(collapsed)


def _reduce_blank_lines(text: str) -> str:
    """
    Replace three or more consecutive newlines with exactly two newlines
    (which renders as one blank line).

    This keeps section headings visually separated without wasting vertical
    space on parser artefacts.
    """
    return _EXCESS_BLANK_LINES_RE.sub("\n\n", text)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_text(text: str) -> str:
    """
    Normalise raw resume text for downstream rule-based extraction.

    This function is deterministic: the same input always produces the same
    output, and it never removes information that is meaningful for extraction.

    Parameters
    ----------
    text:
        Raw string returned by ``extractor.parser.extract_text``.
        Must be a ``str``.  Passing ``None`` or any non-string raises
        ``TypeError`` immediately.

    Returns
    -------
    str
        A normalised, consistently formatted string ready for regex-based
        field extraction and section detection.

    Raises
    ------
    TypeError
        If *text* is not a ``str`` instance.

    Notes
    -----
    - Casing is **not** changed.  Extraction modules may rely on
      capitalisation (e.g. name detection, degree matching).
    - Duplicate lines are **not** removed.  A repeated line may be
      intentional (e.g. a skill listed under two sections).
    - The document is never lowercased.

    Examples
    --------
    >>> clean_text("John   Doe\\n\\n\\n\\nPython Developer")
    'John Doe\\n\\nPython Developer'

    >>> clean_text("  john.doe@gmail.com  ")
    'john.doe@gmail.com'

    >>> clean_text("C++, Node.js, Spring Boot, B.Tech")
    'C++, Node.js, Spring Boot, B.Tech'
    """
    if not isinstance(text, str):
        raise TypeError(
            f"clean_text() expects a str, got {type(text).__name__!r}."
        )

    # Short-circuit: nothing to do for empty/whitespace-only input.
    if not text.strip():
        return ""

    # --- Apply pipeline steps in order -----------------------------------

    # 1. Unicode NFC
    text = _normalise_unicode(text)

    # 2. Special / non-breaking whitespace → ordinary space
    text = _replace_special_whitespace(text)

    # 3. Strip control characters (keeps \n and \t)
    text = _remove_control_characters(text)

    # 4. Unify line endings; page-break \f → blank line
    text = _normalise_line_endings(text)

    # 5. Strip each line individually
    text = _strip_lines(text)

    # 6. Collapse multiple spaces/tabs within a line
    text = _collapse_intra_line_whitespace(text)

    # 7. At most two consecutive newlines (one visible blank line)
    text = _reduce_blank_lines(text)

    # 8. Remove leading/trailing whitespace from the whole document
    text = text.strip()

    return text
