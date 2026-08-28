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

## 6. Contact Information Extraction  ✅ Implemented

`extractor/contact.py` extracts three mandatory fields from the full cleaned
text: **name**, **email**, and **phone**.  All extraction is deterministic —
no ML, no network calls, no external services.

### Email extraction (regex-based)

```
[a-zA-Z0-9][a-zA-Z0-9._%+-]*  @  domain.tld
```

- The pattern anchors with a negative lookbehind (`(?<![.\w])`) so partial
  matches mid-word are rejected.
- A positive lookahead ensures the match ends before a non-alphanumeric
  character, which avoids including trailing sentence punctuation.
- A post-match strip pass then removes any remaining `. , ; )` chars at the
  tail (handles edge cases like `"john@example.com."`).
- The result is lower-cased for consistency.
- If multiple emails exist, the **first** match in document order is returned.
- Label prefixes (`"Email: …"`, `"E-mail: …"`) are handled because the regex
  searches the whole line after the label has been stripped by a separate
  helper.

### Phone extraction (regex + validation)

The regex matches:
- Optional country code: `+91`, `+1`, `91`, etc.
- Optional parenthesised area code: `(022)`.
- 7–17 character core digit sequence with spaces, hyphens, or dots as
  separators.

After the regex finds a candidate, three validation checks filter it:

| Check | Rejects |
|---|---|
| ≥ 7 digits in the match | PIN codes, short IDs |
| Not a 4-digit number in range 1900–2099 | Standalone years (2020, 2024) |
| Next character is not `%` or `/` | Percentages, fractions |

Contact-label prefixes (`"Phone: …"`, `"Mobile: …"`) are stripped per-line
before the regex runs.

### Name extraction (conservative heuristic)

Name extraction has no reliable universal regex — it uses a layered filter
applied to the first **12 non-empty lines** of the document:

| Filter | What it rejects |
|---|---|
| Contains `@` | Email addresses |
| Contains URL pattern | LinkedIn, GitHub, website links |
| Matches contact-label prefix | `"Phone:"`, `"LinkedIn:"`, etc. |
| Token is a known section-heading word | SKILLS, EDUCATION, EXPERIENCE … |
| Token is a job-title word | engineer, developer, analyst, manager … |
| `< 60 %` alphabetic chars | Numeric-heavy lines (phone, years) |
| `> 50` characters | Long prose lines |
| `< 2` tokens | Single-word lines (skill names, etc.) |
| `> 5` tokens | Very long multi-word phrases |

The **first line** that passes all nine filters is accepted as the name.
It is returned **title-cased** (`"ALICE JOHNSON"` → `"Alice Johnson"`).

### Why name extraction is less deterministic than email

Email addresses have a globally unique syntactic marker (`@`).  Phone numbers
have a recognisable digit density.  Names have neither — they are arbitrary
strings of alphabetic tokens.  The heuristic approach above is conservative:
it prefers returning `None` over guessing incorrectly.

### How false positives are reduced

| Scenario | Guard |
|---|---|
| `"2024"` extracted as phone | Digit count < 7, and 4-digit year range check |
| `"95%"` extracted as phone | Next-character `%` check |
| `"Software Engineer"` as name | Job-title keyword filter |
| `"SKILLS"` as name | Section-heading keyword filter |
| `"john@example.com."` (trailing dot) | Email post-match strip |
| Sentence containing "experience" | Length + sentence-indicator guards in `sections.py` |

### Missing fields

A field that cannot be confidently extracted is returned as Python `None`.
The caller always receives all three keys:

```python
{"name": None, "email": None, "phone": None}
```

No field is ever omitted from the result dict, and no value is fabricated.

## 7. Skills Extraction

Performed in `skills.py` using `data/skills.json` as the knowledge base.

### Why a skill dictionary is used

A curated dictionary provides deterministic, maintainable, and explainable
matching — no model weights, no training data, no network calls.  Adding or
removing a skill requires editing only one JSON file.

### Knowledge base structure (`data/skills.json`)

