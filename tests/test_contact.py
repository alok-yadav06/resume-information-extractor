"""
tests/test_contact.py
---------------------
Unit tests for extractor/contact.py.

Covers: email extraction, phone extraction, name extraction,
false-positive handling, combined extraction, and edge cases.
"""

from __future__ import annotations

import pytest

from extractor.contact import (
    extract_contact_info,
    extract_email,
    extract_name,
    extract_phone,
)


# ===========================================================================
# EMAIL EXTRACTION
# ===========================================================================

class TestExtractEmail:
    """Tests for extract_email()."""

    # --- Standard formats ---------------------------------------------------

    def test_simple_email(self):
        assert extract_email("john.doe@gmail.com") == "john.doe@gmail.com"

    def test_email_with_dots_in_local(self):
        assert extract_email("john.doe.jr@example.com") == "john.doe.jr@example.com"

    def test_email_with_underscore(self):
        assert extract_email("john_doe123@example.co.in") == "john_doe123@example.co.in"

    def test_email_with_plus_sign(self):
        assert extract_email("developer+test@company.org") == "developer+test@company.org"

    def test_email_with_hyphen_in_domain(self):
        assert extract_email("alice@my-company.com") == "alice@my-company.com"

    def test_email_subdomain(self):
        assert extract_email("alice@mail.example.co.uk") == "alice@mail.example.co.uk"

    def test_email_in_resume_header(self):
        text = "Alice Johnson\nalice@example.com\n+91 9876543210"
        assert extract_email(text) == "alice@example.com"

    # --- Label prefix -------------------------------------------------------

    def test_email_with_label_prefix(self):
        text = "Email: john@example.com"
        assert extract_email(text) == "john@example.com"

    def test_email_with_label_colon_space(self):
        text = "E-mail: alice@example.org"
        assert extract_email(text) == "alice@example.org"

    # --- Case handling ------------------------------------------------------

    def test_email_returned_lowercase(self):
        result = extract_email("John.DOE@Gmail.COM")
        assert result == "john.doe@gmail.com"

    def test_email_mixed_case_domain(self):
        result = extract_email("Alice@Example.ORG")
        assert result == "alice@example.org"

    # --- Multiple emails — pick first ---------------------------------------

    def test_multiple_emails_returns_first(self):
        text = "first@example.com\nsecond@example.com"
        assert extract_email(text) == "first@example.com"

    # --- Trailing punctuation stripped --------------------------------------

    def test_trailing_period_not_included(self):
        text = "Contact me at john@example.com."
        result = extract_email(text)
        assert result == "john@example.com"
        assert not result.endswith(".")

    def test_trailing_comma_not_included(self):
        text = "john@example.com, please reply"
        result = extract_email(text)
        assert result == "john@example.com"

    def test_trailing_paren_not_included(self):
        text = "(john@example.com)"
        result = extract_email(text)
        assert result == "john@example.com"

    # --- No email -----------------------------------------------------------

    def test_no_email_returns_none(self):
        assert extract_email("Alice Johnson\n+91 9876543210") is None

    def test_empty_string_returns_none(self):
        assert extract_email("") is None

    def test_whitespace_only_returns_none(self):
        assert extract_email("   \n\n\t  ") is None

    def test_email_like_word_without_at_returns_none(self):
        # "example" is not an email — no @ present
        assert extract_email("my example text") is None

    def test_at_only_returns_none(self):
        assert extract_email("hello @ world") is None

    # --- Type safety --------------------------------------------------------

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_email(None)  # type: ignore[arg-type]


# ===========================================================================
# PHONE EXTRACTION
# ===========================================================================

