"""
skills.py
---------
Extracts technical and professional skills from resume text.

This module is part of the extraction layer (stage 4+).  It operates on:
  - The isolated ``skills`` section text when section detection was run.
  - The full cleaned text as a fallback when no skills section is present.

All matching is deterministic, rule-based, and boundary-aware.
No ML, no fuzzy matching, no external services.

Design overview
---------------
1.  ``data/skills.json`` is the single source of truth for the skill vocabulary.
    It contains canonical skill names grouped by category, plus an ``aliases``
    dict that maps common alternative spellings to the canonical form.

2.  At module load-time, a ``SkillDatabase`` is built from the JSON:
    - Every canonical name is stored verbatim.
    - Every alias maps to its canonical name.
    - For each skill, a compiled regex pattern is generated that matches the
      skill as a whole token — never as a substring of another word.

3.  ``extract_skills(text, sections)`` is the public entry point:
    - If ``sections["skills"]`` exists, match against that focused sub-string.
    - Otherwise, scan the full text (fallback mode, less precise).

4.  Multi-word skills are matched before their component words to prevent
    ``"Spring Boot"`` from also matching ``"Spring"`` (longer-first ordering).

5.  Skills that are aliases of the same canonical name are de-duplicated.

Boundary-awareness detail
--------------------------
Special technical names like ``C``, ``C++``, ``C#``, ``Go``, and ``R`` cannot
use the standard ``\\bSKILL\\b`` pattern because:
  - ``\\b`` is a transition between ``\\w`` and ``\\W`` characters.
  - ``+``, ``#``, ``.`` in skill names like ``C++`` are ``\\W`` characters,
    so ``\\bC\\b`` would match the ``C`` inside ``C++`` or ``C#``.

For these problematic skills, the pattern enforces that the token must be
surrounded by non-alphanumeric characters (or start/end of string), which
prevents accidental sub-match inside longer tokens.

Public API
----------
extract_skills(text, sections=None) -> list[str]
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Default path to the skill knowledge base
# ---------------------------------------------------------------------------

_DEFAULT_DB_PATH = Path(__file__).parent.parent / "data" / "skills.json"

# ---------------------------------------------------------------------------
# Skills that require extra-strict boundary patterns because they consist of
# characters that are themselves parts of longer skill names.
# These are matched only when surrounded by non-alphanumeric context.
# ---------------------------------------------------------------------------
_STRICT_BOUNDARY_SKILLS: frozenset[str] = frozenset({
    "C", "R", "Go",
})


# ---------------------------------------------------------------------------
# Regex helpers
# ---------------------------------------------------------------------------

def _escape_skill(skill: str) -> str:
    """
    Return a regex-safe escaped version of *skill*, preserving ``\\+``, ``#``,
    ``.``, ``-``, and other literal characters that appear in skill names.
    """
    return re.escape(skill)


def _build_pattern(skill: str) -> re.Pattern[str]:
    """
    Build a compiled regex that matches *skill* as a whole token in resume text.

    Strategy
    --------
    - For normal skills (letters, digits, spaces):
        ``(?i)(?<![\\w.])SKILL(?![\\w.])``
        The lookbehind/lookahead prevent matching as a substring of another
        alphanumeric token.  The ``.`` is also excluded from the surrounding
        chars to prevent ``react.js`` from matching ``react``.

    - For special/strict skills (C, R, Go) that share prefixes with longer skills:
        ``(?i)(?<![\\w+#.])SKILL(?![\\w+#.])``
        Extra characters ``+ # .`` are added to the exclusion context so that
        ``C`` does not match inside ``C++``, ``C#``, ``CSS``, or ``Cloud``.

    - For skills ending in punctuation (C++, C#, .NET, Node.js, React.js):
        The trailing punctuation is part of the skill literal and is already
        included in the escape.  The lookahead checks for a non-word/non-dot
        character to avoid partial matches.
    """
    escaped = _escape_skill(skill)

    if skill in _STRICT_BOUNDARY_SKILLS:
        # Must not be preceded or followed by any word char, +, #, ., or –
        pattern = rf"(?i)(?<![A-Za-z0-9+#.\-]){escaped}(?![A-Za-z0-9+#.\-])"
    elif skill.endswith(("+", "#")):
        # e.g. C++, C# — lookahead only needs to check for word chars
        pattern = rf"(?i)(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])"
    elif "." in skill or skill.startswith("."):
        # e.g. Node.js, .NET — boundary includes dot context
        pattern = rf"(?i)(?<![A-Za-z0-9.]){escaped}(?![A-Za-z0-9.])"
    elif " " in skill:
        # Multi-word: word boundaries on the outer edges only
        pattern = rf"(?i)(?<!\w){escaped}(?!\w)"
    else:
        # Standard single-word skill
        pattern = rf"(?i)(?<!\w){escaped}(?!\w)"

    return re.compile(pattern)


# ---------------------------------------------------------------------------
# SkillDatabase
# ---------------------------------------------------------------------------

class SkillDatabase:
    """
    In-memory representation of the ``skills.json`` knowledge base.

    Attributes
    ----------
    canonical_names : list[str]
        All canonical skill names from the JSON, preserving original casing.
    alias_map : dict[str, str]
        Lower-cased alias → canonical name.
    patterns : list[tuple[str, re.Pattern]]
        (canonical_name, compiled_regex) pairs, sorted longest-first so that
        multi-word skills are matched before their component words.
    """

    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._load()

    def _load(self) -> None:
        """Parse ``skills.json`` and compile matching patterns."""
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Skills database not found: {self._path}. "
                "Ensure data/skills.json exists in the project root."
            )
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"skills.json is not valid JSON: {exc}"
            ) from exc

        # Collect all canonical names from every category list.
        canonical: list[str] = []
        seen_canonical: set[str] = set()
        for key, value in raw.items():
            if key.startswith("_"):
                continue          # skip comment keys
            if key == "aliases":
                continue          # handled separately
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and item not in seen_canonical:
                        canonical.append(item)
                        seen_canonical.add(item)

        self.canonical_names: list[str] = canonical

        # Build the alias map: lower(alias) → canonical.
        self.alias_map: dict[str, str] = {}
        aliases_block = raw.get("aliases", {})
        for alias_key, canonical_value in aliases_block.items():
            if alias_key.startswith("_"):
                continue
            if isinstance(alias_key, str) and isinstance(canonical_value, str):
                self.alias_map[alias_key.lower()] = canonical_value

        # Also index canonical names themselves (lower → canonical) for fast
        # alias resolution during text scanning.
        self._canonical_lower: dict[str, str] = {
            name.lower(): name for name in canonical
        }

        # Compile patterns: sort by length descending so multi-word/longer
        # skills are attempted before shorter overlapping ones.
        all_skills = list(canonical)
        # Also add aliases whose canonical targets might differ in spelling.
        alias_targets = set(self.alias_map.values())
        for target in alias_targets:
            if target not in seen_canonical:
                all_skills.append(target)

        all_skills.sort(key=lambda s: len(s), reverse=True)
        self.patterns: list[tuple[str, re.Pattern[str]]] = [
            (skill, _build_pattern(skill)) for skill in all_skills
        ]

    def resolve_alias(self, token: str) -> str | None:
        """
        Resolve *token* to a canonical skill name.

        Checks in order:
        1. Alias map (lower-cased key lookup).
        2. Canonical name map (case-insensitive).

        Returns ``None`` if *token* is not a known skill or alias.
        """
        low = token.strip().lower()
        if low in self.alias_map:
            return self.alias_map[low]
        if low in self._canonical_lower:
            return self._canonical_lower[low]
        return None


# ---------------------------------------------------------------------------
# Module-level singleton — loaded once per process, reused across calls.
# ---------------------------------------------------------------------------

_db: SkillDatabase | None = None


def _get_db(db_path: Path | None = None) -> SkillDatabase:
    """Return the module-level ``SkillDatabase``, loading it on first call."""
    global _db
    effective_path = db_path or _DEFAULT_DB_PATH
    if _db is None or (db_path is not None and db_path != _DEFAULT_DB_PATH):
        _db = SkillDatabase(effective_path)
    return _db


# ---------------------------------------------------------------------------
# Token-level pre-processing helpers
# ---------------------------------------------------------------------------

# Separators that may appear between skills within a skills section.
_SEPARATOR_RE = re.compile(r"[,|•\-–—►▪✓*]")

# Labels like "Programming Languages:" at the start of a line.
_CATEGORY_LABEL_RE = re.compile(
    r"^\s*[A-Za-z &/()]+:\s*", re.MULTILINE
)


def _strip_section_labels(text: str) -> str:
    """
    Remove category sub-headings (e.g. ``"Programming Languages: "``).

    These appear when the skills section uses a grouped format like::

        Programming Languages: Java, Python, C++
        Databases: MySQL, MongoDB

    Stripping the label portion lets the remaining comma-/space-separated
    tokens be matched normally.
    """
    return _CATEGORY_LABEL_RE.sub(" ", text)


# ---------------------------------------------------------------------------
# Core matching engine
# ---------------------------------------------------------------------------

def _scan_text(text: str, db: SkillDatabase) -> list[str]:
    """
    Scan *text* for known skills and return them in document order.

    Algorithm
    ---------
    1.  Strip section-category labels (``"Programming: "``).
    2.  Attempt alias resolution on comma/pipe/bullet-separated tokens first —
        this handles short tokens like ``"JS"`` or ``"NodeJS"`` that the
        longer patterns would not match correctly.
    3.  Then run all compiled patterns (longest-first) over the raw text.
        Each match is converted to its canonical name via ``resolve_alias``.
    4.  Track positions so skills are returned in *appearance order*.
    5.  De-duplicate by canonical name (first occurrence wins).

    Returns
    -------
    list[str]
        Canonical skill names in appearance order, no duplicates.
    """
    cleaned = _strip_section_labels(text)

    # --- Pass 1: token-level alias resolution (handles JS, NodeJS, etc.) ---
    # Split on common separators and whitespace to get individual tokens.
    raw_tokens = _SEPARATOR_RE.sub(" ", cleaned).split()
    # Also try adjacent pairs for two-word aliases (e.g. "node js").
    # And adjacent triplets for three-word aliases (e.g. "c plus plus").
    candidate_tokens: list[tuple[int, str]] = []
    for i, tok in enumerate(raw_tokens):
        candidate_tokens.append((i * 100, tok))
    for i in range(len(raw_tokens) - 1):
        pair = f"{raw_tokens[i]} {raw_tokens[i + 1]}"
        candidate_tokens.append((i * 100 + 50, pair))
    for i in range(len(raw_tokens) - 2):
        triplet = f"{raw_tokens[i]} {raw_tokens[i + 1]} {raw_tokens[i + 2]}"
        candidate_tokens.append((i * 100 + 25, triplet))

    found: list[tuple[int, str]] = []  # (position, canonical_name)
    seen_canonical: set[str] = set()

    for pos, token in sorted(candidate_tokens, key=lambda x: x[0]):
        canonical = db.resolve_alias(token)
        if canonical and canonical not in seen_canonical:
            found.append((pos, canonical))
            seen_canonical.add(canonical)

    # --- Pass 2: pattern matching over the full text ----------------------
    # Use character positions for ordering.
    for canonical, pattern in db.patterns:
        for match in pattern.finditer(cleaned):
            resolved = db.resolve_alias(match.group(0)) or canonical
            if resolved not in seen_canonical:
                found.append((match.start(), resolved))
                seen_canonical.add(resolved)

    # Sort by first-appearance position.
    found.sort(key=lambda x: x[0])
    return [canonical for _, canonical in found]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_skills(
    text: str,
    sections: dict[str, str] | None = None,
    db_path: Path | None = None,
) -> list[str]:
    """
    Extract technical/professional skills from resume text.

    Parameters
    ----------
    text:
        The full cleaned resume text produced by ``extractor.cleaner``.
        Must be a ``str``.
    sections:
        Optional dict produced by ``extractor.sections.detect_sections``.
        If ``sections["skills"]`` exists, only that sub-string is scanned
        (section-aware mode).  Otherwise, the full *text* is scanned as a
        conservative fallback.
    db_path:
        Optional path to a custom ``skills.json`` file.  Defaults to
        ``data/skills.json`` in the project root.  Useful for testing.

    Returns
    -------
    list[str]
        Canonical skill names in document-appearance order, deduplicated.
        Returns ``[]`` for empty/whitespace-only input.

    Raises
    ------
    TypeError
        If *text* is not a ``str``.

    Notes
    -----
    - Section-aware mode (``sections["skills"]`` present) is more precise
      because it focuses on the dedicated skills section and avoids
      extracting technologies mentioned only in narrative experience text.
    - Fallback mode (no skills section) scans the full text but uses
      the same boundary-aware patterns, so false-positive risk is low.
    - Skills are never alphabetically sorted; document order is preserved.

    Examples
    --------
    >>> extract_skills("Python, Java, SQL, Docker")
    ['Python', 'Java', 'SQL', 'Docker']

    >>> extract_skills("", sections={})
    []
    """
    if not isinstance(text, str):
        raise TypeError(
            f"extract_skills() expects a str, got {type(text).__name__!r}."
        )

    if not text.strip():
        return []

    db = _get_db(db_path)

    # ── Section-aware mode ──────────────────────────────────────────────
    if sections and "skills" in sections and sections["skills"].strip():
        return _scan_text(sections["skills"], db)

    # ── Fallback: scan full text ─────────────────────────────────────────
    # Less precise — only use when no skills section is available.
    return _scan_text(text, db)