Skills are organised into 11 categories for readability:
`programming_languages`, `web_frontend`, `web_backend`, `databases`, `cloud`,
`devops`, `data_science`, `machine_learning`, `mobile`, `cs_fundamentals`,
`tools_and_other`.

An `aliases` block maps alternative spellings (lower-cased) to the canonical
form:

```json
"aliases": {
  "js":         "JavaScript",
  "nodejs":     "Node.js",
  "c plus plus": "C++",
  "sklearn":    "Scikit-learn",
  "k8s":        "Kubernetes"
}
```

### How aliases are canonicalized

At module load-time, a `SkillDatabase` is built:
1. All canonical names from every category list are indexed.
2. The `aliases` dict is loaded: `lower(alias) → canonical`.
3. For each skill (canonical + alias targets), a boundary-aware regex is
   compiled and stored sorted by length descending.

During matching, `resolve_alias(token)` does a O(1) dict lookup and returns
the canonical string.

### How section-aware extraction works

```python
extract_skills(text, sections={"skills": "Python, Java, Docker"})
```

If `sections["skills"]` is non-empty, only that sub-string is scanned.
This is the preferred mode because the skills section contains intentionally
listed skills — not incidental mentions in prose.

### How fallback extraction works

If no `skills` section is available, the full cleaned text is scanned using
the same boundary-aware patterns.  Fallback is inherently less precise —
technical words mentioned in experience narratives may be extracted — but is
far better than returning nothing.

### How boundary-aware matching prevents false positives

Three tiers of matching protect against substring collisions:

**Tier 1 — alias/token pass (before regex):**
The text is split on separators (`,`, `|`, `•`, etc.) into individual tokens
and adjacent pairs/triplets.  These are looked up in the alias map.  This
handles `"JS"`, `"NodeJS"`, `"C plus plus"` without any regex.

**Tier 2 — compiled regex with custom boundaries:**

| Skill type | Pattern | Why |
|---|---|---|
| Strict (`C`, `R`, `Go`) | `(?<![A-Za-z0-9+#.-])SKILL(?![A-Za-z0-9+#.-])` | Prevents `C` matching in `C++`, `CSS`, `Cloud`, `Scala` |
| Ends in `+` or `#` (`C++`, `C#`) | `(?<![A-Za-z0-9])SKILL(?![A-Za-z0-9])` | Exact literal, no word-char adjacent |
| Contains `.` (`Node.js`, `.NET`) | `(?<![A-Za-z0-9.])SKILL(?![A-Za-z0-9.])` | Dot exclusion prevents partial URL matches |
| Standard single/multi-word | `(?<!\w)SKILL(?!\w)` | Standard word-boundary equivalent |

**Tier 3 — longest-first ordering:**
Patterns are sorted by skill length descending.  `"Spring Boot"` is attempted
before `"Spring"`, preventing the longer skill from being overshadowed.

### How multi-word skills are handled

Multi-word skills (e.g. `"Machine Learning"`, `"Spring Boot"`,
`"Data Structures"`) are treated as atomic units in the regex and as 2- or
3-word phrases in the token pass.  When a multi-word skill is matched, its
component words are not additionally returned as separate skills.

### How duplicates are removed

A `seen_canonical` set tracks which canonical names have already been found.
Skills appearing via both the token pass (e.g. `"JS"`) and the pattern pass
(e.g. `"JavaScript"`) are merged into a single entry.  First occurrence wins.

### Known limitations

- **Out-of-vocabulary skills**: skills not in `data/skills.json` are never
  extracted.  The dictionary must be maintained manually.
- **Fallback mode precision**: experience narratives mentioning technologies
  may produce skill results not intended by the candidate.
- **Uncommon aliases**: only aliases listed in the `aliases` block are
  resolved; creative abbreviations (e.g. `"PG"` for PostgreSQL) will be missed.
- **Non-English resumes**: skill names in other languages are not covered.

Performed in `education.py`.  ✅ Implemented

### Section-aware extraction

If `sections["education"]` is present and non-empty, only that text is
scanned.  This isolates education content from the rest of the resume and
significantly reduces false positives.  Fallback to the full text is
performed only when no education section is available.

### Degree pattern matching

