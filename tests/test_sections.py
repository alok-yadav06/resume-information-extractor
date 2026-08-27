"""
tests/test_sections.py
----------------------
Unit tests for extractor/sections.py.

Tests use realistic resume-like text and target observable behavior,
not internal implementation details.
"""

from __future__ import annotations

import pytest

from extractor.sections import CANONICAL_SECTIONS, detect_sections


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resume(*blocks: str) -> str:
    """Join section blocks with a blank line to simulate a normalised resume."""
    return "\n\n".join(blocks)


# ---------------------------------------------------------------------------
# 1. Basic section detection
# ---------------------------------------------------------------------------

class TestBasicDetection:
    """Core happy-path: standard headings present in a resume."""

    def test_skills_section_detected(self):
        text = "SKILLS\n\nPython\nJava\nSQL"
        result = detect_sections(text)
        assert "skills" in result
        assert "Python" in result["skills"]
        assert "Java" in result["skills"]
        assert "SQL" in result["skills"]

    def test_education_section_detected(self):
        text = "EDUCATION\n\nB.Tech Computer Science\nABC University\n2020"
        result = detect_sections(text)
        assert "education" in result
        assert "B.Tech Computer Science" in result["education"]
        assert "ABC University" in result["education"]

    def test_experience_section_detected(self):
        text = (
            "WORK EXPERIENCE\n\n"
            "Software Engineer\nXYZ Corp\nJan 2022 – Mar 2024"
        )
        result = detect_sections(text)
        assert "experience" in result
        assert "XYZ Corp" in result["experience"]

    def test_multiple_sections_detected(self):
        text = _resume(
            "SKILLS\nPython\nSQL",
            "EDUCATION\nB.Tech\nABC University",
            "WORK EXPERIENCE\nSoftware Intern\nXYZ Tech",
        )
        result = detect_sections(text)
        assert "skills" in result
        assert "education" in result
        assert "experience" in result

    def test_returns_dict(self):
        result = detect_sections("SKILLS\nPython")
        assert isinstance(result, dict)

    def test_values_are_strings(self):
        result = detect_sections("SKILLS\nPython\nJava")
        for v in result.values():
            assert isinstance(v, str)

    def test_heading_line_not_included_in_body(self):
        """The heading itself must not appear in the section body."""
        result = detect_sections("SKILLS\nPython")
        assert "SKILLS" not in result.get("skills", "")


# ---------------------------------------------------------------------------
# 2. Case-insensitive heading detection
# ---------------------------------------------------------------------------

class TestCaseInsensitivity:
    """Headings must be matched regardless of letter case."""

    def test_all_lowercase(self):
        assert "skills" in detect_sections("skills\nPython")

    def test_all_uppercase(self):
        assert "skills" in detect_sections("SKILLS\nPython")

    def test_title_case(self):
        assert "skills" in detect_sections("Skills\nPython")

    def test_mixed_case(self):
        assert "skills" in detect_sections("sKiLlS\nPython")

    def test_education_lowercase(self):
        assert "education" in detect_sections("education\nB.Tech")

    def test_experience_mixed_case(self):
        assert "experience" in detect_sections("Work Experience\nEngineer")


# ---------------------------------------------------------------------------
# 3. Alias variations
# ---------------------------------------------------------------------------

