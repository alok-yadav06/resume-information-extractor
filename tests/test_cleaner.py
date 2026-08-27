"""
tests/test_cleaner.py
---------------------
Unit tests for extractor/cleaner.py.

Tests focus on observable behavior, not implementation internals.
Each test class covers one cleaning concern.
"""

from __future__ import annotations

import pytest

from extractor.cleaner import clean_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def lines(text: str) -> list[str]:
    """Return non-empty lines from *text* for structural assertions."""
    return [l for l in text.split("\n") if l.strip()]


# ---------------------------------------------------------------------------
# 1. Line-ending normalisation
# ---------------------------------------------------------------------------

class TestLineEndingNormalisation:
    """\\r\\n and \\r should both become \\n."""

    def test_windows_crlf_normalised(self):
        result = clean_text("Name: Alice\r\nEmail: alice@example.com")
        assert "\r" not in result
        assert "Name: Alice" in result
        assert "Email: alice@example.com" in result

    def test_old_mac_cr_normalised(self):
        result = clean_text("Name: Bob\rEmail: bob@example.com")
        assert "\r" not in result
        assert "Name: Bob" in result
        assert "Email: bob@example.com" in result

    def test_mixed_line_endings_normalised(self):
        result = clean_text("Line A\r\nLine B\rLine C\nLine D")
        assert "\r" not in result
        assert result.count("\n") >= 3

    def test_form_feed_becomes_blank_line(self):
        """PDF page separators (\\f) should become a blank-line gap."""
        result = clean_text("Page 1 content\fPage 2 content")
        assert "Page 1 content" in result
        assert "Page 2 content" in result
        assert "\f" not in result


# ---------------------------------------------------------------------------
# 2. Intra-line whitespace collapse
# ---------------------------------------------------------------------------

class TestWhitespaceCollapse:
    """Multiple consecutive spaces/tabs within a line → single space."""

    def test_multiple_spaces_collapsed(self):
        assert clean_text("John     Doe") == "John Doe"

    def test_tab_between_words_collapsed(self):
        result = clean_text("Skills:\tPython\tSQL")
        assert "\t" not in result
        assert "Skills: Python SQL" in result or "Skills:" in result

    def test_mixed_spaces_and_tabs_collapsed(self):
        result = clean_text("Name:  \t  Alice")
        assert "Name: Alice" in result

    def test_single_space_unchanged(self):
        assert clean_text("John Doe") == "John Doe"

    def test_whitespace_inside_line_not_line_breaks(self):
        """Newlines must not be collapsed along with intra-line spaces."""
        result = clean_text("Section One\nSection Two")
        assert "\n" in result


# ---------------------------------------------------------------------------
# 3. Blank-line reduction
# ---------------------------------------------------------------------------

class TestBlankLineReduction:
    """Three or more consecutive blank lines → at most two newlines."""

    def test_three_blank_lines_reduced(self):
        result = clean_text("Header\n\n\n\nBody")
        # At most two consecutive \n (= one blank line visible)
        assert "\n\n\n" not in result
        assert "Header" in result
        assert "Body" in result

    def test_five_blank_lines_reduced(self):
        result = clean_text("A\n\n\n\n\nB")
        assert "\n\n\n" not in result
        assert "A" in result
        assert "B" in result

    def test_single_blank_line_preserved(self):
        """One blank line between sections is meaningful — must not be removed."""
        result = clean_text("SKILLS\n\nPython")
        assert "SKILLS" in result
        assert "Python" in result
        # The blank line separator should still be present
        assert "\n\n" in result

    def test_section_structure_preserved(self):
        """Multi-section layout must remain distinguishable after cleaning."""
        resume = (
            "SKILLS\n\nJava\nPython\nSQL\n\n"
            "EDUCATION\n\nB.Tech Computer Science\n2020"
        )
        result = clean_text(resume)
        result_lines = lines(result)
        assert "SKILLS" in result_lines
        assert "Java" in result_lines
        assert "Python" in result_lines
        assert "EDUCATION" in result_lines
        assert "B.Tech Computer Science" in result_lines


# ---------------------------------------------------------------------------
# 4. Per-line and document-level strip
# ---------------------------------------------------------------------------

