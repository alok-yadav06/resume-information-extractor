"""
tests/test_profiles.py
----------------------
Unit tests for extractor/profiles.py.

Covers deterministic extraction of LinkedIn and GitHub profile URLs.
"""

from __future__ import annotations

import pytest

from extractor.profiles import extract_github, extract_linkedin, extract_profiles


# ===========================================================================
# 1. Output Schema & Basic Consistency
# ===========================================================================

class TestProfileSchema:

    def test_extract_profiles_schema(self):
        text = "LinkedIn: https://www.linkedin.com/in/johndoe\nGitHub: https://github.com/johndoe"
        res = extract_profiles(text)

        assert isinstance(res, dict)
        assert set(res.keys()) == {"linkedin", "github"}
        assert res["linkedin"] == "https://www.linkedin.com/in/johndoe"
        assert res["github"] == "https://github.com/johndoe"

    def test_empty_string_returns_none_fields(self):
        res = extract_profiles("")
        assert res == {"linkedin": None, "github": None}

    def test_whitespace_only_returns_none_fields(self):
        res = extract_profiles("   \n\t  ")
        assert res == {"linkedin": None, "github": None}

    def test_none_input_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_profiles(None)  # type: ignore[arg-type]

        with pytest.raises(TypeError):
            extract_linkedin(None)  # type: ignore[arg-type]

        with pytest.raises(TypeError):
            extract_github(None)  # type: ignore[arg-type]


# ===========================================================================
# 2. LinkedIn Extraction Tests
# ===========================================================================

class TestLinkedInExtraction:

    def test_standard_https_www_url(self):
        text = "Profile: https://www.linkedin.com/in/johndoe"
        assert extract_linkedin(text) == "https://www.linkedin.com/in/johndoe"

    def test_https_without_www(self):
        text = "Contact: https://linkedin.com/in/alice-smith-123"
        assert extract_linkedin(text) == "https://linkedin.com/in/alice-smith-123"

    def test_http_url_normalized_to_https(self):
        text = "LinkedIn: http://linkedin.com/in/bob_developer"
        assert extract_linkedin(text) == "https://linkedin.com/in/bob_developer"

    def test_bare_domain_without_scheme(self):
        text = "linkedin.com/in/johndoe"
        assert extract_linkedin(text) == "https://linkedin.com/in/johndoe"

    def test_www_domain_without_scheme(self):
        text = "www.linkedin.com/in/johndoe"
        assert extract_linkedin(text) == "https://www.linkedin.com/in/johndoe"

    def test_labeled_linkedin_url(self):
        text = "LinkedIn Profile: https://linkedin.com/in/john-doe"
        assert extract_linkedin(text) == "https://linkedin.com/in/john-doe"

    def test_labeled_with_dash(self):
        text = "LinkedIn - https://www.linkedin.com/in/johndoe"
        assert extract_linkedin(text) == "https://www.linkedin.com/in/johndoe"

    def test_trailing_punctuation_removed(self):
        text = "Connect with me at https://www.linkedin.com/in/johndoe."
        assert extract_linkedin(text) == "https://www.linkedin.com/in/johndoe"

        text2 = "(see https://www.linkedin.com/in/johndoe)"
        assert extract_linkedin(text2) == "https://www.linkedin.com/in/johndoe"

        text3 = "Profile: https://www.linkedin.com/in/johndoe;"
        assert extract_linkedin(text3) == "https://www.linkedin.com/in/johndoe"

    def test_trailing_slash_handled(self):
        text = "https://www.linkedin.com/in/johndoe/"
        assert extract_linkedin(text) == "https://www.linkedin.com/in/johndoe"

    def test_first_profile_used_when_duplicates_exist(self):
        text = "https://www.linkedin.com/in/first-user\nhttps://www.linkedin.com/in/second-user"
        assert extract_linkedin(text) == "https://www.linkedin.com/in/first-user"

    def test_generic_mention_false_positive(self):
        text = "Follow us on LinkedIn for updates."
        assert extract_linkedin(text) is None

    def test_unrelated_url_not_extracted_as_linkedin(self):
        text = "Visit https://example.com or https://google.com"
        assert extract_linkedin(text) is None


# ===========================================================================
# 3. GitHub Extraction Tests
# ===========================================================================

class TestGitHubExtraction:

    def test_standard_https_url(self):
        text = "GitHub: https://github.com/johndoe"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_https_www_url(self):
        text = "Code at https://www.github.com/alice-dev"
        assert extract_github(text) == "https://github.com/alice-dev"

    def test_http_url(self):
        text = "http://github.com/bobcoder"
        assert extract_github(text) == "https://github.com/bobcoder"

    def test_bare_domain_without_scheme(self):
        text = "github.com/johndoe"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_www_domain_without_scheme(self):
        text = "www.github.com/johndoe"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_labeled_github_url(self):
        text = "GitHub Profile: https://github.com/johndoe"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_labeled_with_dash(self):
        text = "GitHub - https://github.com/johndoe"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_trailing_punctuation_removed(self):
        text = "Check out my repositories at https://github.com/johndoe."
        assert extract_github(text) == "https://github.com/johndoe"

        text2 = "(GitHub: https://github.com/johndoe)"
        assert extract_github(text2) == "https://github.com/johndoe"

        text3 = "Portfolio: https://github.com/johndoe;"
        assert extract_github(text3) == "https://github.com/johndoe"

    def test_trailing_slash_handled(self):
        text = "https://github.com/johndoe/"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_reserved_slugs_ignored(self):
        text = "Visit https://github.com/about or https://github.com/pricing"
        assert extract_github(text) is None

    def test_repo_url_not_confused_with_profile_when_profile_exists(self):
        text = "GitHub: https://github.com/johndoe\nProject: https://github.com/company/awesome-app"
        assert extract_github(text) == "https://github.com/johndoe"

    def test_standalone_repo_url_not_extracted_as_profile(self):
        text = "Project repository at https://github.com/company/awesome-app"
        assert extract_github(text) is None

    def test_generic_mention_false_positive(self):
        text = "Experience using Git and GitHub for version control."
        assert extract_github(text) is None

    def test_unrelated_url_not_extracted_as_github(self):
        text = "Check out https://gitlab.com/johndoe or https://example.com"
        assert extract_github(text) is None


# ===========================================================================
# 4. Realistic Resume Header Tests
# ===========================================================================

class TestRealisticHeaderIntegration:

    def test_both_profiles_in_header(self):
        header = """John Doe
john.doe@example.com | +91 9876543210
LinkedIn: https://www.linkedin.com/in/johndoe | GitHub: https://github.com/johndoe
Mumbai, India
"""
        profiles = extract_profiles(header)
        assert profiles["linkedin"] == "https://www.linkedin.com/in/johndoe"
        assert profiles["github"] == "https://github.com/johndoe"

    def test_only_linkedin_present(self):
        header = """Alice Smith
alice@example.com
linkedin.com/in/alicesmith
"""
        profiles = extract_profiles(header)
        assert profiles["linkedin"] == "https://linkedin.com/in/alicesmith"
        assert profiles["github"] is None

    def test_only_github_present(self):
        header = """Bob Brown
bob@example.com
github.com/bobbrown
"""
        profiles = extract_profiles(header)
        assert profiles["linkedin"] is None
        assert profiles["github"] == "https://github.com/bobbrown"

    def test_neither_profile_present(self):
        header = """Charlie Green
charlie@example.com
+1 (555) 019-2834
"""
        profiles = extract_profiles(header)
        assert profiles == {"linkedin": None, "github": None}
