# Technical Approach — Resume Information Extraction System

> This document describes the architecture and algorithmic decisions behind the
> deterministic, AI-free resume parsing pipeline.

---

## 1. Problem Statement

Recruiting pipelines receive resumes in a wide variety of formats (PDF, DOCX) with no
fixed schema. The goal is to reliably extract structured candidate data — name, contact
details, skills, education, and work experience — using only deterministic, locally
executable techniques, without relying on any external LLM or AI API.

---

## 2. Architecture

The system is a sequential, modular pipeline:

```
[Upload: PDF / DOCX]
        │
        ▼
  ┌──────────────┐
  │  parser.py   │  ← raw text extraction
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  cleaner.py  │  ← text normalisation
  └──────┬───────┘
         │
         ▼
  ┌──────────────┐
  │  sections.py │  ← section boundary detection
  └──────┬───────┘
         │
        ┌┴────────────────────────────┐
        │                             │
        ▼                             ▼
  ┌──────────────┐           ┌──────────────────┐
  │  contact.py  │           │  skills.py       │
  │  (name,      │           │  education.py    │
  │   email,     │           │  experience.py   │
  │   phone,     │           └────────┬─────────┘
  │   LinkedIn,  │                    │
  │   GitHub)    │                    │
  └──────┬───────┘                    │
         └────────────┬───────────────┘
                      ▼
              ┌───────────────┐
              │  extractor.py │  ← orchestrator / JSON assembly
              └───────────────┘
                      │
                      ▼
              ┌───────────────┐
              │   app.py      │  ← Streamlit UI
              └───────────────┘
```

Each module has a single responsibility and can be tested independently.

---

## 3. PDF / DOCX Parsing

### PDF — PyMuPDF (`fitz`)

* Open the PDF using `fitz.open()`.
* Iterate over all pages and extract text blocks using `page.get_text("text")`.
* Concatenate page text with newline separators.
* Preserves reading order as rendered by the PDF engine.

### DOCX — python-docx

* Load the document with `Document(path)`.
* Iterate over `document.paragraphs` and collect `.text` from each paragraph.
* Tables inside DOCX files will also be traversed row-by-row.
* Concatenate with newline separators.

**Output**: a single plain-text string representing the full resume.

---

## 4. Text Cleaning

Performed in `cleaner.py`:

* Replace non-breaking spaces (`\u00a0`) and other Unicode whitespace with standard spaces.
* Collapse multiple consecutive blank lines into a single blank line.
* Strip leading/trailing whitespace from every line.
* Remove null bytes and other control characters.
* Normalise Unicode to NFC form to unify accented characters.

**Output**: clean, normalised multi-line string ready for pattern matching.

---

## 5. Section Detection

Performed in `sections.py`:

* Define a dictionary of section keywords:
  ```
  SECTION_KEYWORDS = {
      "education":   ["education", "academic", "qualification"],
      "experience":  ["experience", "employment", "work history", "career"],
      "skills":      ["skills", "technical skills", "core competencies"],
      "projects":    ["projects", "personal projects"],
      "contact":     ["contact", "personal details"],
      ...
  }
  ```
* Scan each line; if it matches a keyword (case-insensitive, stripped), mark it as a
  section heading.
* Build a dictionary mapping section names → text blocks between headings.

**Output**: `dict[str, str]` — section name to raw section text.

---

## 6. Regex Extraction

Performed in `contact.py`:

| Field | Pattern Strategy |
|---|---|
| **Email** | Standard RFC-5321 local-part + domain regex |
| **Phone** | Flexible pattern covering `+91`, country codes, dashes, spaces, dots, parentheses |
| **LinkedIn** | URL pattern matching `linkedin.com/in/<handle>` |
| **GitHub** | URL pattern matching `github.com/<handle>` |

All patterns use `re.IGNORECASE` and `re.MULTILINE`.

---

## 7. Skills Extraction

Performed in `skills.py`:

* Load a curated list of ~200+ skills from `data/skills.json`.
* Lowercase both the resume text and each skill.
* Use whole-word matching (`\b<skill>\b`) to avoid false positives
  (e.g. "R" skill not matching "React").
* Return a deduplicated, sorted list of matched skills.

---

## 8. Education Extraction

Performed in `education.py`:

* Operate on the text block identified as the Education section.
* Match degree keywords: B.Tech, B.E., M.Tech, MBA, B.Sc, M.Sc, Ph.D, etc.
* Extract institution name from adjacent lines using capitalisation heuristics.
* Extract graduation year using 4-digit year pattern (1970–2035 range).
* Extract CGPA / percentage using numeric patterns near keywords like "CGPA", "GPA", "%".

---

## 9. Work Experience Extraction

Performed in `experience.py`:

* Operate on the text block identified as the Experience section.
* Detect job entries by matching date-range patterns:
  `MMM YYYY – MMM YYYY`, `MM/YYYY – Present`, etc.
* Extract company name from the line preceding or following the date range.
* Extract job title using title-case heuristic on the same or adjacent line.
* Build a list of experience entries ordered chronologically.

---

## 10. JSON Generation

Assembled in `extractor.py`:

```json
{
  "full_name":    "...",
  "email":        "...",
  "phone":        "...",
  "linkedin":     "...",
  "github":       "...",
  "skills":       ["..."],
  "education":    [{ "degree": "...", "institution": "...", "year": "..." }],
  "experience":   [{ "title": "...", "company": "...", "duration": "..." }]
}
```

Fields that cannot be extracted are set to `null` (Python `None`) rather than omitted,
ensuring consumers always receive a consistent schema.

---

## 11. Assumptions

* The resume is written in English.
* At least one page of the PDF contains selectable text (not a scanned image).
* Section headings are on their own line or clearly separated from body text.
* The candidate's name appears in the first 5 lines of the document.
* Phone numbers follow common international formats (Indian +91 and US formats prioritised).

---

## 12. Limitations

* **Scanned PDFs** (image-only) cannot be parsed without OCR; this system has no OCR layer.
* **Multi-column layouts** may cause text extraction order to be incorrect.
* **Graphical or heavily styled resumes** may produce garbled text via PyMuPDF.
* **Ambiguous section headings** (e.g. a section called "About") may be misclassified.
* **Name extraction** is heuristic; names composed of uncommon tokens may be missed.
* **Skills coverage** depends entirely on the manually maintained `skills.json`.
