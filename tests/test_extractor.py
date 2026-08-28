"""
tests/test_extractor.py
-----------------------
Integration tests for the end-to-end resume extraction pipeline.

Tests verify the complete pipeline:
    parser → cleaner → sections → contact, profiles, skills, education, experience → assembled output
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import pytest
import pymupdf as fitz
from docx import Document

from extractor import ResumeExtractor, extract_resume, ParserError


# ---------------------------------------------------------------------------
# Test document generators (in-memory, no external network dependencies)
# ---------------------------------------------------------------------------

def _create_pdf_bytes(text: str) -> bytes:
    """Create a minimal PDF document in memory and return its bytes."""
    doc = fitz.open()
    page = doc.new_page()
    # Insert text lines onto page
    page.insert_text((50, 72), text, fontsize=11)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def _create_docx_bytes(text: str) -> bytes:
    """Create a minimal DOCX document in memory and return its bytes."""
    doc = Document()
    for line in text.split("\n"):
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Sample resume texts
# ---------------------------------------------------------------------------

COMPLETE_RESUME_TEXT = """John Doe
john.doe@example.com
+91 9876543210
LinkedIn: https://www.linkedin.com/in/johndoe
GitHub: https://github.com/johndoe

SKILLS
Python, Java, Docker, SQL, Git

EDUCATION
B.Tech in Computer Engineering
ABC University
2020 - 2024
CGPA: 8.9

EXPERIENCE
Software Engineer Intern
XYZ Technologies
June 2024 - August 2024
Mumbai
- Developed REST APIs using Python and FastAPI
- Optimized SQL database queries
"""

PARTIAL_RESUME_TEXT = """Jane Smith
jane.smith@example.com
(555) 123-4567

Summary
Motivated professional looking for exciting opportunities.
"""

MULTI_SECTION_RESUME_TEXT = """Alex Johnson
alex.j@example.com
+1 415 555 2671
linkedin.com/in/alex-j
github.com/alexj

SKILLS
React, Node.js, TypeScript, PostgreSQL

EXPERIENCE
Frontend Developer
Tech Corp
2023 - Present
- Built responsive user interfaces

PROJECTS
E-Commerce Platform
2024
- Implemented shopping cart using React and Stripe