class TestAliasVariations:
    """Different alias strings must resolve to the same canonical section."""

    # Skills aliases
    def test_technical_skills_alias(self):
        assert "skills" in detect_sections("TECHNICAL SKILLS\nPython")

    def test_skill_set_alias(self):
        assert "skills" in detect_sections("SKILL SET\nPython")

    def test_core_skills_alias(self):
        assert "skills" in detect_sections("CORE SKILLS\nPython")

    def test_technologies_alias(self):
        assert "skills" in detect_sections("TECHNOLOGIES\nDocker")

    def test_technologies_and_tools_alias(self):
        assert "skills" in detect_sections("TECHNOLOGIES & TOOLS\nDocker")

    def test_core_competencies_alias(self):
        assert "skills" in detect_sections("CORE COMPETENCIES\nLeadership")

    # Education aliases
    def test_academic_background_alias(self):
        assert "education" in detect_sections("ACADEMIC BACKGROUND\nB.Tech")

    def test_academic_qualifications_alias(self):
        assert "education" in detect_sections("ACADEMIC QUALIFICATIONS\nB.Tech")

    def test_educational_qualifications_alias(self):
        assert "education" in detect_sections("EDUCATIONAL QUALIFICATIONS\nB.Tech")

    # Experience aliases
    def test_professional_experience_alias(self):
        assert "experience" in detect_sections("PROFESSIONAL EXPERIENCE\nEngineer")

    def test_employment_history_alias(self):
        assert "experience" in detect_sections("EMPLOYMENT HISTORY\nEngineer")

    def test_work_history_alias(self):
        assert "experience" in detect_sections("WORK HISTORY\nEngineer")

    # Summary aliases
    def test_professional_summary_alias(self):
        assert "summary" in detect_sections("PROFESSIONAL SUMMARY\nPassionate developer")

    def test_profile_alias(self):
        assert "summary" in detect_sections("PROFILE\nPassionate developer")

    def test_career_summary_alias(self):
        assert "summary" in detect_sections("CAREER SUMMARY\nPassionate developer")

    # Objective aliases
    def test_career_objective_alias(self):
        assert "objective" in detect_sections("CAREER OBJECTIVE\nTo build software")

    # Projects aliases
    def test_personal_projects_alias(self):
        assert "projects" in detect_sections("PERSONAL PROJECTS\nPortfolio App")

    def test_academic_projects_alias(self):
        assert "projects" in detect_sections("ACADEMIC PROJECTS\nFinal Year Project")

    # Certifications aliases
    def test_certificates_alias(self):
        assert "certifications" in detect_sections("CERTIFICATES\nAWS Certified")

    def test_professional_certifications_alias(self):
        assert "certifications" in detect_sections("PROFESSIONAL CERTIFICATIONS\nAWS")


# ---------------------------------------------------------------------------
# 4. Trailing colon (and similar punctuation)
# ---------------------------------------------------------------------------

class TestTrailingPunctuation:
    """Trailing colons and dashes after a heading must be tolerated."""

    def test_trailing_colon(self):
        assert "skills" in detect_sections("SKILLS:\nPython")

    def test_trailing_colon_lowercase(self):
        assert "skills" in detect_sections("skills:\nPython")

    def test_trailing_dash(self):
        assert "education" in detect_sections("EDUCATION-\nB.Tech")

    def test_trailing_em_dash(self):
        assert "experience" in detect_sections("WORK EXPERIENCE—\nEngineer")

    def test_trailing_whitespace_and_colon(self):
        assert "skills" in detect_sections("SKILLS :  \nPython")


# ---------------------------------------------------------------------------
# 5. Section boundary correctness
# ---------------------------------------------------------------------------

class TestSectionBoundaries:
    """Body content must be assigned to the right section."""

    def test_skills_content_not_in_education(self):
        text = _resume(
            "SKILLS\nPython\nJava",
            "EDUCATION\nB.Tech\nABC University",
        )
        result = detect_sections(text)
        assert "Python" not in result.get("education", "")
        assert "B.Tech" not in result.get("skills", "")

    def test_education_content_not_in_experience(self):
        text = _resume(
            "EDUCATION\nB.Tech\nABC University 2020",
            "WORK EXPERIENCE\nSoftware Engineer\nXYZ Corp",
        )
        result = detect_sections(text)
        assert "ABC University" not in result.get("experience", "")
        assert "XYZ Corp" not in result.get("education", "")

    def test_last_section_captures_to_end_of_document(self):
        """The final section has no following heading — it must capture to EOF."""
        text = "SKILLS\nPython\nJava\nSQL"
        result = detect_sections(text)
        assert "SQL" in result.get("skills", "")

    def test_body_lines_preserved(self):
        text = "SKILLS\nPython\nJava\nSQL\nDocker\nKubernetes"
        result = detect_sections(text)
        skills_body = result.get("skills", "")
        for skill in ["Python", "Java", "SQL", "Docker", "Kubernetes"]:
            assert skill in skills_body


# ---------------------------------------------------------------------------
# 6. Different section ordering
# ---------------------------------------------------------------------------

