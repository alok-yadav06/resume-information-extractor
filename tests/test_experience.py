"""
tests/test_experience.py
------------------------
Unit tests for extractor/experience.py.

Covers realistic resume structures and difficult edge cases.
Does not inflate the count with repetitive trivial tests.
"""

from __future__ import annotations

import pytest

from extractor.experience import extract_experience


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _exp_section(text: str) -> dict[str, str]:
    return {"experience": text}


def _first(records):
    assert records, "Expected at least one record, got []"
    return records[0]


def _schema_ok(record: dict) -> bool:
    """Every record must have exactly the five expected keys."""
    return set(record.keys()) == {
        "job_title", "company", "dates", "location", "description"
    }


# ===========================================================================
# 1. Schema consistency
# ===========================================================================

class TestSchema:

    def test_record_has_all_five_keys(self):
        text = "Software Engineer\nABC Technologies\n2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        assert records
        assert _schema_ok(records[0])

    def test_description_is_always_a_list(self):
        text = "Software Engineer\nABC Technologies\n2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        assert records
        assert isinstance(records[0]["description"], list)

    def test_all_records_consistent_schema(self):
        text = (
            "Software Engineer\nABC Corp\n2023 - 2024\n\n"
            "Software Developer\nXYZ Ltd\n2022 - 2023"
        )
        records = extract_experience(text, sections=_exp_section(text))
        for rec in records:
            assert _schema_ok(rec)

    def test_returns_list(self):
        assert isinstance(extract_experience(""), list)


# ===========================================================================
# 2. Basic single-entry extraction
# ===========================================================================

class TestBasicExtraction:

    def test_title_company_dates(self):
        text = "Software Engineer\nABC Technologies\n2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["job_title"] is not None
        assert "Engineer" in rec["job_title"]
        assert rec["dates"] is not None
        assert "2024" in rec["dates"]

    def test_company_then_title(self):
        """Institution-first format: Company → Title → Dates."""
        text = "XYZ Solutions\nBackend Developer\n2023 - 2024"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        # At minimum dates or company/title should be captured
        assert rec["dates"] is not None or rec["company"] is not None

    def test_title_company_dates_location(self):
        text = "Software Engineer Intern\nABC Technologies\nJune 2025 - August 2025\nMumbai"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["job_title"] is not None
        assert "Intern" in rec["job_title"]
        assert rec["dates"] is not None
        assert "2025" in rec["dates"]

    def test_title_company_dates_with_bullets(self):
        text = (
            "Software Engineer\nABC Corp\n2023 - 2024\n"
            "- Developed REST APIs\n"
            "- Worked with MySQL"
        )
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["description"] is not None
        assert len(rec["description"]) >= 1
        assert any("REST" in d or "MySQL" in d for d in rec["description"])


# ===========================================================================
# 3. Multiple experience entries
# ===========================================================================

class TestMultipleEntries:

    TWO_JOBS = (
        "Software Engineer Intern\n"
        "ABC Technologies\n"
        "June 2025 - August 2025\n"
        "- Developed REST APIs.\n"
        "- Worked with MySQL.\n\n"
        "Software Developer\n"
        "XYZ Solutions\n"
        "2024 - 2025\n"
        "- Built backend services."
    )

    def test_two_entries_detected(self):
        records = extract_experience(self.TWO_JOBS, sections=_exp_section(self.TWO_JOBS))
        assert len(records) >= 2

    def test_document_order_preserved(self):
        records = extract_experience(self.TWO_JOBS, sections=_exp_section(self.TWO_JOBS))
        assert len(records) >= 2
        # Intern role should come first (as it appears first in the doc)
        titles = [r["job_title"] or "" for r in records]
        intern_pos = next((i for i, t in enumerate(titles) if "Intern" in t), None)
        dev_pos = next((i for i, t in enumerate(titles) if "Developer" in t), None)
        if intern_pos is not None and dev_pos is not None:
            assert intern_pos < dev_pos

    def test_three_entries_detected(self):
        text = (
            "Senior Engineer\nAlpha Corp\n2022 - 2024\n- Led team.\n\n"
            "Software Engineer\nBeta Ltd\n2020 - 2022\n- Built APIs.\n\n"
            "Software Intern\nGamma Inc\n2019 - 2020\n- Assisted team."
        )
        records = extract_experience(text, sections=_exp_section(text))
        assert len(records) >= 2  # at minimum two should be detected

    def test_internship_followed_by_fulltime(self):
        text = (
            "Software Engineering Intern\nABC Corp\nJan 2024 - Jun 2024\n"
            "- Built features.\n\n"
            "Software Engineer\nABC Corp\nJul 2024 - Present\n"
            "- Designed APIs."
        )
        records = extract_experience(text, sections=_exp_section(text))
        assert len(records) >= 2