A list `_DEGREE_PATTERNS` contains 30+ patterns covering doctoral, master's,
bachelor's, diploma, and secondary degrees.  All patterns use:
- **Negative lookbehind/lookahead on letters** (`(?<![A-Za-z])…(?![A-Za-z])`)
  so abbreviations like `M.E.` cannot match inside `"resume"`.
- Case-insensitive matching (`re.IGNORECASE`).

Examples of recognised forms:
`Ph.D.`, `M.Tech`, `MBA`, `B.Tech`, `B.Sc`, `BCA`, `Diploma`, `HSC`, `SSC`,
`12th`, `Bachelor of Technology`, `Master of Science`.

### Field-of-study extraction

After a degree token is matched, the remainder of the line is inspected for
a field-of-study separator pattern (`in <X>`, `- <X>`, `(<X>)`, `, <X>`).
The captured text becomes both `field_of_study` and is appended to the
`degree` string for readability (e.g. `"B.Tech in Computer Engineering"`).

### Institution identification

Lines that do not match any other category (degree / date / grade / skip list)
and pass a five-condition filter are treated as institution candidates:

1. Non-empty, 3–120 chars.
2. Does not match a skip-list word (CGPA, Percentage, Email, etc.).
3. Does not match the grade regex.
4. Is not a date-only line.
5. Has ≤ 8 words and ≥ 45% alphabetic characters.

When multiple candidates exist, they are ranked by a confidence score that
rewards institution-keyword presence (`university`, `college`, `institute`,
`polytechnic`, etc.) and title-case word formatting.

### Entry grouping

The section text is split into groups using a degree-boundary strategy:
a new group is started whenever a degree pattern is found and the current
group already contains a degree.  Each group is then parsed independently
by `_parse_group`.

A secondary inline parser (`_try_parse_inline`) handles single-line or
comma/pipe-separated formats such as:
- `"B.Tech | Computer Engineering | ABC University | 2023-2027"`
- `"M.Tech — Data Science — IIT Delhi — 2022-2024"`

### Date extraction

Date spans such as `2023 - 2027`, `Aug 2022 - May 2024`, and `2023 - Present`
are matched by `_DATE_SPAN_RE`.  Single years (1950–2035) serve as a fallback.
Date-only lines are identified first and skipped for other field extraction to
prevent years from being misclassified as institutions or grades.

### Grade extraction

Explicit grade lines (`CGPA: 9.2`, `GPA: 3.8/4.0`, `Percentage: 91%`,
bare `92.5%`) are matched by `_GRADE_RE` and stored verbatim.

### Conservative validity filtering

A record is only included if:
- Its `degree` field is non-None and at least 3 characters long.

Institution-only records (where `degree=None`) are discarded — they would
create false positives from plain sentences in fallback mode.

### Duplicate handling

Records are de-duplicated by a `(lower(degree), lower(institution))` key.
First occurrence in document order wins.

### Known limitations

- **Institution-without-keyword**: institutions whose names contain no
  standard keyword (University, College, etc.) may occasionally be missed.
- **Unusual abbreviations**: degree abbreviations not in `_DEGREE_PATTERNS`
  will be missed.
- **Multi-column PDF layouts**: text extraction order may mismatch the visual
  layout, confusing the line-grouping heuristic.
- **Degree-only entries**: records where the institution is completely absent
  will have `institution=None`.
- **Fallback precision**: education-like phrases in project or experience
  descriptions may be incorrectly extracted in fallback mode.

Performed in `experience.py`.  ✅ Implemented

### Section-aware extraction

If `sections["experience"]` is present and non-empty, only that sub-string
is scanned.  This prevents education entries, project descriptions, and skills
lists from being misinterpreted as work experience.  Fallback to the full text
is used only when no experience section is detected.

### Entry boundary detection — two-phase approach

**Phase 1 — blank-line segmentation.**
The section text is split into *raw blocks* at blank lines.  This handles the
most common resume format where jobs are separated by empty lines.

**Phase 2 — intra-block splitting.**
Each raw block is further inspected.  If a block contains a job-title-like
line that appears *after* a date line, that signals a new entry within the
same block (no blank line between jobs).  The block is split at that point.