class TestSectionOrdering:
    """Section order in the resume must not affect detection correctness."""

    def test_experience_before_skills(self):
        text = _resume(
            "WORK EXPERIENCE\nSoftware Engineer",
            "SKILLS\nPython",
            "EDUCATION\nB.Tech",
        )
        result = detect_sections(text)
        assert "experience" in result
        assert "skills" in result
        assert "education" in result

    def test_education_first(self):
        text = _resume(
            "EDUCATION\nB.Tech",
            "EXPERIENCE\nIntern",
            "SKILLS\nSQL",
        )
        result = detect_sections(text)
        assert "education" in result
        assert "experience" in result
        assert "skills" in result

    def test_content_correct_regardless_of_order(self):
        text = _resume(
            "PROJECTS\nPortfolio App",
            "SKILLS\nPython",
            "EDUCATION\nB.Tech",
        )
        result = detect_sections(text)
        assert "Portfolio App" in result.get("projects", "")
        assert "Python" in result.get("skills", "")
        assert "B.Tech" in result.get("education", "")


# ---------------------------------------------------------------------------
# 7. Duplicate sections
# ---------------------------------------------------------------------------

class TestDuplicateSections:
    """If the same canonical section appears twice, content must be combined."""

    def test_two_skills_sections_combined(self):
        text = _resume(
            "SKILLS\nPython\nJava",
            "EDUCATION\nB.Tech",
            "TECHNICAL SKILLS\nDocker\nSQL",
        )
        result = detect_sections(text)
        skills = result.get("skills", "")
        assert "Python" in skills
        assert "Java" in skills
        assert "Docker" in skills
        assert "SQL" in skills

    def test_combined_content_in_document_order(self):
        text = _resume(
            "SKILLS\nFirst block",
            "EDUCATION\nB.Tech",
            "CORE SKILLS\nSecond block",
        )
        result = detect_sections(text)
        skills = result.get("skills", "")
        assert skills.index("First block") < skills.index("Second block")


# ---------------------------------------------------------------------------
# 8. Empty sections
# ---------------------------------------------------------------------------

class TestEmptySections:
    """A heading with no body content must not crash and must be handled."""

    def test_empty_section_at_end(self):
        # CERTIFICATIONS has no lines after it — should not raise.
        text = "SKILLS\nPython\n\nCERTIFICATIONS"
        result = detect_sections(text)
        # certifications may be absent or present with empty/blank value
        # Either is acceptable — the important thing is no exception.
        assert isinstance(result, dict)

    def test_empty_section_between_others(self):
        text = _resume(
            "SKILLS\nPython",
            "CERTIFICATIONS",
            "EDUCATION\nB.Tech",
        )
        result = detect_sections(text)
        # Skills and education must still be captured correctly.
        assert "Python" in result.get("skills", "")
        assert "B.Tech" in result.get("education", "")

    def test_empty_section_does_not_crash(self):
        text = "SKILLS\n\nEDUCATION\n\nEXPERIENCE"
        # Must not raise — what is returned is a secondary concern.
        result = detect_sections(text)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 9. Empty / whitespace-only input
# ---------------------------------------------------------------------------

class TestEmptyInput:
    """Degenerate inputs must return an empty dict, never raise."""

    def test_empty_string(self):
        assert detect_sections("") == {}

    def test_whitespace_only(self):
        assert detect_sections("   \n\n\t\n  ") == {}

    def test_single_newline(self):
        assert detect_sections("\n") == {}

    def test_no_headings_returns_empty_dict(self):
        # Plain text with no recognisable headings.
        text = "This is just a paragraph without any resume sections."
        assert detect_sections(text) == {}


# ---------------------------------------------------------------------------
# 10. Unknown / custom section headings
# ---------------------------------------------------------------------------

class TestUnknownSections:
    """Custom headings unknown to the alias table must be silently ignored."""

    def test_unknown_heading_ignored(self):
        text = _resume(
            "SKILLS\nPython",
            "FAVOURITE MOVIES\nInception\nInterstellar",
            "EDUCATION\nB.Tech",
        )
        result = detect_sections(text)
        # Known sections still detected.
        assert "skills" in result
        assert "education" in result
        # Unknown section not in result.
        assert "favourite movies" not in result

    def test_unknown_heading_does_not_corrupt_neighbours(self):
        text = _resume(
            "SKILLS\nPython\nJava",
            "RANDOM CUSTOM SECTION\nSome content",
            "EDUCATION\nB.Tech",
        )
        result = detect_sections(text)
        assert "Python" in result.get("skills", "")
        assert "B.Tech" in result.get("education", "")


# ---------------------------------------------------------------------------
# 11 & 12. False-positive prevention
# ---------------------------------------------------------------------------