class TestExtractPhone:
    """Tests for extract_phone()."""

    # --- Indian formats -----------------------------------------------------

    def test_10_digit_indian_mobile(self):
        result = extract_phone("9876543210")
        assert result is not None
        assert "9876543210" in result.replace(" ", "").replace("-", "")

    def test_plus91_format(self):
        result = extract_phone("+91 9876543210")
        assert result is not None
        assert "9876543210" in result.replace(" ", "").replace("-", "")

    def test_plus91_hyphen_format(self):
        result = extract_phone("+91-9876543210")
        assert result is not None

    def test_plus91_space_split(self):
        result = extract_phone("+91 98765 43210")
        assert result is not None

    def test_91_without_plus(self):
        result = extract_phone("91 9876543210")
        assert result is not None

    # --- Separators ---------------------------------------------------------

    def test_hyphen_separated(self):
        result = extract_phone("987-654-3210")
        assert result is not None

    def test_space_separated(self):
        result = extract_phone("9876 543 210")
        assert result is not None

    def test_dot_separated(self):
        result = extract_phone("987.654.3210")
        assert result is not None

    # --- With label ---------------------------------------------------------

    def test_phone_with_label_prefix(self):
        result = extract_phone("Phone: +91 9876543210")
        assert result is not None

    def test_mobile_label(self):
        result = extract_phone("Mobile: 9876543210")
        assert result is not None

    # --- No phone -----------------------------------------------------------

    def test_no_phone_returns_none(self):
        text = "Alice Johnson\nalice@example.com"
        assert extract_phone(text) is None

    def test_empty_string_returns_none(self):
        assert extract_phone("") is None

    def test_whitespace_only_returns_none(self):
        assert extract_phone("   \n\n  ") is None

    # --- False-positive guards ----------------------------------------------

    def test_year_not_extracted_as_phone(self):
        """A 4-digit year must never be returned as a phone number."""
        text = "Graduated in 2024."
        result = extract_phone(text)
        # If anything is returned it must not be a bare 4-digit year.
        if result is not None:
            digits_only = "".join(c for c in result if c.isdigit())
            assert len(digits_only) >= 7, (
                f"Extracted '{result}' looks like a year, not a phone number."
            )

    def test_short_number_not_extracted(self):
        """Numbers with fewer than 7 digits must be rejected."""
        assert extract_phone("Code: 12345") is None

    def test_percentage_not_extracted_as_phone(self):
        """A number followed by % must not be returned as a phone number."""
        text = "CGPA: 8.5/10, Percentage: 85%"
        result = extract_phone(text)
        if result is not None:
            digits_only = "".join(c for c in result if c.isdigit())
            assert len(digits_only) >= 7

    def test_realistic_resume_with_phone_and_year(self):
        """Year (2020) adjacent to phone must not bleed into the phone result."""
        text = (
            "Alice Johnson\n"
            "Phone: +91 9876543210\n"
            "Graduated: 2020\n"
            "CGPA: 9.0"
        )
        result = extract_phone(text)
        assert result is not None
        assert "9876543210" in result.replace(" ", "").replace("-", "")

    # --- Type safety --------------------------------------------------------

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_phone(None)  # type: ignore[arg-type]


# ===========================================================================
# NAME EXTRACTION
# ===========================================================================