This two-phase strategy correctly handles:
- standard blank-line-separated multi-job sections
- tightly-packed single-column layouts
- entries where only Phase 1 fires (simple single-entry sections)

### Job title identification

A line is classified as a job title if it passes all of:
1. Length: 3–80 chars, ≤7 words.
2. Not a date-only line.
3. Not a bullet line.
4. Not a degree/education line (`_DEGREE_GUARD_RE`).
5. Not dominated by commas or pipes (→ skills list).
6. Contains at least one known job-title keyword (`engineer`, `developer`,
   `analyst`, `intern`, `manager`, `intern`, `researcher`, etc.).
7. Does not contain known section-heading or degree words.
8. ≥55% of characters are alphabetic.

The keyword set is intentionally broad so that novel titles such as
`"Quantitative Researcher"` or `"Site Reliability Engineer"` are recognised.

### Company identification

A line is classified as a company candidate if it passes:
1. Length: 2–80 chars, ≤7 words.
2. Not a date, bullet, or degree line.
3. Not a comma/pipe-heavy skills line.
4. ≥45% alphabetic characters.
5. Either contains a company-keyword (`Technologies`, `Ltd`, `Pvt`, `Inc`,
   `Solutions`, `Labs`, `Consulting`, etc.) **or** every word starts with
   an uppercase letter (proper name heuristic).

Within a group, the first non-title candidate is assigned as the company.

### Date detection

`_DATE_SPAN_RE` matches:
- `"June 2024 - August 2025"`, `"Jan 2023 – Present"`, `"2024 - 2025"`
- `"01/2023 - 05/2024"`, `"2024–2025"` (en-dash)
- Bare `"Present"` / `"Current"` as part of a span

`_DATE_ONLY_LINE_RE` identifies lines that contain *only* a date, so they are
claimed as `dates` immediately and not re-evaluated as company or title lines.

Inline dates embedded in a line (e.g. `"ABC Corp | 2024–2025"`) are extracted
with `_DATE_SPAN_RE`, removed from the line, and the remainder is re-processed.

### Bullet / description handling

Lines starting with `-`, `•`, `*`, `▪`, `●` are bullet descriptions.  The
leading marker and surrounding whitespace are stripped.  Cleaned text is
appended to `record["description"]` as a list of strings.

### Location detection

A line is classified as a location when `_LOCATION_SIGNAL_RE` matches a known
city/country/state or the word `Remote`.  Location detection is conservative;
if ambiguous, `None` is returned.  A missing location never discards the entry.

### Inline / pipe-separated formats

`_try_parse_inline` handles compact single-line entries such as:
`"Software Engineer | ABC Corp | 2024 - 2025"`

### Duplicate handling

Records are de-duplicated by a `(lower(job_title), lower(company), lower(dates))`
key.  First occurrence wins; document order is preserved.

### False-positive protection

- **Skills lists**: comma/pipe-heavy lines (>2 commas or >2 pipes) are rejected
  as job title and company candidates.
- **Degree lines**: `_DEGREE_GUARD_RE` prevents B.Tech / University / etc. from
  becoming job titles.
- **Section headings**: words like `SKILLS`, `EDUCATION`, `EXPERIENCE` in
  `_NOT_TITLE_WORDS` block those lines from being classified as titles.
- **Prose sentences**: a 10+ word sentence almost never passes the ≤7-word
  title filter.
- **Bare dates**: a date-only line with no associated title/company does not
  create a valid record (`_is_valid_record` requires at least one of
  job_title / company / dates, but a bare date record is still weak).

### Known limitations

- **Ambiguous title/company order**: if a resume places company before title,
  the heuristics may assign them in the wrong field.
- **Non-English resumes**: job-title keywords are English only.
- **Fallback precision**: experience-like patterns in projects or education may
  be extracted when no section boundary is available.
- **Location**: only a small set of known city/country names triggers location
  detection.  Lesser-known cities are not detected.
- **Multi-column PDFs**: text extraction order may scramble lines.

---