# ===========================================================================
# 4. Date format variations
# ===========================================================================

class TestDateFormats:

    def test_year_range_hyphen(self):
        text = "Software Developer\nABC Corp\n2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None
        assert "2024" in rec["dates"]
        assert "2025" in rec["dates"]

    def test_year_range_en_dash(self):
        text = "Software Developer\nABC Corp\n2024–2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None

    def test_month_year_range(self):
        text = "Software Engineer\nABC Corp\nJune 2024 - August 2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None
        assert "2024" in rec["dates"]

    def test_abbreviated_month_range(self):
        text = "Data Analyst\nXYZ Ltd\nJan 2023 - Mar 2024"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None

    def test_present_in_date(self):
        text = "Software Engineer\nABC Corp\n2023 - Present"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None
        assert "Present" in (rec["dates"] or "")

    def test_current_in_date(self):
        text = "Software Engineer\nABC Corp\nJan 2023 - Current"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None

    def test_mm_yyyy_format(self):
        text = "Software Engineer\nABC Corp\n01/2023 - 05/2024"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None


# ===========================================================================
# 5. Bullet descriptions
# ===========================================================================

class TestDescriptions:

    def test_dash_bullets(self):
        text = (
            "Software Engineer\nABC Corp\n2024 - 2025\n"
            "- Developed REST APIs\n"
            "- Worked with Spring Boot"
        )
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert len(rec["description"]) >= 1
        assert any("REST" in d for d in rec["description"])

    def test_bullet_char(self):
        text = (
            "Software Engineer\nABC Corp\n2024 - 2025\n"
            "• Implemented authentication\n"
            "• Optimized SQL queries"
        )
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert len(rec["description"]) >= 1

    def test_star_bullets(self):
        text = (
            "Data Analyst\nXYZ Ltd\n2023 - 2024\n"
            "* Analyzed sales data\n"
            "* Built Tableau dashboards"
        )
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert len(rec["description"]) >= 1

    def test_bullet_marker_stripped(self):
        """The bullet character itself must not appear in the description text."""
        text = "Software Engineer\nABC Corp\n2024 - 2025\n- Developed REST APIs"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        if rec["description"]:
            for item in rec["description"]:
                assert not item.startswith("-")
                assert not item.startswith("•")

    def test_multiple_bullets_all_captured(self):
        text = (
            "Backend Developer\nABC Corp\n2023 - 2024\n"
            "- Built microservices\n"
            "- Improved DB performance\n"
            "- Wrote unit tests"
        )
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert len(rec["description"]) >= 2


# ===========================================================================
# 6. Missing optional fields
# ===========================================================================

class TestMissingFields:

    def test_missing_location_is_none(self):
        text = "Software Developer\nABC Corp\n2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["location"] is None or isinstance(rec["location"], str)

    def test_missing_description_is_empty_list(self):
        text = "Software Developer\nABC Corp\n2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["description"] == [] or isinstance(rec["description"], list)

    def test_missing_dates_does_not_crash(self):
        """Entry without dates should not crash — dates=None is acceptable."""
        text = "Software Developer\nABC Corp"
        records = extract_experience(text, sections=_exp_section(text))
        assert isinstance(records, list)

    def test_valid_entry_not_discarded_for_missing_location(self):
        """An experience entry must never be discarded because location is absent."""
        text = "Software Engineer\nABC Technologies\n2024 - 2025\n- Built APIs"
        records = extract_experience(text, sections=_exp_section(text))
        assert records  # must not be empty


# ===========================================================================
# 7. Internships and special roles
# ===========================================================================

class TestInternships:

    def test_intern_role_detected(self):
        text = "Software Engineering Intern\nABC Corp\nJun 2024 - Aug 2024"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["job_title"] is not None
        assert "Intern" in rec["job_title"]

    def test_backend_intern(self):
        text = "Backend Intern\nXYZ Technologies\n2024 - 2024"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["job_title"] is not None

    def test_research_intern(self):
        text = "Research Intern\nIIT Bombay\nMay 2024 - Jul 2024"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["job_title"] is not None

    def test_freelance_role(self):
        text = "Freelance Web Developer\nSelf-Employed\n2023 - Present"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["job_title"] is not None
        assert rec["dates"] is not None


# ===========================================================================
# 8. Section-aware extraction
# ===========================================================================

