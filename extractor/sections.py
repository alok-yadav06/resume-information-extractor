"""
sections.py
-----------
Responsible for detecting logical section boundaries within resume text.

Strategy:
    - Define a keyword map: section_name → list of heading variants
    - Scan lines for case-insensitive keyword matches
    - Split the full text into named blocks between detected headings

Public API:
    detect_sections(clean_text: str) -> dict[str, str]
        Returns a mapping of section names to their corresponding text blocks.
        Example keys: "education", "experience", "skills", "contact", "projects"
"""

# TODO: Implement section heading detection and text splitting logic.
