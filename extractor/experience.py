"""
experience.py
-------------
Responsible for extracting work experience entries from the Experience section text.

Fields per entry:
    - title    → job title (title-case heuristic)
    - company  → company name (capitalised line near date range)
    - duration → raw date-range string (e.g. "Jan 2022 – Mar 2024")

Supported date-range formats:
    - "MMM YYYY – MMM YYYY"   e.g. "Jan 2022 – Mar 2024"
    - "MM/YYYY – MM/YYYY"
    - "YYYY – YYYY"
    - "... – Present"

Public API:
    extract_experience(section_text: str) -> list[dict]
        Returns a list of experience entry dictionaries.
        Each dict contains: title, company, duration (all nullable).
"""

# TODO: Implement date-range detection and job entry extraction logic.
