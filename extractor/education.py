"""
education.py
------------
Responsible for extracting education history from the Education section text.

Fields per entry:
    - degree      → B.Tech, M.Tech, MBA, B.Sc, M.Sc, Ph.D, etc.
    - institution → adjacent capitalised line heuristic
    - year        → 4-digit year in range 1970–2035
    - score       → CGPA / GPA / percentage near relevant keywords

Public API:
    extract_education(section_text: str) -> list[dict]
        Returns a list of education entry dictionaries.
        Each dict contains: degree, institution, year, score (all nullable).
"""

# TODO: Implement degree, institution, year, and score extraction logic.
