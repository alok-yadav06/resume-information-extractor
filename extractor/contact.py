"""
contact.py
----------
Responsible for extracting contact and identity information from resume text.

Fields extracted:
    - Full Name     → heuristic: first capitalised line in top-5 lines
    - Email         → RFC-5321 regex
    - Phone         → flexible international phone regex
    - LinkedIn URL  → pattern: linkedin.com/in/<handle>
    - GitHub URL    → pattern: github.com/<handle>

Public API:
    extract_name(clean_text: str) -> str | None
    extract_email(clean_text: str) -> str | None
    extract_phone(clean_text: str) -> str | None
    extract_linkedin(clean_text: str) -> str | None
    extract_github(clean_text: str) -> str | None
"""

# TODO: Implement regex-based contact field extraction.
