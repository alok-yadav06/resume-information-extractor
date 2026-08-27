"""
skills.py
---------
Responsible for extracting technical and professional skills from resume text.

Strategy:
    - Load a curated reference list from data/skills.json
    - Perform case-insensitive whole-word matching against the full resume text
    - Return a deduplicated, sorted list of matched skill strings

Public API:
    extract_skills(clean_text: str, skills_db_path: str | Path | None = None) -> list[str]
        Returns a sorted list of skills found in the resume text.
"""

# TODO: Implement skills matching against the reference JSON list.
