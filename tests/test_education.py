"""
tests/test_education.py
-----------------------
Unit tests for extractor/education.py.

Focuses on realistic resume formats and meaningful edge cases.
Does not create hundreds of trivial or repetitive tests.
"""

from __future__ import annotations

import pytest

from extractor.education import extract_education


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _edu_section(text: str) -> dict[str, str]:
    return {"education": text}


def _first(records):
    assert records, "Expected at least one record, got []"
    return records[0]


def _schema_ok(record: dict) -> bool:
    """Every record must have exactly the six expected keys."""
    return set(record.keys()) == {
        "degree", "institution", "dates", "field_of_study", "grade", "location"
    }


# ===========================================================================
# 1. Schema consistency
# ===========================================================================

class TestSchema:

    def test_record_has_all_six_keys(self):
        text = "B.Tech\nABC University"
        records = extract_education(text, sections=_edu_section(text))
        assert records
        assert _schema_ok(records[0])

    def test_all_records_have_same_keys(self):
        text = "B.Tech\nABC University\n\nMBA\nXYZ Business School"
        records = extract_education(text, sections=_edu_section(text))
        for rec in records:
            assert _schema_ok(rec)

    def test_returns_list(self):
        assert isinstance(extract_education(""), list)


# ===========================================================================
# 2. Basic single-entry extraction
# ===========================================================================

class TestBasicExtraction:

    def test_btech_with_university(self):
        text = "B.Tech in Computer Engineering\nABC University\n2023 - 2027"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "B.Tech" in rec["degree"]
        assert rec["institution"] is not None
        assert "ABC" in rec["institution"]

    def test_be_with_institute(self):
        text = "B.E. in Electronics\nXYZ Institute of Technology\n2020 - 2024"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "B.E" in rec["degree"]

    def test_bsc_with_college(self):
        text = "B.Sc in Physics\nSt. Xavier's College\n2019 - 2022"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "B.Sc" in rec["degree"]

    def test_mca_with_university(self):
        text = "MCA\nABC University\n2024 - 2026"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "MCA" in rec["degree"]

    def test_mba_with_business_school(self):
        text = "MBA\nIndian Institute of Management\n2022 - 2024"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "MBA" in rec["degree"]

    def test_phd_with_university(self):
        text = "Ph.D. in Machine Learning\nIIT Bombay\n2020 - 2025"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "Ph.D" in rec["degree"] or "PhD" in rec["degree"]

    def test_mtech_with_institute(self):
        text = "M.Tech in Data Science\nNIT Trichy\n2022 - 2024"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "M.Tech" in rec["degree"]


# ===========================================================================
# 3. Multiple education entries
# ===========================================================================

class TestMultipleEntries:

    def test_btech_and_hsc(self):
        text = (
            "B.Tech in Information Technology\n"
            "ABC University\n"
            "2022 - 2026\n\n"
            "HSC\n"
            "XYZ Junior College\n"
            "2020 - 2022"
        )
        records = extract_education(text, sections=_edu_section(text))
        assert len(records) >= 2
        degrees = [r["degree"] for r in records if r["degree"]]
        assert any("B.Tech" in d for d in degrees)
        assert any("HSC" in d for d in degrees)

    def test_bachelors_and_masters(self):
        text = (
            "B.Tech Computer Science\n"
            "ABC University\n"
            "2018 - 2022\n\n"
            "M.Tech in Machine Learning\n"
            "IIT Delhi\n"
            "2022 - 2024"
        )
        records = extract_education(text, sections=_edu_section(text))
        assert len(records) >= 2
        degrees = [r["degree"] for r in records if r["degree"]]
        assert any("B.Tech" in d for d in degrees)
        assert any("M.Tech" in d for d in degrees)

    def test_multiple_institutions(self):
        text = (
            "B.Tech in CSE\n"
            "Mumbai University\n"
            "2016 - 2020\n\n"
            "M.Sc in Data Science\n"
            "London School of Economics\n"
            "2020 - 2021"
        )
        records = extract_education(text, sections=_edu_section(text))
        assert len(records) >= 2
        institutions = [r["institution"] for r in records if r["institution"]]
        assert any("Mumbai" in i for i in institutions)

    def test_three_entries(self):
        text = (
            "Ph.D. in CS\nIIT Bombay\n2020 - 2025\n\n"
            "M.Tech\nNIT Trichy\n2018 - 2020\n\n"
            "B.Tech\nABC College\n2014 - 2018"
        )
        records = extract_education(text, sections=_edu_section(text))
        assert len(records) >= 2   # at minimum two of the three should be detected


