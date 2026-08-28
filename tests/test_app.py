"""
tests/test_app.py
-----------------
Lightweight tests for the Streamlit UI helper utilities in app.py.
"""

from __future__ import annotations

from app import format_file_size


class TestAppHelpers:

    def test_format_file_size_bytes(self):
        assert format_file_size(500) == "500 B"

    def test_format_file_size_kilobytes(self):
        assert format_file_size(2048) == "2.0 KB"

    def test_format_file_size_megabytes(self):
        assert format_file_size(1024 * 1024 * 3) == "3.00 MB"