## 10. End-to-End Pipeline & JSON Generation

Performed in `extractor.py` via `extract_resume(source, filename=None)` and `ResumeExtractor`.  ✅ Implemented

### Architecture Overview

The system processes resumes through a linear, deterministic 8-step pipeline:

```
Resume Source (Path / Bytes / Stream)
  │
  ▼
[1. Document Parsing]       → extractor.parser.extract_text()
  │
  ▼
[2. Text Normalisation]     → extractor.cleaner.clean_text()
  │
  ▼
[3. Section Detection]      → extractor.sections.detect_sections()
  │
  ├───► [4. Contact Extraction]   → extractor.contact.extract_contact_info()
  ├───► [5. Skills Extraction]    → extractor.skills.extract_skills(sections=...)
  ├───► [6. Education Extraction] → extractor.education.extract_education(sections=...)
  └───► [7. Experience Extraction]→ extractor.experience.extract_experience(sections=...)
  │
  ▼
[8. Result Assembly]        → Standard JSON-serialisable dictionary
```

### 1. Input Handling & Parsing
The pipeline accepts filesystem paths (`str` or `Path`), raw `bytes`, or binary streams (e.g. Streamlit's `UploadedFile`, `io.BytesIO`). Filename extension matching determines the underlying parser:
- PDF files are parsed via PyMuPDF (`pymupdf`).
- DOCX files are parsed via `python-docx`.

### 2. Cleaning & Normalisation
Raw text is passed through Unicode NFC normalisation, non-breaking space replacement, control-character stripping, per-line stripping, and intra-line whitespace collapsing. Original casing and punctuation are preserved.

### 3. Section Detection
`detect_sections()` identifies canonical headings (`skills`, `education`, `experience`, `projects`, etc.) and isolates their text blocks.

### 4. Extraction Routing
- **Contact Info (`name`, `email`, `phone`)**: Scanned from the full cleaned text to capture header information preceding any section.
- **Skills (`skills`)**: Prefers the isolated `skills` section, resolving aliases against `data/skills.json` and applying boundary-aware regex patterns.
- **Education (`education`)**: Prefers the isolated `education` section, extracting degrees, institutions, date ranges, and scores.
- **Work Experience (`experience`)**: Prefers the isolated `experience` section, grouping lines into entries and extracting job titles, companies, date spans, locations, and bullet descriptions.

### 5. Final JSON Assembly & Stable Output Schema
The pipeline produces a JSON-serialisable dictionary with a consistent schema:

```json
{
  "name": "John Doe",
  "email": "john.doe@example.com",
  "phone": "+91 9876543210",
  "skills": ["Python", "SQL", "Docker"],
  "education": [
    {
      "degree": "B.Tech in Computer Engineering",
      "institution": "ABC University",
      "dates": "2020 - 2024",
      "field_of_study": "Computer Engineering",
      "grade": "CGPA: 8.9",
      "location": null
    }
  ],
  "experience": [
    {
      "job_title": "Software Engineer Intern",
      "company": "XYZ Technologies",
      "dates": "June 2024 - August 2024",
      "location": "Mumbai",
      "description": [
        "Developed REST APIs using Python and FastAPI",
        "Optimized SQL database queries"
      ]
    }
  ]
}
```

- If a scalar field is missing or cannot be extracted, it is set to `null` (`None`).
- If a list field has no matches, it is set to `[]`.
- Mandatory top-level keys (`name`, `email`, `phone`, `skills`, `education`, `experience`) are always present.

### 6. Error Handling
- Invalid, corrupted, or unsupported file formats raise `ParserError` with clear user-facing messages.
- Empty documents with no selectable text raise `ParserError`.
- Valid documents with partial or missing resume fields return `null` / `[]` without crashing.

### 7. Deterministic & Local Architecture
- **Zero External Calls**: No network requests, external APIs, or cloud parsers are invoked.
- **Zero LLM / GenAI Usage**: The system does NOT use OpenAI, Gemini, Claude, or any generative AI model. All extraction is 100% rule-based and deterministic.
- **Privacy & Compliance**: Resume content never leaves the local execution environment.

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