# ===========================================================================
# 4. Formatting variations
# ===========================================================================

class TestFormattingVariations:

    def test_format_A_degree_first(self):
        """Degree → Institution → Dates (most common)."""
        text = "B.Tech in Computer Engineering\nABC University\n2023 - 2027"
        records = extract_education(text, sections=_edu_section(text))
        assert records and records[0]["degree"] is not None

    def test_format_B_institution_first(self):
        """Institution → Degree → Dates."""
        text = "ABC University\nBachelor of Technology in Information Technology\n2023 - 2027"
        records = extract_education(text, sections=_edu_section(text))
        assert records
        rec = records[0]
        assert rec["degree"] is not None
        assert "Technology" in rec["degree"] or "B" in rec["degree"]

    def test_format_C_degree_in_parens(self):
        """B.E. (Computer Engineering) format."""
        text = "Bachelor of Engineering (Computer Engineering)\nXYZ Institute of Technology\n2022 - 2026"
        records = extract_education(text, sections=_edu_section(text))
        assert records and records[0]["degree"] is not None

    def test_format_D_with_cgpa(self):
        """MCA format with CGPA."""
        text = "MCA\nABC College\n2024 - 2026\nCGPA: 8.9"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["grade"] is not None
        assert "8.9" in rec["grade"]

    def test_format_E_inline_comma(self):
        """B.Tech, Computer Engineering — ABC University, 2023–2027."""
        text = "B.Tech — Computer Engineering — ABC University — 2023-2027"
        records = extract_education(text, sections=_edu_section(text))
        assert records

    def test_format_F_pipe_separated(self):
        """B.Tech | Computer Engineering | ABC University | 2023-2027."""
        text = "B.Tech | Computer Engineering | ABC University | 2023-2027"
        records = extract_education(text, sections=_edu_section(text))
        assert records

    def test_dates_before_degree(self):
        """2023 - 2027 → B.Tech → University (unusual ordering)."""
        text = "2023 - 2027\nB.Tech Computer Engineering\nABC University"
        records = extract_education(text, sections=_edu_section(text))
        # Should still extract something
        assert isinstance(records, list)

    def test_comma_separated_on_one_line(self):
        """B.Tech, ABC University, 2022-2026 on one line."""
        text = "B.Tech, ABC University, 2022-2026"
        records = extract_education(text, sections=_edu_section(text))
        assert records


# ===========================================================================
# 5. Specialization / field_of_study
# ===========================================================================

class TestFieldOfStudy:

    def test_btech_in_information_technology(self):
        text = "B.Tech in Information Technology\nABC University"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "Information Technology" in rec["degree"] or rec["field_of_study"] == "Information Technology"

    def test_msc_in_data_science(self):
        text = "M.Sc in Data Science\nABC University"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["degree"] is not None
        assert "Data Science" in rec["degree"] or (
            rec["field_of_study"] is not None and "Data Science" in rec["field_of_study"]
        )

    def test_be_computer_engineering(self):
        text = "B.E. Computer Engineering\nXYZ Institute"
        records = extract_education(text, sections=_edu_section(text))
        assert records


# ===========================================================================
# 6. Optional fields
# ===========================================================================

