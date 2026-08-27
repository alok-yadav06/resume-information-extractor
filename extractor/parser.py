"""
parser.py
---------
Responsible for extracting raw plain text from uploaded resume files.

Supported formats:
    - PDF  → via PyMuPDF (fitz)
    - DOCX → via python-docx

Public API:
    parse_resume(file_path: str | Path) -> str
        Returns the full raw text of the resume as a single string.
"""

# TODO: Implement PDF and DOCX parsing logic.