EDUCATION
Bachelor of Science in Computer Science
State University
2019 - 2023
"""


# ===========================================================================
# 1. Output Schema and JSON Serializability
# ===========================================================================

class TestOutputSchema:

    def test_schema_keys_always_present(self):
        pdf_bytes = _create_pdf_bytes(COMPLETE_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="resume.pdf")

        expected_keys = {
            "name", "email", "phone", "skills", "education", "experience",
            "linkedin", "github"
        }
        assert set(result.keys()) == expected_keys

    def test_json_serializability(self):
        pdf_bytes = _create_pdf_bytes(COMPLETE_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="resume.pdf")

        # Must serialize cleanly to JSON string
        json_str = json.dumps(result, indent=2)
        assert isinstance(json_str, str)

        # Roundtrip check
        deserialized = json.loads(json_str)
        assert deserialized == result

    def test_field_types(self):
        pdf_bytes = _create_pdf_bytes(COMPLETE_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="resume.pdf")

        assert isinstance(result["name"], (str, type(None)))
        assert isinstance(result["email"], (str, type(None)))
        assert isinstance(result["phone"], (str, type(None)))
        assert isinstance(result["skills"], list)
        assert isinstance(result["education"], list)
        assert isinstance(result["experience"], list)
        assert isinstance(result["linkedin"], (str, type(None)))
        assert isinstance(result["github"], (str, type(None)))


# ===========================================================================
# 2. Complete End-to-End Extraction
# ===========================================================================

class TestCompleteExtraction:

    def test_complete_pdf_resume(self):
        pdf_bytes = _create_pdf_bytes(COMPLETE_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="john_doe.pdf")

        # Contact info
        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@example.com"
        assert result["phone"] is not None
        assert "9876543210" in result["phone"]

        # Profiles
        assert result["linkedin"] == "https://www.linkedin.com/in/johndoe"
        assert result["github"] == "https://github.com/johndoe"

        # Skills
        assert "Python" in result["skills"]
        assert "Docker" in result["skills"]

        # Education
        assert len(result["education"]) >= 1
        edu = result["education"][0]
        assert "B.Tech" in (edu.get("degree") or "")
        assert "ABC University" in (edu.get("institution") or "")

        # Experience
        assert len(result["experience"]) >= 1
        exp = result["experience"][0]
        assert "Intern" in (exp.get("job_title") or "")
        assert "XYZ" in (exp.get("company") or "")
        assert len(exp.get("description", [])) >= 1

    def test_complete_docx_resume(self):
        docx_bytes = _create_docx_bytes(COMPLETE_RESUME_TEXT)
        result = extract_resume(docx_bytes, filename="john_doe.docx")

        # Contact info
        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@example.com"
        assert result["phone"] is not None

        # Profiles
        assert result["linkedin"] == "https://www.linkedin.com/in/johndoe"
        assert result["github"] == "https://github.com/johndoe"

        # Skills
        assert "Python" in result["skills"]
        assert "Java" in result["skills"]

        # Education
        assert len(result["education"]) >= 1

        # Experience
        assert len(result["experience"]) >= 1


# ===========================================================================
# 3. Missing Fields and Partial Resumes
# ===========================================================================

class TestPartialResumes:

    def test_resume_with_only_contact_info(self):
        pdf_bytes = _create_pdf_bytes(PARTIAL_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="partial.pdf")

        assert result["name"] == "Jane Smith"
        assert result["email"] == "jane.smith@example.com"
        assert result["phone"] is not None
        assert result["skills"] == []
        assert result["education"] == []
        assert result["experience"] == []
        assert result["linkedin"] is None
        assert result["github"] is None

    def test_document_with_no_recognizable_fields(self):
        unrecognizable_text = "This is a general document with arbitrary notes and no resume content."
        pdf_bytes = _create_pdf_bytes(unrecognizable_text)
        result = extract_resume(pdf_bytes, filename="general.pdf")

        assert result == {
            "name": None,
            "email": None,
            "phone": None,
            "skills": [],
            "education": [],
            "experience": [],
            "linkedin": None,
            "github": None,
        }

    def test_empty_unreadable_pdf_raises_parser_error(self):
        pdf_bytes = _create_pdf_bytes("")
        with pytest.raises(ParserError):
            extract_resume(pdf_bytes, filename="empty.pdf")

    def test_empty_unreadable_docx_raises_parser_error(self):
        docx_bytes = _create_docx_bytes("")
        with pytest.raises(ParserError):
            extract_resume(docx_bytes, filename="empty.docx")


# ===========================================================================
# 4. Section-Aware Isolation and Routing
# ===========================================================================

class TestSectionAwareRouting:

    def test_projects_not_leaked_into_experience(self):
        pdf_bytes = _create_pdf_bytes(MULTI_SECTION_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="multi.pdf")

        # Experience should contain Tech Corp, not E-Commerce Platform project
        exp_companies = [e.get("company") or "" for e in result["experience"]]
        exp_titles = [e.get("job_title") or "" for e in result["experience"]]

        assert any("Tech Corp" in c for c in exp_companies)
        assert not any("E-Commerce" in t for t in exp_titles)

    def test_education_not_leaked_into_experience(self):
        pdf_bytes = _create_pdf_bytes(MULTI_SECTION_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="multi.pdf")

        exp_companies = [e.get("company") or "" for e in result["experience"]]
        assert not any("State University" in c for c in exp_companies)

    def test_skills_extracted_from_skills_section(self):
        pdf_bytes = _create_pdf_bytes(MULTI_SECTION_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="multi.pdf")

        assert "React" in result["skills"]
        assert "Node.js" in result["skills"]
        assert "TypeScript" in result["skills"]
        assert "PostgreSQL" in result["skills"]

    def test_profiles_extracted_from_multi_section(self):
        pdf_bytes = _create_pdf_bytes(MULTI_SECTION_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="multi.pdf")

        assert result["linkedin"] == "https://linkedin.com/in/alex-j"
        assert result["github"] == "https://github.com/alexj"


# ===========================================================================
# 5. Class Interface (ResumeExtractor)
# ===========================================================================

class TestResumeExtractorClass:

    def test_instance_extract_method(self):
        extractor = ResumeExtractor()
        pdf_bytes = _create_pdf_bytes(COMPLETE_RESUME_TEXT)
        result = extractor.extract(pdf_bytes, filename="resume.pdf")

        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@example.com"
        assert result["linkedin"] == "https://www.linkedin.com/in/johndoe"
        assert result["github"] == "https://github.com/johndoe"

    def test_classmethod_extract_resume(self):
        pdf_bytes = _create_pdf_bytes(COMPLETE_RESUME_TEXT)
        result = ResumeExtractor.extract_resume(pdf_bytes, filename="resume.pdf")

        assert result["name"] == "John Doe"
        assert result["email"] == "john.doe@example.com"
        assert result["linkedin"] == "https://www.linkedin.com/in/johndoe"
        assert result["github"] == "https://github.com/johndoe"


# ===========================================================================
# 6. File Handling and Error Propagation
# ===========================================================================

class TestErrorHandlingAndFileFormats:

    def test_unsupported_file_extension_raises_parser_error(self):
        with pytest.raises(ParserError):
            extract_resume(b"dummy content", filename="resume.txt")

    def test_unsupported_source_type_raises_parser_error(self):
        with pytest.raises(ParserError):
            extract_resume(12345)  # type: ignore[arg-type]

    def test_case_insensitive_extension(self):
        pdf_bytes = _create_pdf_bytes(PARTIAL_RESUME_TEXT)
        result = extract_resume(pdf_bytes, filename="RESUME.PDF")
        assert result["name"] == "Jane Smith"

        docx_bytes = _create_docx_bytes(PARTIAL_RESUME_TEXT)
        result_docx = extract_resume(docx_bytes, filename="CANDIDATE.DoCx")
        assert result_docx["name"] == "Jane Smith"

    def test_corrupted_pdf_raises_parser_error(self):
        with pytest.raises(ParserError):
            extract_resume(b"not a valid pdf content", filename="broken.pdf")

    def test_corrupted_docx_raises_parser_error(self):
        with pytest.raises(ParserError):
            extract_resume(b"not a valid docx content", filename="broken.docx")