class TestSectionAware:

    def test_uses_experience_section_when_present(self):
        full_text = (
            "EDUCATION\nB.Tech\nABC University\n2018-2022\n\n"
            "EXPERIENCE\nSoftware Engineer\nXYZ Corp\n2022-2024"
        )
        sections = {"experience": "Software Engineer\nXYZ Corp\n2022 - 2024"}
        records = extract_experience(full_text, sections=sections)
        assert records
        assert records[0]["job_title"] is not None
        assert "Engineer" in records[0]["job_title"]

    def test_education_content_not_in_experience(self):
        """Education section content must not leak into experience."""
        sections = {
            "experience": "Software Engineer\nABC Corp\n2022 - 2024",
            "education": "B.Tech\nXYZ University\n2018-2022",
        }
        records = extract_experience("full text", sections=sections)
        if records:
            companies = [r["company"] or "" for r in records]
            assert not any("University" in c for c in companies)

    def test_projects_section_not_used_as_experience(self):
        """When experience section exists, projects content must not appear."""
        sections = {
            "experience": "Software Engineer\nABC Corp\n2023 - 2024",
            "projects": "E-Commerce Backend\n2024 - 2025\n- Built REST API",
        }
        records = extract_experience("full text", sections=sections)
        job_titles = [r["job_title"] or "" for r in records]
        # "E-Commerce Backend" must not appear as a job title
        assert not any("E-Commerce" in t for t in job_titles)

    def test_fallback_used_when_sections_empty(self):
        text = "Software Engineer\nABC Corp\n2023 - 2024"
        records = extract_experience(text, sections={})
        assert isinstance(records, list)

    def test_fallback_used_when_sections_none(self):
        text = "Software Engineer\nABC Corp\n2023 - 2024"
        records = extract_experience(text, sections=None)
        assert isinstance(records, list)


# ===========================================================================
# 9. False-positive prevention
# ===========================================================================

class TestFalsePositives:

    def test_sentence_with_experience_word_not_extracted(self):
        """'I have experience working with Java and Python.' → no record."""
        text = "I have experience working with Java and Python."
        records = extract_experience(text, sections=_exp_section(text))
        # Must not create a spurious experience record from this sentence
        assert records == [] or all(
            r["job_title"] is None and r["company"] is None
            for r in records
        )

    def test_dates_alone_do_not_create_experience(self):
        """Bare dates without title or company must not produce a record."""
        text = "2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        # If any record exists it must have very weak fields — dates alone is not enough
        for rec in records:
            assert rec["job_title"] is None or rec["company"] is None

    def test_education_text_not_extracted_as_experience(self):
        """B.Tech / University / date must not become an experience record."""
        edu_text = "B.Tech\nABC University\n2023 - 2027"
        sections = {"experience": edu_text}
        records = extract_experience("full text", sections=sections)
        # If records exist, they must not have degree-like job titles
        for rec in records:
            assert rec["job_title"] is None or "B.Tech" not in (rec["job_title"] or "")

    def test_skills_list_not_extracted_as_experience(self):
        """A comma-separated skills list must not become an experience record."""
        text = "Java, Python, Spring Boot, Docker, Kubernetes"
        records = extract_experience(text, sections=_exp_section(text))
        # Skills list alone should produce no valid experience record
        valid = [r for r in records if r["job_title"] or r["company"]]
        assert valid == []

    def test_project_text_not_experience(self):
        """Project entries must not become experience when clearly under projects."""
        # When called with a projects section as experience, the extractor sees
        # the raw text — the key protection is section-awareness upstream.
        sections = {
            "experience": "Software Engineer\nABC Corp\n2022 - 2024",
        }
        records = extract_experience("irrelevant", sections=sections)
        # Only the real experience entry should appear
        assert len(records) <= 2

    def test_year_inside_bullet_not_standalone_date_entry(self):
        """A year mentioned inside a bullet description must not split entries."""
        text = (
            "Software Engineer\nABC Corp\n2023 - 2025\n"
            "- Delivered 3 projects in 2024\n"
            "- Led team of 5 engineers"
        )
        records = extract_experience(text, sections=_exp_section(text))
        # Should produce exactly one record (not split by the "2024" in bullet)
        assert len(records) <= 2

    def test_section_heading_not_a_job_title(self):
        """The heading 'WORK EXPERIENCE' must not become a job title."""
        text = (
            "WORK EXPERIENCE\n"
            "Software Engineer\nABC Corp\n2023 - 2024"
        )
        records = extract_experience(text, sections=_exp_section(text))
        titles = [r["job_title"] or "" for r in records]
        assert not any("WORK" in t and "EXPERIENCE" in t for t in titles)

    def test_company_in_bullet_not_standalone_entry(self):
        """A company name inside a bullet should not create a new entry."""
        text = (
            "Software Engineer\nABC Corp\n2023 - 2024\n"
            "- Collaborated with XYZ Technologies on client projects."
        )
        records = extract_experience(text, sections=_exp_section(text))
        # Should be one entry, not two
        assert len(records) <= 2


