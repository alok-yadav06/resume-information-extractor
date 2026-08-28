# Resume Information Extraction System


---

## Overview

This project is a locally-running **Resume Information Extractor** that accepts PDF and DOCX files and
returns structured JSON containing key candidate information. No external AI or LLM API is involved;
all extraction is performed through rule-based, deterministic techniques.

---

## Objective

Build a modular, well-structured Python application that:

* Parses raw text from PDF and DOCX resumes.
* Cleans and normalises the extracted text.
* Detects logical sections (Education, Experience, Skills, etc.).
* Extracts structured fields using regular expressions and keyword matching.
* Returns a validated JSON object for each processed resume.

---

## Planned Features

| Feature | Status |
|---|---|
| PDF parsing (PyMuPDF) | 🔲 Planned |
| DOCX parsing (python-docx) | 🔲 Planned |
| Text cleaning & normalisation | 🔲 Planned |
| Section detection | 🔲 Planned |
| Name extraction | 🔲 Planned |
| Email extraction (regex) | 🔲 Planned |
| Phone extraction (regex) | 🔲 Planned |
| Skills matching | 🔲 Planned |
| Education extraction | 🔲 Planned |
| Work experience extraction | 🔲 Planned |
| LinkedIn / GitHub profile detection | 🔲 Planned |
| Streamlit web UI | 🔲 Planned |
| JSON output | 🔲 Planned |

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.10+ | Core runtime |
| PDF Parsing | PyMuPDF (`fitz`) | Extract text from PDF files |
| DOCX Parsing | python-docx | Extract text from Word files |
| NLP / Extraction | `re`, string ops | Regex & rule-based extraction |
| Web UI | Streamlit | Interactive upload & display |
| Data | JSON files | Skills reference lists |
| Testing | pytest (stdlib) | Unit tests |

> **No external LLM, AI API, or cloud service is used at any stage.**

---

## Project Structure

```
resume-information-extractor/
│
├── app.py                  ← Streamlit web application entry point
├── requirements.txt        ← Pinned production dependencies
├── README.md               ← This file
├── .gitignore
│
├── extractor/              ← Core extraction package
│   ├── __init__.py
│   ├── parser.py           ← PDF / DOCX → raw text
│   ├── cleaner.py          ← Text normalisation
│   ├── sections.py         ← Section boundary detection
│   ├── contact.py          ← Name, email, phone, LinkedIn, GitHub
│   ├── skills.py           ← Skills matching against reference list
│   ├── education.py        ← Education block extraction
│   ├── experience.py       ← Work experience block extraction
│   └── extractor.py        ← Orchestrator: runs the full pipeline
│
├── data/
│   ├── skills.json         ← Curated skills reference list
│   └── sample_resumes/     ← Example PDF / DOCX files for testing
│
├── tests/                  ← pytest unit tests
│
├── outputs/
│   └── sample_outputs/     ← Example JSON output files
│
└── docs/
    └── approach.md         ← Technical design document
```

---

## Setup

```bash
# 1. Clone the repository
git clone <repo-url>
cd resume-information-extractor

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```

---

## Execution

```bash
# Run the Streamlit web application
streamlit run app.py
```

Open the URL shown in the terminal (usually `http://localhost:8501`) in your browser.

---

## Extraction Approach

The pipeline follows these sequential steps:

1. **Parse** — Extract raw text from PDF (PyMuPDF) or DOCX (python-docx).
2. **Clean** — Normalise whitespace, fix encoding artefacts, strip noise.
3. **Section Detection** — Identify section boundaries using heading keywords.
4. **Contact Extraction** — Regex patterns for email, phone, LinkedIn, GitHub.
5. **Name Extraction** — Heuristic: first non-empty line or capitalised token near the top.
6. **Skills Matching** — Lookup against a curated `skills.json` reference list.
7. **Education Parsing** — Keyword + pattern matching within the Education section.
8. **Experience Parsing** — Date-range pattern + company/role heuristics.
9. **JSON Assembly** — Merge all fields into a validated output dictionary.

---

## Limitations

* Extraction accuracy depends on resume formatting consistency.
* Highly creative or graphical PDF layouts may yield incomplete text.
* Name detection is heuristic and may fail on unusual resume structures.
* The skills list must be maintained manually.
* Non-English resumes are not supported.
