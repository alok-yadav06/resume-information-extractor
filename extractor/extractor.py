"""
extractor.py
------------
Orchestrator for the full resume extraction pipeline.

Ties together all sub-modules in the correct order and assembles the
final structured JSON-serialisable dictionary.

Pipeline order:
    1. parser.parse_resume()     → raw text
    2. cleaner.clean_text()      → normalised text
    3. sections.detect_sections() → section map
    4. contact.*                 → name, email, phone, LinkedIn, GitHub
    5. skills.extract_skills()   → skills list
    6. education.extract_education() → education list
    7. experience.extract_experience() → experience list
    8. Assemble and return output dict

Public API:
    class ResumeExtractor:
        def extract(file_path: str | Path) -> dict
            Runs the full pipeline and returns a structured result dict.

Output schema:
    {
        "full_name":  str | None,
        "email":      str | None,
        "phone":      str | None,
        "linkedin":   str | None,
        "github":     str | None,
        "skills":     list[str],
        "education":  list[dict],
        "experience": list[dict]
    }
"""

# TODO: Implement the ResumeExtractor orchestrator class.