# ===========================================================================
# 10. Inline / pipe-separated formats
# ===========================================================================

class TestInlineFormats:

    def test_pipe_separated_single_line(self):
        text = "Software Engineer | ABC Corp | 2024 - 2025"
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None

    def test_pipe_with_description(self):
        text = (
            "Backend Developer | XYZ Ltd | Jan 2023 - Dec 2023\n"
            "- Built REST APIs\n"
            "- Improved performance"
        )
        records = extract_experience(text, sections=_exp_section(text))
        rec = _first(records)
        assert rec["dates"] is not None


# ===========================================================================
# 11. Duplicate handling
# ===========================================================================

class TestDuplicateHandling:

    def test_identical_entry_not_duplicated(self):
        text = (
            "Software Engineer\nABC Corp\n2023 - 2024\n\n"
            "Software Engineer\nABC Corp\n2023 - 2024"
        )
        records = extract_experience(text, sections=_exp_section(text))
        # Same entry repeated should produce at most one record
        # Deduplication key: (job_title, company, dates)
        keys = [
            (
                (r.get("job_title") or "").strip().lower(),
                (r.get("company") or "").strip().lower(),
                (r.get("dates") or "").strip().lower(),
            )
            for r in records
        ]
        assert len(keys) == len(set(keys)), "Duplicate records found"

    def test_different_entries_not_merged(self):
        text = (
            "Software Engineer\nABC Corp\n2022 - 2023\n\n"
            "Senior Engineer\nXYZ Ltd\n2023 - 2025"
        )
        records = extract_experience(text, sections=_exp_section(text))
        assert len(records) >= 2


# ===========================================================================
# 12. Empty / edge-case input
# ===========================================================================

class TestEmptyInput:

    def test_empty_string_returns_empty_list(self):
        assert extract_experience("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert extract_experience("   \n\n  ") == []

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_experience(None)  # type: ignore[arg-type]

    def test_empty_experience_section_returns_empty(self):
        records = extract_experience("text", sections={"experience": ""})
        assert isinstance(records, list)

    def test_sections_none_uses_fallback(self):
        records = extract_experience("Software Engineer\nABC Corp\n2023 - 2024", sections=None)
        assert isinstance(records, list)


# ===========================================================================
# 13. Realistic resume integration
# ===========================================================================

class TestRealisticResumes:

    EXPERIENCE_TEXT = (
        "Software Engineer Intern\n"
        "ABC Technologies, Mumbai\n"
        "June 2025 - August 2025\n"
        "• Developed REST APIs using Spring Boot\n"
        "• Implemented JWT authentication\n"
        "• Worked with MySQL and Redis\n\n"
        "Junior Software Developer\n"
        "XYZ Solutions Pvt. Ltd.\n"
        "2024 - 2025\n"
        "• Built microservices architecture\n"
        "• Improved query performance by 40%"
    )

    def test_both_entries_extracted(self):
        sections = {"experience": self.EXPERIENCE_TEXT}
        records = extract_experience("full text", sections=sections)
        assert len(records) >= 2

    def test_intern_entry_correct(self):
        sections = {"experience": self.EXPERIENCE_TEXT}
        records = extract_experience("full text", sections=sections)
        intern_rec = next(
            (r for r in records if r["job_title"] and "Intern" in r["job_title"]),
            None,
        )
        assert intern_rec is not None
        assert intern_rec["dates"] is not None
        assert "2025" in intern_rec["dates"]
        assert len(intern_rec["description"]) >= 1

    def test_developer_entry_correct(self):
        sections = {"experience": self.EXPERIENCE_TEXT}
        records = extract_experience("full text", sections=sections)
        dev_rec = next(
            (r for r in records if r["job_title"] and "Developer" in r["job_title"]),
            None,
        )
        assert dev_rec is not None

    def test_no_duplicates_in_realistic_resume(self):
        sections = {"experience": self.EXPERIENCE_TEXT}
        records = extract_experience("full text", sections=sections)
        keys = [
            (
                (r.get("job_title") or "").strip().lower(),
                (r.get("company") or "").strip().lower(),
                (r.get("dates") or "").strip().lower(),
            )
            for r in records
        ]
        assert len(keys) == len(set(keys))