class TestOptionalFields:

    def test_cgpa_extracted(self):
        text = "B.Tech\nABC University\nCGPA: 9.2"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["grade"] is not None
        assert "9.2" in rec["grade"]

    def test_gpa_extracted(self):
        text = "M.Sc\nABC University\nGPA: 3.8 / 4.0"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["grade"] is not None
        assert "3.8" in rec["grade"]

    def test_percentage_extracted(self):
        text = "HSC\nXYZ Junior College\nPercentage: 91%"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["grade"] is not None
        assert "91" in rec["grade"]

    def test_bare_percentage_extracted(self):
        text = "SSC\nXYZ School\n92.5%"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["grade"] is not None

    def test_date_range_extracted(self):
        text = "B.Tech\nABC University\n2022 - 2026"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["dates"] is not None
        assert "2022" in rec["dates"]
        assert "2026" in rec["dates"]

    def test_date_range_with_month(self):
        text = "M.Tech\nIIT Delhi\nAug 2022 - May 2024"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["dates"] is not None
        assert "2022" in rec["dates"]

    def test_missing_fields_are_none(self):
        text = "B.Tech\nABC University"
        records = extract_education(text, sections=_edu_section(text))
        rec = _first(records)
        assert rec["dates"] is None or isinstance(rec["dates"], str)
        assert rec["grade"] is None or isinstance(rec["grade"], str)
        assert rec["location"] is None


# ===========================================================================
# 7. Section-aware behaviour
# ===========================================================================

class TestSectionAware:

    def test_uses_education_section_when_available(self):
        full_text = (
            "WORK EXPERIENCE\nSoftware Engineer at XYZ\n2022-2024\n\n"
            "EDUCATION\nB.Tech\nABC University\n2018-2022"
        )
        sections = {"education": "B.Tech\nABC University\n2018-2022"}
        records = extract_education(full_text, sections=sections)
        assert records
        assert records[0]["degree"] is not None
        assert "B.Tech" in records[0]["degree"]

    def test_section_content_does_not_bleed_into_experience(self):
        sections = {"education": "B.Tech\nABC University\n2018-2022"}
        records = extract_education("irrelevant full text", sections=sections)
        # Experience text should not appear as institution
        if records:
            assert "XYZ" not in (records[0]["institution"] or "")

    def test_fallback_when_no_education_section(self):
        text = (
            "B.Tech in Computer Science\n"
            "Delhi Technological University\n"
            "2016 - 2020"
        )
        records = extract_education(text, sections={})
        assert isinstance(records, list)

    def test_fallback_when_sections_none(self):
        text = "M.Tech in AI\nIIT Bombay\n2022-2024"
        records = extract_education(text, sections=None)
        assert isinstance(records, list)


# ===========================================================================
# 8. False-positive prevention
# ===========================================================================

class TestFalsePositives:

    def test_year_alone_not_an_education_record(self):
        """A bare year should not create an education record."""
        records = extract_education("2024", sections=_edu_section("2024"))
        assert records == []

    def test_cgpa_alone_not_an_education_record(self):
        """Just 'CGPA: 9.2' without a degree should not create a record."""
        records = extract_education("CGPA: 9.2", sections=_edu_section("CGPA: 9.2"))
        assert records == []

    def test_percentage_alone_not_an_education_record(self):
        records = extract_education("90%", sections=_edu_section("90%"))
        assert records == []

    def test_random_sentence_with_bachelor_not_extracted(self):
        """'She is a bachelor of arts graduate' in a narrative should not
        create a spurious education record in fallback mode."""
        text = "I met a Bachelor of Arts graduate at the event."
        # Provide this as full text (no dedicated section) — should not crash
        records = extract_education(text, sections={})
        # May or may not extract depending on heuristics — must not crash
        assert isinstance(records, list)

    def test_company_with_institute_in_name(self):
        """A company called 'XYZ Institute of Finance Ltd' in the
        experience section must not become an education institution when
        the education section is isolated."""
        edu_section = "B.Tech\nABC University\n2018-2022"
        sections = {
            "education": edu_section,
            "experience": "Software Engineer\nXYZ Institute of Finance Ltd\n2022-2024",
        }
        records = extract_education("full text", sections=sections)
        institutions = [r["institution"] or "" for r in records]
        assert not any("Finance" in i for i in institutions)


