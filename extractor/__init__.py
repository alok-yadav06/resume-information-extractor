"""
Resume Information Extractor
============================
Deterministic, AI-free resume parsing pipeline.

Public surface:
    from extractor import ResumeExtractor
"""

# ResumeExtractor is added incrementally; guard so the package can be imported
# even when extractor.py is still a stub.
try:
    from .extractor import ResumeExtractor
    __all__ = ["ResumeExtractor"]
except ImportError:
    __all__ = []