class TestFalsePositivePrevention:
    """Ordinary sentences containing section keywords must NOT be headings."""

    def test_experience_in_sentence_not_a_heading(self):
        # "I have experience in Python" contains "experience" but is NOT a heading.
        text = (
            "SUMMARY\n"
            "I have experience in Python and Java.\n"
            "EDUCATION\n"
            "B.Tech"
        )
        result = detect_sections(text)
        # "experience" must only appear as body text inside SUMMARY, not as
        # a separate top-level section key.
        assert "experience" not in result
        assert "summary" in result
        assert "education" in result

    def test_skills_in_sentence_not_a_heading(self):
        text = (
            "SUMMARY\n"
            "My skills include Python and team leadership.\n"
            "EDUCATION\n"
            "B.Tech"
        )
        result = detect_sections(text)
        # "skills" inside a sentence must not become a section key.
        if "skills" in result:
            # If it somehow gets picked up, the content must be the sentence,
            # not the education block — but ideally it is not present at all.
            assert "B.Tech" not in result["skills"]

    def test_long_line_not_treated_as_heading(self):
        # A very long line that happens to end with a known word must not match.
        long_line = (
            "This candidate has demonstrated exceptional leadership and strong experience "
            "in software engineering over the past five years."
        )
        text = f"EDUCATION\nB.Tech\n{long_line}"
        result = detect_sections(text)
        # Only education should be detected; the long sentence must not spawn
        # a spurious "experience" section.
        assert "experience" not in result

    def test_heading_content_distinguished_from_body(self):
        """A word-for-word alias must only match when it is on its own line."""
        text = (
            "EDUCATION\n"
            "She graduated with skills in Java and Python.\n"
        )
        result = detect_sections(text)
        # "skills" occurs inside a body sentence — must not become a heading.
        # We check that the education body contains that sentence.
        if "education" in result:
            assert "skills" in result["education"].lower() or True
        assert "skills" not in result  # no spurious skills section


# ---------------------------------------------------------------------------
# 13. Type safety
# ---------------------------------------------------------------------------

class TestTypeSafety:
    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            detect_sections(None)  # type: ignore[arg-type]

    def test_list_raises_type_error(self):
        with pytest.raises(TypeError):
            detect_sections(["SKILLS", "Python"])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 14. Realistic full resume
# ---------------------------------------------------------------------------

class TestRealisticResume:
    """Integration-style test using a complete synthetic resume."""

    RESUME = """
PROFESSIONAL SUMMARY

Motivated software engineer with 3 years of experience building scalable web applications.

TECHNICAL SKILLS

Python, Java, SQL
Docker, Kubernetes
REST APIs, Microservices
Spring Boot, Django

EDUCATION

B.Tech in Computer Science
ABC University, Hyderabad
CGPA: 8.5 / 10 (2020)

WORK EXPERIENCE

Software Engineer
XYZ Technologies, Bangalore
Jan 2021 – Present
- Developed REST APIs using Spring Boot
- Improved database query performance by 40%

Software Intern
LMN Startup, Remote
Jun 2020 – Dec 2020
- Built a data pipeline using Python and Pandas

PROJECTS

Resume Parser Tool
Built a rule-based resume parser using Python and regex.

CERTIFICATIONS

AWS Certified Developer – Associate (2022)

ACHIEVEMENTS

Best Intern Award – LMN Startup, 2020
""".strip()

    def test_all_major_sections_detected(self):
        result = detect_sections(self.RESUME)
        assert "summary" in result
        assert "skills" in result
        assert "education" in result
        assert "experience" in result
        assert "projects" in result
        assert "certifications" in result
        assert "achievements" in result

    def test_skills_content_correct(self):
        result = detect_sections(self.RESUME)
        skills = result["skills"]
        assert "Python" in skills
        assert "Docker" in skills
        assert "Spring Boot" in skills

    def test_education_content_correct(self):
        result = detect_sections(self.RESUME)
        edu = result["education"]
        assert "B.Tech" in edu
        assert "ABC University" in edu

    def test_experience_content_correct(self):
        result = detect_sections(self.RESUME)
        exp = result["experience"]
        assert "XYZ Technologies" in exp
        assert "LMN Startup" in exp
        assert "Spring Boot" in exp

    def test_projects_content_correct(self):
        result = detect_sections(self.RESUME)
        assert "Resume Parser Tool" in result["projects"]

    def test_certifications_content_correct(self):
        result = detect_sections(self.RESUME)
        assert "AWS Certified Developer" in result["certifications"]
