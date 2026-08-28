"""
profiles.py
-----------
Extracts LinkedIn and GitHub profile URLs from cleaned resume text.

This module provides deterministic, rule-based extraction for social/developer
profiles as bonus fields.

Design overview
---------------
1.  Regex-based URL and handle recognition for LinkedIn and GitHub.
2.  Normalisation ensures consistent URLs (scheme prefix, trailing punctuation
    stripping, canonical path).
3.  False-positive guards reject generic mentions ("Follow us on LinkedIn"),
    unrelated websites, and deep repository URLs when ambiguous.
4.  Zero external network requests or API calls — all extraction is strictly local.

Public API
----------
extract_profiles(text: str) -> dict[str, str | None]
extract_linkedin(text: str) -> str | None
extract_github(text: str)   -> str | None
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Reserved / non-profile slugs on GitHub
# ---------------------------------------------------------------------------
_GITHUB_RESERVED_SLUGS: frozenset[str] = frozenset({
    "about", "pricing", "features", "explore", "topics", "trending",
    "collections", "events", "sponsors", "readme", "security",
    "customer-stories", "enterprise", "team", "settings", "notifications",
    "login", "signup", "join", "search", "pulls", "issues", "marketplace",
    "orgs", "organizations", "blog", "site", "contact", "support",
    "mobile", "desktop", "apps", "nonprofit", "education",
})

# ---------------------------------------------------------------------------
# Regex Patterns
# ---------------------------------------------------------------------------

# Trailing punctuation to strip from extracted URLs (e.g. at end of sentence)
_TRAILING_PUNCT_RE = re.compile(r"[.,;:)>\]\s/]+$")

# LinkedIn profile regex: matches linkedin.com/in/<username>
_LINKEDIN_URL_RE = re.compile(
    r"(?i)\b(?:https?://)?(?:[a-zA-Z0-9_\-]+\.)?linkedin\.com/in/([a-zA-Z0-9_\-%]+)(?:/[a-zA-Z0-9_\-%]*)?",
)

# Explicit label pattern for LinkedIn, e.g. "LinkedIn: johndoe" or "LinkedIn: in/johndoe"
_LINKEDIN_LABEL_RE = re.compile(
    r"(?i)(?:linkedin(?:\s+profile|\s+url)?\s*[:\-–—]\s*)(?:https?://)?(?:[a-zA-Z0-9_\-]+\.)?linkedin\.com/in/([a-zA-Z0-9_\-%]+)",
)

# GitHub profile URL regex: matches github.com/<username>
# Captures the username segment and ensures it is not immediately followed by /<repo>
_GITHUB_URL_RE = re.compile(
    r"(?i)\b(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9](?:[a-zA-Z0-9_\-]{0,38}))(?:\b|/|\Z)",
)

# GitHub repo pattern: github.com/<username>/<repo>
_GITHUB_REPO_RE = re.compile(
    r"(?i)\b(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-.]+)",
)


# ---------------------------------------------------------------------------
# Normalisation Helpers
# ---------------------------------------------------------------------------

def _clean_url(url: str) -> str:
    """Strip surrounding whitespace and trailing sentence punctuation."""
    cleaned = url.strip()
    cleaned = _TRAILING_PUNCT_RE.sub("", cleaned)
    return cleaned


def _normalize_scheme(url: str) -> str:
    """Ensure *url* begins with 'https://'."""
    url = _clean_url(url)
    if url.startswith("http://"):
        return "https://" + url[7:]
    if not url.startswith("https://"):
        return "https://" + url
    return url


# ---------------------------------------------------------------------------
# LinkedIn Extractor
# ---------------------------------------------------------------------------

def extract_linkedin(text: str) -> str | None:
    """
    Extract the primary LinkedIn profile URL from *text*.

    Recognises formats such as:
    - https://www.linkedin.com/in/johndoe
    - https://linkedin.com/in/johndoe
    - www.linkedin.com/in/johndoe
    - linkedin.com/in/johndoe
    - LinkedIn: https://linkedin.com/in/johndoe

    Returns
    -------
    str | None
        The normalised LinkedIn profile URL (https://...), or None if not found.
    """
    if not isinstance(text, str):
        raise TypeError(f"extract_linkedin expects a str, got {type(text).__name__!r}.")

    if not text.strip():
        return None

    # Pass 1: Check for explicit labeled match first
    label_match = _LINKEDIN_LABEL_RE.search(text)
    if label_match:
        full_match = label_match.group(0)
        # Extract the URL part after the label
        url_part = re.sub(r"(?i)^linkedin(?:\s+profile|\s+url)?\s*[:\-–—]\s*", "", full_match).strip()
        slug = label_match.group(1).strip()
        if slug and len(slug) >= 2:
            return _normalize_scheme(url_part)

    # Pass 2: Search for linkedin.com/in/ pattern
    for match in _LINKEDIN_URL_RE.finditer(text):
        slug = match.group(1).strip()
        # Ensure slug is not generic or empty
        if not slug or len(slug) < 2 or slug.lower() in ("in", "profile", "user"):
            continue
        raw_url = match.group(0)
        return _normalize_scheme(raw_url)

    return None


# ---------------------------------------------------------------------------
# GitHub Extractor
# ---------------------------------------------------------------------------

def extract_github(text: str) -> str | None:
    """
    Extract the primary GitHub profile URL from *text*.

    Recognises formats such as:
    - https://github.com/johndoe
    - https://www.github.com/johndoe
    - www.github.com/johndoe
    - github.com/johndoe
    - GitHub: https://github.com/johndoe

    Distinguishes profile URLs from deep repository URLs (e.g. github.com/user/repo).

    Returns
    -------
    str | None
        The normalised GitHub profile URL (https://...), or None if not found.
    """
    if not isinstance(text, str):
        raise TypeError(f"extract_github expects a str, got {type(text).__name__!r}.")

    if not text.strip():
        return None

    lines = text.splitlines()

    # Pass 1: Look for clean standalone profile URLs in text
    for line in lines:
        for match in _GITHUB_URL_RE.finditer(line):
            username = match.group(1).strip()
            if not username or len(username) < 2:
                continue
            if username.lower() in _GITHUB_RESERVED_SLUGS:
                continue

            # Verify this is not just the prefix of a deep repository URL on this line
            # e.g., "github.com/johndoe/project"
            end_pos = match.end()
            if end_pos < len(line) and line[end_pos:].startswith("/"):
                # Check if what follows is a repository name
                after_slash = line[end_pos + 1:].strip()
                repo_token = re.match(r"^[a-zA-Z0-9_\-]+", after_slash)
                if repo_token:
                    # It's a repository link; skip treating it as a bare profile match
                    continue

            raw_url = match.group(0)
            # Build normalized profile URL
            return f"https://github.com/{username}"

    # Pass 2: If a line is explicitly labelled "GitHub: <url>", extract username
    for line in lines:
        label_match = re.search(r"(?i)\bgithub(?:\s+profile|\s+url)?\s*[:\-–—]\s*(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9_\-]+)", line)
        if label_match:
            username = label_match.group(1).strip()
            if username.lower() not in _GITHUB_RESERVED_SLUGS and len(username) >= 2:
                return f"https://github.com/{username}"

    return None


# ---------------------------------------------------------------------------
# Public Aggregate API
# ---------------------------------------------------------------------------

def extract_profiles(text: str) -> dict[str, str | None]:
    """
    Extract social and professional profile links from resume text.

    Parameters
    ----------
    text:
        Cleaned resume text.

    Returns
    -------
    dict[str, str | None]
        {
            "linkedin": str | None,
            "github": str | None
        }

    Raises
    ------
    TypeError:
        If *text* is not a ``str``.
    """
    if not isinstance(text, str):
        raise TypeError(f"extract_profiles expects a str, got {type(text).__name__!r}.")

    return {
        "linkedin": extract_linkedin(text),
        "github": extract_github(text),
    }
