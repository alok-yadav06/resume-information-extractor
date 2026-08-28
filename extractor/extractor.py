"""
extractor.py
------------
Orchestrator for the full resume extraction pipeline.

Ties together all sub-modules in the correct deterministic order and assembles
the final structured JSON-serialisable dictionary.

Pipeline order:
    1. parser.extract_text()        → raw text from PDF / DOCX
    2. parser.extract_hyperlinks()  → embedded link annotation URLs
    3. cleaner.clean_text()         → normalised text
    4. sections.detect_sections()   → canonical section map
    5. contact.extract_contact_info() → name, email, phone
    6. profiles.extract_profiles(extra_urls=...) → linkedin, github
    7. skills.extract_skills()      → deduplicated skills list
    8. education.extract_education()→ structured education records
    9. experience.extract_experience() → structured experience records
    10. Assemble and return structured dictionary

Output schema:
    {
        "name":        str | None,
        "email":       str | None,
        "phone":       str | None,
        "skills":      list[str],
        "education":   list[dict],
        "experience":  list[dict],
        "linkedin":    str | None,
        "github":      str | None
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
from .parser import FileSource, extract_hyperlinks, extract_text
from .profiles import extract_profiles
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
            "experience": list[dict],
            "linkedin": str | None,
            "github": str | None
        }

    Raises
    ------
    ParserError:
        If the file format is unsupported, corrupted, or cannot be parsed.
    TypeError:
        If *source* is not a supported type.
    """
    # Normalise source to raw bytes once so that stream-based sources (e.g.
    # Streamlit UploadedFile) are not consumed twice.
    from .parser import _to_bytes  # private helper — intentional internal use
    try:
        source_bytes: bytes = _to_bytes(source)
    except Exception:
        source_bytes = source  # type: ignore[assignment]  # let extract_text surface the error

    # 1. Parse document to raw text
    raw_text = extract_text(source_bytes, filename=filename)

    # 2. Extract embedded hyperlink annotation targets (for profile detection)
    #    PDF / DOCX files often store LinkedIn / GitHub URLs as clickable
    #    annotations while showing only a label (e.g. "LinkedIn") in the text.
    embedded_urls = extract_hyperlinks(source_bytes, filename=filename)

    # 3. Normalise / clean text
    cleaned_text = clean_text(raw_text)

    # 4. Detect logical resume sections
    sections = detect_sections(cleaned_text)

    # 5. Extract contact information (name, email, phone) from full text
    contact = extract_contact_info(cleaned_text)

    # 6. Extract social / developer profiles (LinkedIn, GitHub)
    #    Pass embedded_urls so annotation-only URLs are detected even when
    #    the visible text shows only a label such as "LinkedIn" or "GitHub".
    profiles = extract_profiles(cleaned_text, extra_urls=embedded_urls)

    # 7. Extract skills (preferring detected skills section)
    skills = extract_skills(cleaned_text, sections=sections)

    # 8. Extract education records (preferring detected education section)
    education = extract_education(cleaned_text, sections=sections)

    # 9. Extract work experience records (preferring detected experience section)
    experience = extract_experience(cleaned_text, sections=sections)

    # 9. Assemble final structured result
    return {
        "name": contact.get("name"),
        "email": contact.get("email"),
        "phone": contact.get("phone"),
        "skills": skills,
        "education": education,
        "experience": experience,
        "linkedin": profiles.get("linkedin"),
        "github": profiles.get("github"),
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