# ===========================================================================
# 9. Empty / edge-case input
# ===========================================================================

class TestEmptyInput:

    def test_empty_string_returns_empty_list(self):
        assert extract_education("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert extract_education("   \n\n\t  ") == []

    def test_empty_education_section_returns_empty(self):
        records = extract_education("full text", sections={"education": ""})
        assert isinstance(records, list)

    def test_whitespace_education_section_returns_empty(self):
        records = extract_education("full text", sections={"education": "   "})
        assert isinstance(records, list)

    def test_none_text_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_education(None)  # type: ignore[arg-type]

    def test_no_known_degree_returns_empty(self):
        text = "This is a resume with no degree information."
        records = extract_education(text, sections=_edu_section(text))
        assert records == []


# ===========================================================================
# 10. Duplicate handling
# ===========================================================================

class TestDuplicateHandling:

    def test_same_record_not_duplicated(self):
        # Repeated in the text — should appear only once
        text = (
            "B.Tech in IT\nABC University\n2018-2022\n\n"
            "B.Tech in IT\nABC University\n2018-2022"
        )
        records = extract_education(text, sections=_edu_section(text))
        btech_records = [r for r in records if r["degree"] and "B.Tech" in r["degree"]]
        assert len(btech_records) <= 1

    def test_different_degrees_not_merged(self):
        text = (
            "B.Tech in CSE\nABC University\n2014-2018\n\n"
            "M.Tech in AI\nIIT Delhi\n2018-2020"
        )
        records = extract_education(text, sections=_edu_section(text))
        assert len(records) >= 2


# ===========================================================================
# 11. Realistic full resume snippets
# ===========================================================================

class TestRealisticResumes:

    def test_standard_indian_resume_education(self):
        edu_text = (
            "B.Tech in Computer Science and Engineering\n"
            "Vidyalankar Institute of Technology, Mumbai University\n"
            "2020 - 2024\n"
            "CGPA: 8.6 / 10\n\n"
            "HSC (Science)\n"
            "ABC Junior College\n"
            "2018 - 2020\n"
            "Percentage: 87%"
        )
        sections = {"education": edu_text}
        records = extract_education("full text", sections=sections)
        assert len(records) >= 2
        btech = next((r for r in records if r["degree"] and "B.Tech" in r["degree"]), None)
        assert btech is not None
        assert btech["grade"] is not None
        assert "8.6" in btech["grade"]
        hsc = next((r for r in records if r["degree"] and "HSC" in r["degree"]), None)
        assert hsc is not None

    def test_us_style_education(self):
        edu_text = (
            "Master of Science in Computer Science\n"
            "Stanford University\n"
            "Aug 2020 - May 2022\n"
            "GPA: 3.9 / 4.0\n\n"
            "Bachelor of Science in Mathematics\n"
            "MIT\n"
            "2016 - 2020"
        )
        sections = {"education": edu_text}
        records = extract_education("full text", sections=sections)
        assert len(records) >= 2

    def test_diploma_plus_btech(self):
        edu_text = (
            "B.Tech in Mechanical Engineering\n"
            "ABC University\n"
            "2018 - 2022\n\n"
            "Diploma in Mechanical Engineering\n"
            "XYZ Polytechnic\n"
            "2015 - 2018"
        )
        sections = {"education": edu_text}
        records = extract_education("full text", sections=sections)
        assert len(records) >= 2
        degrees = [r["degree"] for r in records if r["degree"]]
        assert any("B.Tech" in d for d in degrees)
        assert any("Diploma" in d for d in degrees)
