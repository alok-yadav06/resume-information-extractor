"""
extractor.py
------------
Orchestrator for the full resume extraction pipeline.

Ties together all sub-modules in the correct deterministic order and assembles
the final structured JSON-serialisable dictionary.

Pipeline order:
    1. parser.extract_text()        → raw text from PDF / DOCX
    2. cleaner.clean_text()         → normalised text
    3. sections.detect_sections()   → canonical section map
    4. contact.extract_contact_info() → name, email, phone
    5. skills.extract_skills()      → deduplicated skills list
    6. education.extract_education()→ structured education records
    7. experience.extract_experience() → structured experience records
    8. Assemble and return structured dictionary

Output schema:
    {
        "name":        str | None,
        "email":       str | None,
        "phone":       str | None,
        "skills":      list[str],
        "education":   list[dict],
        "experience":  list[dict]
    }

Public API:
    extract_resume(source, filename=None) -> dict
    class ResumeExtractor:
        extract(source, filename=None) -> dict
"""

from __future__ import annotations

from typing import Any

from .cleaner import clean_text
from .contact import extract_contact_info
from .education import extract_education
from .experience import extract_experience
from .parser import FileSource, extract_text
from .sections import detect_sections
from .skills import extract_skills


def extract_resume(
    source: FileSource,
    filename: str | None = None,
) -> dict[str, Any]:
    """
    Extract structured candidate information from a PDF or DOCX resume.

    This is the main entry point for the Resume Information Extraction System.
    The extraction process is completely local, deterministic, and rule-based.
    No external LLMs or GenAI APIs are invoked.

    Parameters
    ----------
    source:
        The file to extract from.  Can be:
        - A filesystem path (``str`` or ``pathlib.Path``)
        - A binary buffer / stream (e.g. ``io.BytesIO``, Streamlit UploadedFile)
        - Raw ``bytes``
    filename:
        Optional filename (e.g. ``"resume.pdf"``).  Required when *source* is
        a raw ``bytes`` object or an anonymous stream without a ``.name`` attribute.
        Ignored / optional when *source* is a file path or named buffer.

    Returns
    -------
    dict[str, Any]
        A JSON-serialisable dictionary conforming to the standard schema:
        {
            "name": str | None,
            "email": str | None,
            "phone": str | None,
            "skills": list[str],
            "education": list[dict],
            "experience": list[dict]
        }

    Raises
    ------
    ParserError:
        If the file format is unsupported, corrupted, or cannot be parsed.
    TypeError:
        If *source* is not a supported type.
    """
    # 1. Parse document to raw text
    raw_text = extract_text(source, filename=filename)

    # 2. Normalise / clean text
    cleaned_text = clean_text(raw_text)

    # 3. Detect logical resume sections
    sections = detect_sections(cleaned_text)

    # 4. Extract contact information (name, email, phone) from full text
    contact = extract_contact_info(cleaned_text)

    # 5. Extract skills (preferring detected skills section)
    skills = extract_skills(cleaned_text, sections=sections)

    # 6. Extract education records (preferring detected education section)
    education = extract_education(cleaned_text, sections=sections)

    # 7. Extract work experience records (preferring detected experience section)
    experience = extract_experience(cleaned_text, sections=sections)

    # 8. Assemble final structured result
    return {
        "name": contact.get("name"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "skills": skills,
        "education": education,
        "experience": experience,
    }


class ResumeExtractor:
    """
    Object-oriented interface for the resume extraction pipeline.

    Provides instance and class-level methods for extracting information
    from resumes.

    Examples
    --------
    >>> extractor = ResumeExtractor()
    >>> data = extractor.extract("sample.pdf")

    Or as a class method:
    >>> data = ResumeExtractor.extract_resume("sample.docx")
    """

    def extract(
        self,
        source: FileSource,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Run the end-to-end extraction pipeline on *source*."""
        return extract_resume(source, filename=filename)

    @classmethod
    def extract_resume(
        cls,
        source: FileSource,
        filename: str | None = None,
    ) -> dict[str, Any]:
        """Convenience classmethod calling ``extract_resume``."""
        return extract_resume(source, filename=filename)
