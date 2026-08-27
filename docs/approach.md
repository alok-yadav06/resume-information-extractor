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

## 3. PDF / DOCX Parsing  ✅ Implemented

`extractor/parser.py` is the first and only stage that touches the actual file.
Its sole responsibility is converting a binary file into a plain-text string.

### Why a separate parser module?

Keeping file I/O and format-specific decoding completely isolated from pattern
matching and field extraction means:
- Each concern can be unit-tested independently (no real resumes needed).
- Swapping or extending a parser (e.g. adding ODT support) requires touching
  only this one file.
- The rest of the pipeline only ever sees clean strings — no fitz or docx objects.

### Input handling

The module defines a `FileSource` type alias covering three input forms:
- A filesystem path (`str` or `Path`) — useful for CLI and tests.
- Raw `bytes` — useful for in-memory fixture creation in tests.
- A binary file-like object (`io.IOBase`) — useful for Streamlit's
  `UploadedFile`, `io.BytesIO`, or any stream.

An internal `_to_bytes(source)` helper normalises all three into raw bytes,
so the PDF and DOCX parsers share a single, clean code path.

### PDF — PyMuPDF (`fitz`)

```python
doc = fitz.open(stream=raw_bytes, filetype="pdf")
for page_index in range(len(doc)):
    page = doc.load_page(page_index)
    page_text = page.get_text("text")   # reading-order, plain text
```

- `fitz.open(stream=..., filetype="pdf")` avoids writing a temporary file to
  disk, keeping parsing entirely in-memory.
- `get_text("text")` preserves left-to-right, top-to-bottom reading order.
- Pages are joined with `"\f\n"` (form-feed + newline) so callers can detect
  page boundaries if needed.
- A `ParserError` is raised if the file is corrupt, password-protected, or if
  no selectable text is found (e.g. scanned image PDFs).

### DOCX — python-docx

```python
doc = Document(io.BytesIO(raw_bytes))
for para in doc.paragraphs:
    lines.append(para.text.strip())
for table in doc.tables:
    for row in table.rows:
        lines.append("  |  ".join(cell.text.strip() for cell in row.cells))
```

- Both body paragraphs **and table cells** are extracted, because many resumes
  use tables to lay out skills, contact info, or education entries.
- Table rows are joined with `" | "` so the cell values remain readable and
  searchable without merging into a single word.
- A `ParserError` is raised on invalid or empty files.

### Unified entry point — `extract_text(source, filename)`

```python
ext = _detect_extension(source, filename)   # ".pdf" or ".docx"
if ext == ".pdf":  return extract_text_from_pdf(source)
if ext == ".docx": return extract_text_from_docx(source)
raise ParserError("Unsupported file format …")
```

- Format detection is case-insensitive (`.PDF`, `.Docx` all work).
- The `filename` parameter is the hook for Streamlit integration:
  `extract_text(uploaded_file, filename=uploaded_file.name)`.
- Unsupported extensions (`.txt`, `.doc`, `.rtf`, …) raise an informative
  `ParserError` immediately — no silent failures.

**Output**: a single plain-text `str` representing the full resume, ready to
be passed to `cleaner.py`.

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
