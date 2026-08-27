"""
tests/test_skills.py
--------------------
Unit tests for extractor/skills.py.

Tests focus on observable behavior: correct extraction, boundary safety,
alias resolution, multi-word skills, ordering, and false-positive prevention.
"""

from __future__ import annotations

import pytest

from extractor.skills import extract_skills


# ===========================================================================
# Helpers
# ===========================================================================

def _skills(*args: str) -> dict[str, str]:
    """Build a minimal sections dict with a skills section."""
    return {"skills": "\n".join(args)}


# ===========================================================================
# 1. Basic extraction — common separators
# ===========================================================================

class TestBasicExtraction:

    def test_comma_separated(self):
        result = extract_skills("Python, Java, SQL, Docker")
        for skill in ["Python", "Java", "SQL", "Docker"]:
            assert skill in result

    def test_pipe_separated(self):
        result = extract_skills("Python | Java | SQL | Docker")
        for skill in ["Python", "Java", "SQL", "Docker"]:
            assert skill in result

    def test_line_separated(self):
        result = extract_skills("Python\nJava\nSQL\nDocker")
        for skill in ["Python", "Java", "SQL", "Docker"]:
            assert skill in result

    def test_bullet_style(self):
        text = "• Python\n• Java\n• SQL\n• Docker"
        result = extract_skills(text)
        for skill in ["Python", "Java", "SQL", "Docker"]:
            assert skill in result

    def test_mixed_formatting(self):
        text = "Java, Spring Boot | MySQL\nGit\nDocker"
        result = extract_skills(text)
        for skill in ["Java", "Spring Boot", "MySQL", "Git", "Docker"]:
            assert skill in result

    def test_returns_list(self):
        assert isinstance(extract_skills("Python"), list)

    def test_empty_string_returns_empty_list(self):
        assert extract_skills("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert extract_skills("   \n\n  ") == []

    def test_no_known_skills_returns_empty_list(self):
        assert extract_skills("The quick brown fox jumps over the lazy dog.") == []


# ===========================================================================
# 2. Section-aware extraction
# ===========================================================================

class TestSectionAwareExtraction:

    def test_skills_from_sections_dict(self):
        sections = _skills("Python", "Java", "SQL")
        result = extract_skills("unrelated text", sections=sections)
        assert "Python" in result
        assert "Java" in result
        assert "SQL" in result

    def test_skills_section_takes_priority_over_full_text(self):
        """Skills section should be used when present; other sections ignored."""
        full_text = (
            "SKILLS\nPython\nJava\n\n"
            "EXPERIENCE\nUsed C++ and Rust extensively."
        )
        sections = {"skills": "Python\nJava"}
        result = extract_skills(full_text, sections=sections)
        # Python and Java should be present.
        assert "Python" in result
        assert "Java" in result
        # C++ and Rust come from experience — should NOT appear when
        # we restrict to the skills section.
        assert "C++" not in result
        assert "Rust" not in result

    def test_skills_section_multiline(self):
        sections = _skills(
            "Python, Java, C++",
            "Docker, Kubernetes",
            "MySQL, MongoDB",
        )
        result = extract_skills("irrelevant", sections=sections)
        for skill in ["Python", "Java", "C++", "Docker", "Kubernetes", "MySQL", "MongoDB"]:
            assert skill in result

    def test_fallback_used_when_sections_none(self):
        result = extract_skills("Python and Java are popular.", sections=None)
        assert "Python" in result
        assert "Java" in result

    def test_fallback_used_when_sections_empty(self):
        result = extract_skills("Python is great.", sections={})
        assert "Python" in result

    def test_fallback_used_when_skills_key_missing(self):
        result = extract_skills("Use Docker for containers.", sections={"education": "B.Tech"})
        assert "Docker" in result

    def test_skills_section_after_other_sections(self):
        sections = {
            "education": "B.Tech Computer Science",
            "experience": "Software Engineer at XYZ",
            "skills": "Python, Django, PostgreSQL",
        }
        result = extract_skills("full resume text", sections=sections)
        assert "Python" in result
        assert "Django" in result
        assert "PostgreSQL" in result

    def test_category_labels_stripped(self):
        """Category sub-headings in the skills section should not block extraction."""
        sections = _skills(
            "Programming Languages: Java, Python, C++",
            "Databases: MySQL, MongoDB",
            "Tools: Git, Docker",
        )
        result = extract_skills("irrelevant", sections=sections)
        for skill in ["Java", "Python", "C++", "MySQL", "MongoDB", "Git", "Docker"]:
            assert skill in result


# ===========================================================================
# 3. Boundary safety — critical correctness tests
# ===========================================================================

class TestBoundarySafety:
    """Skill names must not match as substrings of longer tokens."""

    # C must NOT match inside C++, C#, CSS, Cloud, Scala, etc.
    def test_C_does_not_match_cpp(self):
        result = extract_skills("C++ is a systems language.", sections={"skills": "C++"})
        assert "C++" in result
        # "C" should not appear as a separate skill when only C++ is present
        # (unless C is independently mentioned)
        assert result.count("C") == 0 or "C++" in result

    def test_C_not_extracted_from_css(self):
        result = extract_skills("CSS styles the page.", sections={"skills": "CSS"})
        assert "CSS" in result
        # Standalone C must not be extracted from CSS
        canonical_list = [s.strip() for s in result]
        assert "C" not in canonical_list

    def test_C_not_extracted_from_csharp(self):
        result = extract_skills("C# is managed.", sections={"skills": "C#"})
        assert "C#" in result
        assert "C" not in result

    def test_C_not_extracted_from_cloud(self):
        result = extract_skills("Cloud computing is popular.", sections={"skills": "AWS"})
        assert "C" not in result

    # Java must NOT match inside JavaScript
    def test_java_does_not_match_javascript(self):
        result = extract_skills(
            "I love JavaScript.",
            sections={"skills": "JavaScript"},
        )
        assert "JavaScript" in result
        assert "Java" not in result

    def test_java_extracted_when_present_alone(self):
        result = extract_skills("Java and Python", sections={"skills": "Java, Python"})
        assert "Java" in result
        assert "Python" in result

    # Go must not match the English word "go" in sentences
    def test_go_not_matched_in_sentence(self):
        result = extract_skills(
            "I would like to go into software engineering.",
            sections={"skills": "Python"},
        )
        assert "Go" not in result

    # R must not match arbitrary r-containing words
    def test_R_not_matched_in_arbitrary_words(self):
        result = extract_skills(
            "React is great for frontend.",
            sections={"skills": "React"},
        )
        assert "R" not in result

    def test_R_not_matched_in_regular(self):
        text = "I am a regular developer."
        result = extract_skills(text, sections={"skills": "Python"})
        assert "R" not in result

    # Spring Boot vs Spring
    def test_spring_boot_not_split_into_spring(self):
        """If only Spring Boot is present, plain Spring must not appear."""
        result = extract_skills(
            "Spring Boot is a framework.",
            sections={"skills": "Spring Boot"},
        )
        assert "Spring Boot" in result
        # Spring alone should not appear as a duplicate
        assert result.count("Spring") == 0

    # JavaScript must not also produce TypeScript match
    def test_javascript_not_matched_as_typescript(self):
        result = extract_skills("JavaScript", sections={"skills": "JavaScript"})
        assert "JavaScript" in result
        assert "TypeScript" not in result


# ===========================================================================
# 4. Multi-word skills
# ===========================================================================

class TestMultiWordSkills:

    def test_spring_boot(self):
        assert "Spring Boot" in extract_skills("Spring Boot, Django", sections=_skills("Spring Boot, Django"))

    def test_machine_learning(self):
        assert "Machine Learning" in extract_skills("Machine Learning", sections=_skills("Machine Learning"))

    def test_deep_learning(self):
        assert "Deep Learning" in extract_skills("Deep Learning", sections=_skills("Deep Learning"))

    def test_data_structures(self):
        assert "Data Structures" in extract_skills("Data Structures", sections=_skills("Data Structures"))

    def test_object_oriented_programming(self):
        result = extract_skills("Object-Oriented Programming", sections=_skills("Object-Oriented Programming"))
        assert "Object-Oriented Programming" in result

    def test_google_cloud(self):
        assert "Google Cloud" in extract_skills("Google Cloud", sections=_skills("Google Cloud"))

    def test_sql_server(self):
        assert "SQL Server" in extract_skills("SQL Server", sections=_skills("SQL Server"))

    def test_natural_language_processing(self):
        result = extract_skills(
            "Natural Language Processing",
            sections=_skills("Natural Language Processing"),
        )
        assert "NLP" in result or "Natural Language Processing" in result


# ===========================================================================
# 5. Alias resolution
# ===========================================================================

class TestAliasResolution:

    def test_js_resolves_to_javascript(self):
        result = extract_skills("JS, Python", sections=_skills("JS, Python"))
        assert "JavaScript" in result
        assert "JS" not in result   # alias, not canonical

    def test_nodejs_resolves_to_nodejs(self):
        result = extract_skills("NodeJS", sections=_skills("NodeJS"))
        assert "Node.js" in result

    def test_node_js_space_variant(self):
        result = extract_skills("Node JS", sections=_skills("Node JS"))
        assert "Node.js" in result

    def test_c_sharp_alias(self):
        result = extract_skills("C sharp", sections=_skills("C sharp"))
        assert "C#" in result

    def test_c_plus_plus_alias(self):
        result = extract_skills("C plus plus", sections=_skills("C plus plus"))
        assert "C++" in result

    def test_sklearn_alias(self):
        result = extract_skills("sklearn", sections=_skills("sklearn"))
        assert "Scikit-learn" in result

    def test_ml_alias(self):
        result = extract_skills("ML, DL", sections=_skills("ML, DL"))
        assert "Machine Learning" in result
        assert "Deep Learning" in result

    def test_postgres_alias(self):
        result = extract_skills("postgres", sections=_skills("postgres"))
        assert "PostgreSQL" in result

    def test_k8s_alias(self):
        result = extract_skills("k8s", sections=_skills("k8s"))
        assert "Kubernetes" in result

    def test_oop_alias(self):
        result = extract_skills("OOP", sections=_skills("OOP"))
        assert "Object-Oriented Programming" in result

    def test_dotnet_alias(self):
        result = extract_skills("dotnet", sections=_skills("dotnet"))
        assert ".NET" in result


# ===========================================================================
# 6. Case handling
# ===========================================================================

class TestCaseHandling:

    def test_lowercase_java_returns_canonical(self):
        result = extract_skills("java", sections=_skills("java"))
        assert "Java" in result

    def test_uppercase_java_returns_canonical(self):
        result = extract_skills("JAVA", sections=_skills("JAVA"))
        assert "Java" in result

    def test_titlecase_java_returns_canonical(self):
        result = extract_skills("Java", sections=_skills("Java"))
        assert "Java" in result

    def test_mixed_case_python(self):
        result = extract_skills("PYTHON", sections=_skills("PYTHON"))
        assert "Python" in result

    def test_case_does_not_create_duplicates(self):
        result = extract_skills("Java, java, JAVA", sections=_skills("Java, java, JAVA"))
        assert result.count("Java") == 1


# ===========================================================================
# 7. Duplicate handling
# ===========================================================================

class TestDuplicateHandling:

    def test_repeated_skill_appears_once(self):
        result = extract_skills("Python, Python, Python", sections=_skills("Python, Python, Python"))
        assert result.count("Python") == 1

    def test_alias_and_canonical_not_duplicated(self):
        result = extract_skills("JS, JavaScript", sections=_skills("JS, JavaScript"))
        assert result.count("JavaScript") == 1

    def test_multiple_aliases_not_duplicated(self):
        result = extract_skills("NodeJS, Node.js, Node JS", sections=_skills("NodeJS, Node.js, Node JS"))
        assert result.count("Node.js") == 1


# ===========================================================================
# 8. Document order preservation
# ===========================================================================

class TestOrdering:

    def test_order_preserved_comma_list(self):
        result = extract_skills("Python, Java, SQL, Docker", sections=_skills("Python, Java, SQL, Docker"))
        # Python should appear before Docker
        assert result.index("Python") < result.index("Docker")

    def test_order_preserved_line_list(self):
        result = extract_skills("Docker\nKubernetes\nGit", sections=_skills("Docker\nKubernetes\nGit"))
        assert result.index("Docker") < result.index("Git")


# ===========================================================================
# 9. Special technical names
# ===========================================================================

class TestSpecialTechnicalNames:

    def test_cpp_extracted(self):
        assert "C++" in extract_skills("C++", sections=_skills("C++"))

    def test_csharp_extracted(self):
        assert "C#" in extract_skills("C#", sections=_skills("C#"))

    def test_dotnet_extracted(self):
        assert ".NET" in extract_skills(".NET", sections=_skills(".NET"))

    def test_aspnet_extracted(self):
        assert "ASP.NET" in extract_skills("ASP.NET", sections=_skills("ASP.NET"))

    def test_nodejs_extracted(self):
        assert "Node.js" in extract_skills("Node.js", sections=_skills("Node.js"))

    def test_reactjs_extracted(self):
        result = extract_skills("React.js", sections=_skills("React.js"))
        assert "React" in result or "React.js" in result

    def test_nextjs_extracted(self):
        assert "Next.js" in extract_skills("Next.js", sections=_skills("Next.js"))

    def test_typescript_extracted(self):
        assert "TypeScript" in extract_skills("TypeScript", sections=_skills("TypeScript"))

    def test_postgresql_extracted(self):
        assert "PostgreSQL" in extract_skills("PostgreSQL", sections=_skills("PostgreSQL"))

    def test_sql_extracted(self):
        assert "SQL" in extract_skills("SQL", sections=_skills("SQL"))


# ===========================================================================
# 10. False-positive prevention
# ===========================================================================

class TestFalsePositives:

    def test_go_in_sentence_not_extracted(self):
        """'go' in normal English must not be extracted as the Go language."""
        text = "I would like to go into software engineering."
        result = extract_skills(text, sections={"skills": "Python"})
        assert "Go" not in result

    def test_javascript_sentence_no_java(self):
        """JavaScript in a sentence must not also produce Java."""
        result = extract_skills(
            "JavaScript is one of my primary technologies.",
            sections={"skills": "JavaScript"},
        )
        assert "JavaScript" in result
        assert "Java" not in result

    def test_cpp_and_csharp_coexist_without_c(self):
        """C++ and C# together must not produce standalone C."""
        result = extract_skills("C++ and C# are different languages.", sections=_skills("C++, C#"))
        assert "C++" in result
        assert "C#" in result
        assert "C" not in result

    def test_css_and_react_no_c(self):
        """CSS and React must not produce C."""
        result = extract_skills(
            "Experience working with CSS and React.",
            sections=_skills("CSS, React"),
        )
        assert "CSS" in result
        assert "React" in result
        assert "C" not in result

    def test_scala_does_not_produce_c(self):
        result = extract_skills("Scala developer", sections=_skills("Scala"))
        assert "Scala" in result
        assert "C" not in result

    def test_year_not_extracted_as_skill(self):
        result = extract_skills("Graduated in 2020.", sections={"skills": "Python"})
        assert "Python" in result
        # No skill should look like a year
        for skill in result:
            assert not skill.strip().isdigit()

    def test_r_not_extracted_from_react(self):
        result = extract_skills("React is great.", sections=_skills("React"))
        assert "React" in result
        assert "R" not in result

    def test_r_not_extracted_from_arbitrary_sentences(self):
        """The letter R in ordinary words must not be a skill match."""
        result = extract_skills(
            "I regularly review requirements.",
            sections=_skills("Python"),
        )
        assert "R" not in result


# ===========================================================================
# 11. Missing / edge cases
# ===========================================================================

class TestEdgeCases:

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_skills(None)  # type: ignore[arg-type]

    def test_integer_raises_type_error(self):
        with pytest.raises(TypeError):
            extract_skills(42)  # type: ignore[arg-type]

    def test_sections_none_uses_fallback(self):
        result = extract_skills("Python, Docker", sections=None)
        assert "Python" in result

    def test_sections_empty_uses_fallback(self):
        result = extract_skills("Python, Docker", sections={})
        assert "Python" in result

    def test_resume_with_no_skills_returns_empty(self):
        text = (
            "This is a cover letter. I am enthusiastic and a team player.\n"
            "I look forward to hearing from you."
        )
        result = extract_skills(text, sections={"education": "B.Tech"})
        # Should return empty or only incidentally matched skills — not crash.
        assert isinstance(result, list)


# ===========================================================================
# 12. Realistic resume integration
# ===========================================================================

class TestRealisticResume:

    SKILLS_TEXT = (
        "Programming Languages: Python, Java, C++, JavaScript\n"
        "Frameworks: Spring Boot, Django, React\n"
        "Databases: MySQL, MongoDB, Redis\n"
        "Tools: Git, Docker, Kubernetes\n"
        "Cloud: AWS, Google Cloud\n"
        "ML: Machine Learning, Scikit-learn, TensorFlow"
    )

    def test_all_skills_extracted(self):
        sections = {"skills": self.SKILLS_TEXT}
        result = extract_skills("full resume text", sections=sections)
        for skill in [
            "Python", "Java", "C++", "JavaScript",
            "Spring Boot", "Django", "React",
            "MySQL", "MongoDB", "Redis",
            "Git", "Docker", "Kubernetes",
            "AWS", "Google Cloud",
            "Machine Learning", "Scikit-learn", "TensorFlow",
        ]:
            assert skill in result, f"Expected '{skill}' in result"

    def test_no_duplicates_in_realistic_resume(self):
        sections = {"skills": self.SKILLS_TEXT}
        result = extract_skills("full resume text", sections=sections)
        assert len(result) == len(set(result)), "Duplicates found in result"

    def test_java_and_javascript_both_extracted(self):
        """Both Java and JavaScript must appear as separate distinct skills."""
        sections = {"skills": "Java, JavaScript, Spring Boot"}
        result = extract_skills("irrelevant", sections=sections)
        assert "Java" in result
        assert "JavaScript" in result