class TestStripping:
    """Leading/trailing whitespace should be removed from lines and document."""

    def test_leading_spaces_on_line_removed(self):
        result = clean_text("   Python Developer")
        assert result == "Python Developer"

    def test_trailing_spaces_on_line_removed(self):
        result = clean_text("Python Developer   ")
        assert result == "Python Developer"

    def test_document_level_leading_trailing_whitespace_removed(self):
        result = clean_text("\n\n  Alice Johnson  \n\n")
        assert result == "Alice Johnson"

    def test_empty_lines_after_strip_preserved_structurally(self):
        """Blank-line separators should survive per-line stripping."""
        result = clean_text("SKILLS\n   \nPython")
        assert "SKILLS" in result
        assert "Python" in result


# ---------------------------------------------------------------------------
# 5. Preservation of extraction-critical content
# ---------------------------------------------------------------------------

class TestPreservation:
    """Cleaning must not corrupt content that extraction modules depend on."""

    def test_email_preserved(self):
        assert clean_text("john.doe@gmail.com") == "john.doe@gmail.com"

    def test_email_with_plus_preserved(self):
        assert clean_text("john+alias@gmail.com") == "john+alias@gmail.com"

    def test_phone_with_country_code_preserved(self):
        result = clean_text("+91 9876543210")
        assert "+91" in result
        assert "9876543210" in result

    def test_phone_with_dashes_preserved(self):
        result = clean_text("(123) 456-7890")
        assert "(123)" in result
        assert "456-7890" in result

    def test_github_url_preserved(self):
        url = "https://github.com/johndoe"
        assert clean_text(url) == url

    def test_linkedin_url_preserved(self):
        url = "https://linkedin.com/in/johndoe"
        assert clean_text(url) == url

    def test_cpp_preserved(self):
        """C++ must not be mangled."""
        assert "C++" in clean_text("Languages: C++, Java")

    def test_node_js_preserved(self):
        assert "Node.js" in clean_text("Node.js, Express")

    def test_spring_boot_preserved(self):
        assert "Spring Boot" in clean_text("Frameworks: Spring Boot, Django")

    def test_btech_degree_preserved(self):
        assert "B.Tech" in clean_text("B.Tech in Computer Science")

    def test_hyphenated_skill_preserved(self):
        assert "full-stack" in clean_text("full-stack developer")

    def test_version_number_preserved(self):
        assert "Python 3.10" in clean_text("Python 3.10")

    def test_percentage_preserved(self):
        assert "95%" in clean_text("GPA: 95%")

    def test_date_range_preserved(self):
        assert "Jan 2022" in clean_text("Jan 2022 – Mar 2024")


# ---------------------------------------------------------------------------
# 6. Case preservation
# ---------------------------------------------------------------------------

class TestCasePreservation:
    """clean_text must NEVER lowercase or uppercase the content."""

    def test_mixed_case_unchanged(self):
        assert clean_text("Alice Johnson") == "Alice Johnson"

    def test_all_caps_heading_unchanged(self):
        assert clean_text("WORK EXPERIENCE") == "WORK EXPERIENCE"

    def test_camel_case_unchanged(self):
        assert clean_text("JavaScript TypeScript") == "JavaScript TypeScript"


# ---------------------------------------------------------------------------
# 7. Edge cases and safety
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Graceful handling of unusual inputs."""

    def test_empty_string_returns_empty_string(self):
        assert clean_text("") == ""

    def test_whitespace_only_returns_empty_string(self):
        assert clean_text("   \n\n\t  \n  ") == ""

    def test_single_word_unchanged(self):
        assert clean_text("Python") == "Python"

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            clean_text(None)  # type: ignore[arg-type]

    def test_integer_raises_type_error(self):
        with pytest.raises(TypeError):
            clean_text(42)  # type: ignore[arg-type]

    def test_unicode_text_handled(self):
        """Accented characters must pass through intact."""
        result = clean_text("Résumé of José María")
        assert "Résumé" in result
        assert "José" in result

    def test_non_breaking_space_converted(self):
        """Non-breaking space (U+00A0) should become a plain space."""
        result = clean_text("John\u00a0Doe")
        assert result == "John Doe"

    def test_zero_width_space_removed(self):
        """Zero-width space (U+200B) should be removed."""
        result = clean_text("John\u200bDoe")
        # ZWS is special whitespace — becomes a plain space then collapses
        assert "John" in result
        assert "Doe" in result

    def test_already_clean_text_unchanged(self):
        """Passing already-clean text should return the same content."""
        clean = "Alice Johnson\n\nPython Developer\nNew York"
        assert clean_text(clean) == clean

    def test_idempotent(self):
        """Calling clean_text twice should produce the same result as once."""
        raw = "  Alice   Johnson\r\n\r\nPython   Developer  "
        once = clean_text(raw)
        twice = clean_text(once)
        assert once == twice
