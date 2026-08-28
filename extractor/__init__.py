"""
Resume Information Extractor
============================
Deterministic, AI-free resume parsing pipeline.

Public surface:
    from extractor import ResumeExtractor, extract_resume, extract_profiles, ParserError
"""

from .extractor import ResumeExtractor, extract_resume
from .parser import ParserError
from .profiles import extract_profiles

__all__ = ["ResumeExtractor", "extract_resume", "extract_profiles", "ParserError"]
