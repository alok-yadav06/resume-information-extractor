"""
Resume Information Extractor
============================
Deterministic, AI-free resume parsing pipeline.

Public surface:
    from extractor import ResumeExtractor, extract_resume, ParserError
"""

from .extractor import ResumeExtractor, extract_resume
from .parser import ParserError

__all__ = ["ResumeExtractor", "extract_resume", "ParserError"]