class TestExtractName:
    """Tests for extract_name()."""

    # --- Standard resume headers --------------------------------------------

    def test_simple_full_name(self):
        text = "Alice Johnson\nalice@example.com\n+91 9876543210"
        result = extract_name(text)
        assert result is not None
        assert "Alice" in result
        assert "Johnson" in result

    def test_two_word_name(self):
        text = "John Doe\nSoftware Engineer\njohn@example.com"
        result = extract_name(text)
        # Must select the name, not the job title.
        assert result is not None
        # "John Doe" should be returned; "Software Engineer" should not be.
        assert "Engineer" not in result

    def test_three_word_name(self):
        text = "Mary Jane Watson\nmary@example.com"
        result = extract_name(text)
        assert result is not None
        assert "Mary" in result

    def test_uppercase_name_title_cased(self):
        """ALL-CAPS name in resume should be returned title-cased."""
        text = "ALICE JOHNSON\nalice@example.com"
        result = extract_name(text)
        assert result is not None
        # Title-cased
        assert result == "Alice Johnson"

    def test_name_after_blank_lines(self):
        text = "\n\n\nBob Smith\nbob@example.com\n+91 9876543210"
        result = extract_name(text)
        assert result is not None
        assert "Bob" in result

    # --- Name must not be confused with headings ----------------------------

    def test_skills_heading_not_selected_as_name(self):
        text = "SKILLS\nPython\nJava"
        result = extract_name(text)
        assert result != "Skills"
        assert result != "SKILLS"
        # Either None or something other than the heading
        if result is not None:
            assert result.lower() not in {"skills", "python", "java"}

    def test_education_heading_not_selected_as_name(self):
        text = "EDUCATION\nB.Tech\nABC University"
        result = extract_name(text)
        if result is not None:
            assert result.lower() != "education"

    def test_experience_heading_not_selected_as_name(self):
        text = "WORK EXPERIENCE\nSoftware Engineer\nXYZ Corp"
        result = extract_name(text)
        if result is not None:
            assert "experience" not in result.lower()
            assert "work" not in result.lower()

    def test_summary_heading_not_selected_as_name(self):
        text = "SUMMARY\nPassionate software developer."
        result = extract_name(text)
        if result is not None:
            assert result.lower() != "summary"

    # --- Job title must not be selected as name -----------------------------

    def test_job_title_not_selected_as_name(self):
        """If the resume starts with a job title, it must not be returned."""
        text = "Software Engineer\njohn@example.com\n+91 9876543210"
        result = extract_name(text)
        # The job title should not be the name.
        if result is not None:
            assert "Engineer" not in result or "Software" not in result

    def test_data_analyst_not_selected_as_name(self):
        text = "Data Analyst\nalice@example.com"
        result = extract_name(text)
        if result is not None:
            assert "Analyst" not in result or "Data" not in result

    # --- Email/phone lines must not be selected ----------------------------

    def test_email_line_not_selected_as_name(self):
        text = "alice@example.com\n+91 9876543210\nAlice Johnson"
        result = extract_name(text)
        if result is not None:
            assert "@" not in result

    def test_phone_line_not_selected_as_name(self):
        text = "+91 9876543210\nAlice Johnson"
        result = extract_name(text)
        if result is not None:
            # A name should not be primarily digits
            digit_ratio = sum(1 for c in result if c.isdigit()) / len(result)
            assert digit_ratio < 0.5

    # --- Missing name -------------------------------------------------------

    def test_no_name_returns_none_for_empty_input(self):
        assert extract_name("") is None

    def test_no_name_returns_none_for_whitespace(self):
        assert extract_name("   \n\n\t  ") is None

    def test_name_from_realistic_header(self):
        text = (
            "Alice Johnson\n"
            "Email: alice@example.com\n"
            "Phone: +91 9876543210\n"
            "LinkedIn: linkedin.com/in/alice\n"
            "GitHub: github.com/alice\n"
        )
        result = extract_name(text)
        assert result is not None
        assert "Alice" in result
        assert "Johnson" in result

    # --- Type safety --------------------------------------------------------

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_name(None)  # type: ignore[arg-type]


# ===========================================================================
# COMBINED EXTRACTION — extract_contact_info()
# ===========================================================================

