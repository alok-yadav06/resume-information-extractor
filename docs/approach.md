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

## 4. Text Cleaning  ✅ Implemented

`extractor/cleaner.py` is the second stage of the pipeline.  It receives the
raw string from the parser and returns a consistently formatted string that all
downstream modules can rely on.

### Why normalisation is necessary

PDF and DOCX parsers are format converters, not text cleaners.  Their output
commonly contains:
- Windows-style `\r\n` and old Mac-style `\r` line endings mixed with `\n`.
- Non-breaking spaces (`\u00a0`) and other Unicode whitespace variants that
  look like spaces but break regex word-boundary matching.
- Runs of multiple spaces from columnar PDF layouts ("John     Doe").
- Three, four, or five consecutive blank lines from page headers/footers.
- Null bytes, form feeds, and other invisible control characters.
- Composite Unicode characters that may not match their precomposed equivalents.

Without normalisation, a simple email regex can fail because the text contains
`\u00a0` instead of a space next to the address.

### The 8-step cleaning pipeline

Steps are applied in order — each step's output feeds the next:

| Step | What it does |
|---|---|
| 1. Unicode NFC | Unifies accented / composite characters (é vs e + ́) |
| 2. Special whitespace | Replaces `\u00a0`, `\u2009`, BOM, etc. with plain spaces |
| 3. Control-char removal | Strips invisible bytes; keeps `\n` and `\t` |
| 4. Line-ending unification | `\r\n`, `\r` → `\n`; `\f` (PDF page break) → `\n\n` |
| 5. Per-line strip | Removes leading/trailing spaces from every line individually |
| 6. Intra-line whitespace collapse | `"John     Doe"` → `"John Doe"` |
| 7. Blank-line reduction | Three or more consecutive `\n` → two `\n` (one visible gap) |
| 8. Document-level strip | Removes leading/trailing whitespace from the whole output |

```python
# Simplified view of the pipeline
text = _normalise_unicode(text)
text = _replace_special_whitespace(text)
text = _remove_control_characters(text)
text = _normalise_line_endings(text)
text = _strip_lines(text)
text = _collapse_intra_line_whitespace(text)
text = _reduce_blank_lines(text)
text = text.strip()
```

### What is intentionally preserved

| Preserved | Reason |
|---|---|
| Original casing | Name detection and degree matching depend on capitalisation |
| Punctuation (`.`, `@`, `+`, `-`, `/`, `#`) | Email, URL, phone, C++, Node.js, B.Tech |
| Newlines | Section structure depends on line boundaries |
| Single blank lines | Visual separator between resume sections |
| Duplicate lines | May be meaningful (skill listed under multiple sections) |

### Safety

- Passing a non-`str` argument raises `TypeError` immediately.
- Empty or whitespace-only input returns `""` without error.
- The function is **idempotent**: `clean_text(clean_text(x)) == clean_text(x)`.

**Output**: a normalised `str` passed to `sections.py` for section detection.

## 5. Section Detection  ✅ Implemented

`extractor/sections.py` is the third pipeline stage.  It receives normalised
text from the cleaner and returns a `dict[str, str]` that maps canonical
section names to their body text.

### Why section detection is useful

Extraction modules (skills, education, experience) produce far better results
when they operate on a focused sub-string rather than the entire document.
For example, a date-range in a *certification* block should not be confused
with work experience.  Isolating sections first makes every later rule simpler
and more precise.

### How aliases are handled

The module maintains a single flat dictionary `SECTION_ALIASES` that maps
every known heading variant (lower-cased) to a canonical name:

```python
SECTION_ALIASES = {
    "skills":               "skills",
    "technical skills":     "skills",
    "core competencies":    "skills",
    "technologies & tools": "skills",
    # ... 100+ entries covering 10+ canonical sections
}
```

Benefits of this design:
- Adding a new alias requires editing only the dictionary — no logic changes.
- The lookup is O(1) (frozenset membership test).
- All 10 canonical sections (`summary`, `objective`, `skills`, `education`,
  `experience`, `projects`, `certifications`, `achievements`, `languages`,
  `interests`) are supported.

### How section boundaries are identified

The detector makes **two passes** over the lines of the document:

**Pass 1 — classify lines as headings or body:**
For every line, `_is_heading(line)` applies four rules:
1. The stripped line is non-empty.
2. The raw line is ≤ 60 characters (avoids treating prose sentences as headings).
3. After stripping trailing `:`, `–`, `—`, `.`, etc. and lower-casing, the line
   exists in `SECTION_ALIASES`.
4. The normalised line does **not** contain sentence-indicator words
   (`the`, `a`, `an`, `with`, `have`, `my`, `in`, `of`, etc.) — this prevents
   `"I have experience in Python"` from being classified as an experience heading.

**Pass 2 — slice body text:**
Heading positions are collected as `[(line_index, canonical_name), ...]`.
For each consecutive pair, the lines between them form the section body.
The final heading captures all remaining lines to the end of the document.

### How false positives are reduced

Two complementary guards work together:

| Guard | What it prevents |
|---|---|
| Length limit (60 chars) | Long sentences containing keyword words |
| Sentence-indicator words | Short sentences like "I have experience in Java" |

Because matching is **exact** (the whole normalised line must equal a known
alias), words like "experience" or "skills" appearing anywhere inside a body
sentence never trigger a false heading match.

### How duplicate sections are handled

If two headings resolve to the same canonical name (e.g. "SKILLS" and
"TECHNICAL SKILLS" both → `"skills"`), their body blocks are **appended** in
document order, separated by a blank line:

```python
# Simplified
if canonical in sections:
    sections[canonical].append(body_text)   # combine
else:
    sections[canonical] = [body_text]       # first occurrence
```

The caller always receives a single string per canonical key.

**Output**: `dict[str, str]` — only sections that were actually detected are
included; missing sections are omitted rather than set to `None` or `""`.

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