class TestExtractContactInfo:
    """Tests for the unified extract_contact_info() function."""

    def test_returns_dict_with_three_keys(self):
        result = extract_contact_info("Alice\nalice@example.com\n+91 9876543210")
        assert set(result.keys()) == {"name", "email", "phone"}

    def test_all_fields_extracted_from_complete_header(self):
        text = (
            "Alice Johnson\n"
            "alice.johnson@example.com\n"
            "+91 9876543210\n"
        )
        result = extract_contact_info(text)
        assert result["name"] is not None
        assert "Alice" in result["name"]
        assert result["email"] == "alice.johnson@example.com"
        assert result["phone"] is not None
        assert "9876543210" in result["phone"].replace(" ", "").replace("-", "")

    def test_empty_string_returns_all_none(self):
        result = extract_contact_info("")
        assert result == {"name": None, "email": None, "phone": None}

    def test_whitespace_only_returns_all_none(self):
        result = extract_contact_info("   \n\n\t  ")
        assert result == {"name": None, "email": None, "phone": None}

    def test_missing_email_is_none(self):
        result = extract_contact_info("Alice Johnson\n+91 9876543210")
        assert result["email"] is None

    def test_missing_phone_is_none(self):
        result = extract_contact_info("Alice Johnson\nalice@example.com")
        assert result["phone"] is None

    def test_values_are_str_or_none(self):
        result = extract_contact_info("Alice\nalice@example.com\n9876543210")
        for v in result.values():
            assert v is None or isinstance(v, str)

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_contact_info(None)  # type: ignore[arg-type]

    # --- Realistic full resume snippets ------------------------------------

    def test_realistic_resume_1(self):
        """Standard Indian tech resume header."""
        text = (
            "Rahul Sharma\n"
            "rahul.sharma@gmail.com\n"
            "+91 98765 43210\n\n"
            "SKILLS\nPython, Java, SQL\n\n"
            "EDUCATION\nB.Tech Computer Science\nABC University 2020"
        )
        result = extract_contact_info(text)
        assert result["email"] == "rahul.sharma@gmail.com"
        assert result["phone"] is not None
        assert "9876543210" in result["phone"].replace(" ", "")
        assert result["name"] is not None
        assert "Rahul" in result["name"]

    def test_realistic_resume_2_with_labels(self):
        """Resume where contact fields have explicit labels."""
        text = (
            "PRIYA PATEL\n"
            "Email: priya.patel@example.co.in\n"
            "Phone: +91-9988776655\n"
            "LinkedIn: linkedin.com/in/priya\n\n"
            "PROFESSIONAL SUMMARY\n"
            "Experienced data analyst with 4 years in fintech.\n\n"
            "SKILLS\nPython, R, Tableau, SQL"
        )
        result = extract_contact_info(text)
        assert result["email"] == "priya.patel@example.co.in"
        assert result["phone"] is not None
        assert result["name"] is not None
        assert "Priya" in result["name"]

    def test_realistic_resume_3_missing_fields(self):
        """Resume with only an email — phone and name may be absent."""
        text = (
            "WORK EXPERIENCE\n"
            "Software Engineer at XYZ\n"
            "contact: nobody@example.com\n"
        )
        result = extract_contact_info(text)
        assert result["email"] == "nobody@example.com"
        # Name and phone may or may not be extracted — must not crash.
        assert "name" in result
        assert "phone" in result

    def test_year_in_resume_does_not_become_phone(self):
        """Year values scattered through a resume must not be extracted as phone."""
        text = (
            "Alice Johnson\n"
            "alice@example.com\n\n"
            "EDUCATION\n"
            "B.Tech Computer Science\n"
            "Graduated: 2020\n"
            "CGPA: 8.7 / 10\n\n"
            "WORK EXPERIENCE\n"
            "XYZ Corp — Jan 2022 to Mar 2024"
        )
        result = extract_contact_info(text)
        # Phone must be None or a real phone number, never a year.
        phone = result["phone"]
        if phone is not None:
            digits_only = "".join(c for c in phone if c.isdigit())
            assert len(digits_only) >= 7, (
                f"Extracted phone '{phone}' looks too short to be real."
            )

    def test_percentage_in_resume_does_not_become_phone(self):
        """Percentages in education section must not be returned as phone."""
        text = (
            "Bob Kumar\nbob@example.com\n\n"
            "EDUCATION\nB.Tech — 88.5%\n2020"
        )
        result = extract_contact_info(text)
        phone = result["phone"]
        if phone is not None:
            digits_only = "".join(c for c in phone if c.isdigit())
            assert len(digits_only) >= 7
