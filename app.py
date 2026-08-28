"""
app.py
------
Streamlit web application for the Resume Information Extraction System.

This application provides a compact, professional dashboard for uploading
resumes (PDF / DOCX) and visualising structured candidate information
extracted by the fully deterministic, local rule-based pipeline.

Run with:
    streamlit run app.py
"""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from extractor import ParserError, extract_resume


# ---------------------------------------------------------------------------
# Page configuration — must be the very first Streamlit call
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Resume Extractor",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------------
# Theme-aware CSS
# ---------------------------------------------------------------------------
# Rules intentionally avoid hard-coding light-mode colours for text/background
# so they render correctly in both light and dark Streamlit themes.
# Only structural rules (spacing, borders, border-radius) use opaque values.

CUSTOM_CSS = """
<style>
    /* ── Layout ─────────────────────────────────────────────────── */
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 1160px;
    }

    /* ── Page title row ─────────────────────────────────────────── */
    .app-header {
        display: flex;
        align-items: center;
        gap: 0.6rem;
        margin-bottom: 0.2rem;
    }
    .app-title {
        font-size: 1.6rem;
        font-weight: 700;
        margin: 0;
    }
    .app-subtitle {
        font-size: 0.9rem;
        opacity: 0.6;
        margin-bottom: 0.8rem;
    }

    /* ── Privacy badge ───────────────────────────────────────────── */
    .privacy-badge {
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        border: 1px solid currentColor;
        border-radius: 9999px;
        padding: 3px 12px;
        font-size: 0.78rem;
        opacity: 0.65;
        margin-bottom: 1.2rem;
    }

    /* ── Field label / value pairs ───────────────────────────────── */
    .field-label {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        opacity: 0.55;
        margin-bottom: 2px;
    }
    .field-value {
        font-size: 0.95rem;
        font-weight: 500;
        word-break: break-word;
    }
    .field-value a {
        text-decoration: none;
    }
    .field-value a:hover {
        text-decoration: underline;
    }
    .not-detected {
        opacity: 0.38;
        font-style: italic;
    }

    /* ── Skill badges ────────────────────────────────────────────── */
    .skill-pills {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-bottom: 0.25rem;
    }
    .skill-pill {
        border: 1px solid currentColor;
        border-radius: 9999px;
        padding: 2px 11px;
        font-size: 0.8rem;
        font-weight: 500;
        opacity: 0.85;
        white-space: nowrap;
    }

    /* ── Timeline entries ────────────────────────────────────────── */
    .entry-block {
        border-left: 3px solid;
        border-color: var(--entry-border, #3b82f6);
        padding-left: 0.9rem;
        margin-bottom: 1.1rem;
    }
    .entry-title {
        font-size: 0.95rem;
        font-weight: 600;
        margin-bottom: 1px;
    }
    .entry-subtitle {
        font-size: 0.875rem;
        opacity: 0.75;
        margin-bottom: 2px;
    }
    .entry-meta {
        font-size: 0.8rem;
        opacity: 0.55;
        margin-bottom: 4px;
    }
    .entry-bullet {
        font-size: 0.85rem;
        opacity: 0.85;
        margin-bottom: 2px;
    }

    /* ── Section divider ─────────────────────────────────────────── */
    .section-divider {
        height: 1px;
        background: currentColor;
        opacity: 0.08;
        margin: 1rem 0;
    }

    /* ── Empty state card ────────────────────────────────────────── */
    .empty-card {
        text-align: center;
        padding: 3rem 1.5rem;
        border: 2px dashed currentColor;
        border-radius: 12px;
        opacity: 0.7;
        margin-top: 1rem;
    }
    .empty-card h3 {
        margin-bottom: 0.4rem;
        font-size: 1.1rem;
    }
    .empty-card p {
        font-size: 0.88rem;
        opacity: 0.7;
        max-width: 480px;
        margin: 0 auto 1rem auto;
    }
    .empty-features {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 0.5rem 1.2rem;
        font-size: 0.84rem;
        opacity: 0.6;
    }
</style>
"""


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def format_file_size(size_bytes: int) -> str:
    """Human-readable file size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def _val(value: Any, fallback: str = "—") -> str:
    """Return value as string or a fallback marker."""
    return str(value).strip() if value else fallback


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------

def render_contact_section(data: dict[str, Any]) -> None:
    """Three-column contact row: name / email / phone."""
    st.markdown("#### 👤 Contact")
    c1, c2, c3 = st.columns(3)

    def _field(col, label: str, html_value: str) -> None:
        with col:
            st.markdown(f"<div class='field-label'>{label}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='field-value'>{html_value}</div>", unsafe_allow_html=True)

    name  = data.get("name")
    email = data.get("email")
    phone = data.get("phone")

    _field(c1, "Full Name",
           f"<strong>{name}</strong>" if name else "<span class='not-detected'>Not detected</span>")
    _field(c2, "Email",
           f"<a href='mailto:{email}'>{email}</a>" if email else "<span class='not-detected'>Not detected</span>")
    _field(c3, "Phone",
           phone if phone else "<span class='not-detected'>Not detected</span>")


def render_profiles_section(data: dict[str, Any]) -> None:
    """Two-column LinkedIn / GitHub row."""
    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
    st.markdown("#### 🌐 Profiles")
    c1, c2 = st.columns(2)

    linkedin = data.get("linkedin")
    github   = data.get("github")

    def _link(col, label: str, url: str | None) -> None:
        with col:
            st.markdown(f"<div class='field-label'>{label}</div>", unsafe_allow_html=True)
            if url:
                st.markdown(
                    f"<div class='field-value'><a href='{url}' target='_blank'>🔗 {url}</a></div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div class='field-value not-detected'>Not detected</div>",
                    unsafe_allow_html=True,
                )

    _link(c1, "LinkedIn", linkedin)
    _link(c2, "GitHub", github)


def render_skills_section(skills: list[str]) -> None:
    """Skill badges with count."""
    st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)
    n = len(skills)
    st.markdown(f"#### 🛠️ Skills &nbsp;<small style='opacity:.5;font-weight:400'>({n})</small>", unsafe_allow_html=True)

    if not skills:
        st.caption("No skills detected.")
        return

    pills = "".join(f"<span class='skill-pill'>{s}</span>" for s in skills)
    st.markdown(f"<div class='skill-pills'>{pills}</div>", unsafe_allow_html=True)


def render_education_section(education: list[dict[str, Any]]) -> None:
    """Education entries as timeline cards."""
    n = len(education)
    st.markdown(f"#### 🎓 Education &nbsp;<small style='opacity:.5;font-weight:400'>({n})</small>", unsafe_allow_html=True)

    if not education:
        st.caption("No education history detected.")
        return

    for entry in education:
        degree      = entry.get("degree") or "Degree not specified"
        institution = entry.get("institution", "")
        dates       = entry.get("dates", "")
        grade       = entry.get("grade", "")
        field       = entry.get("field_of_study", "")
        location    = entry.get("location", "")

        meta_parts: list[str] = []
        if dates:       meta_parts.append(f"📅 {dates}")
        if field and field not in degree:
                        meta_parts.append(f"📚 {field}")
        if grade:       meta_parts.append(f"🏆 {grade}")
        if location:    meta_parts.append(f"📍 {location}")
        meta_html = " &nbsp;·&nbsp; ".join(meta_parts)

        st.markdown(
            f"""
            <div class='entry-block'>
                <div class='entry-title'>{degree}</div>
                {f"<div class='entry-subtitle'>{institution}</div>" if institution else ""}
                {f"<div class='entry-meta'>{meta_html}</div>" if meta_html else ""}
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_experience_section(experience: list[dict[str, Any]]) -> None:
    """Work experience entries as timeline cards with bullet points."""
    n = len(experience)
    st.markdown(f"#### 💼 Experience &nbsp;<small style='opacity:.5;font-weight:400'>({n})</small>", unsafe_allow_html=True)

    if not experience:
        st.caption("No work experience detected.")
        return

    for entry in experience:
        title    = entry.get("job_title") or "Position not specified"
        company  = entry.get("company", "")
        dates    = entry.get("dates", "")
        location = entry.get("location", "")
        bullets  = entry.get("description", [])

        meta_parts: list[str] = []
        if dates:    meta_parts.append(f"📅 {dates}")
        if location: meta_parts.append(f"📍 {location}")
        meta_html = " &nbsp;·&nbsp; ".join(meta_parts)

        if bullets:
            bullets_html = "".join(f"<li class='entry-bullet'>{b}</li>" for b in bullets)
            bullets_block = f"<ul style='margin: 4px 0 0; padding-left: 1.1rem;'>{bullets_html}</ul>"
        else:
            bullets_block = ""

        st.markdown(
            f"""
            <div class='entry-block'>
                <div class='entry-title'>{title}</div>
                {f"<div class='entry-subtitle'>{company}</div>" if company else ""}
                {f"<div class='entry-meta'>{meta_html}</div>" if meta_html else ""}
                {bullets_block}
            </div>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

def main() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # ── Sidebar ──────────────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("## 📄 Resume Extractor")
        st.caption("Upload a PDF or DOCX resume to extract structured candidate information.")

        uploaded_file = st.file_uploader(
            label="Choose a resume file",
            type=["pdf", "docx"],
            help="Supports PDF and DOCX files with selectable (non-scanned) text.",
            label_visibility="collapsed",
        )

        if uploaded_file is not None:
            st.markdown("---")
            st.markdown(f"**📄** `{uploaded_file.name}`")
            st.markdown(f"**Size:** {format_file_size(uploaded_file.size)}")

        st.markdown("---")
        st.markdown("**🔒 100% Local & Offline**")
        st.caption(
            "All extraction runs on your machine. "
            "No data is sent to OpenAI, Gemini, Claude, or any external API."
        )
        st.markdown("**⚙️ Pipeline stages:**")
        st.caption(
            "PDF/DOCX parse → hyperlink extraction → "
            "text cleaning → section detection → "
            "contact · profiles · skills · education · experience"
        )

    # ── Page heading ─────────────────────────────────────────────────────────
    st.markdown(
        "<div class='app-header'>"
        "<span style='font-size:1.7rem'>📄</span>"
        "<span class='app-title'>Resume Information Extractor</span>"
        "</div>"
        "<div class='app-subtitle'>"
        "Structured candidate data from PDF &amp; DOCX resumes — "
        "100% local, deterministic, rule-based."
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<span class='privacy-badge'>🛡️ No LLM · No GenAI API · No network requests</span>",
        unsafe_allow_html=True,
    )

    # ── Empty state ───────────────────────────────────────────────────────────
    if uploaded_file is None:
        st.markdown(
            """
            <div class='empty-card'>
                <h3>Upload a resume to get started</h3>
                <p>Drag and drop or browse for a <strong>PDF</strong> or
                   <strong>DOCX</strong> file using the sidebar panel.</p>
                <div class='empty-features'>
                    <span>✅ Name · Email · Phone</span>
                    <span>✅ LinkedIn · GitHub</span>
                    <span>✅ Skills (200+ vocabulary)</span>
                    <span>✅ Education history</span>
                    <span>✅ Work experience</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # ── Extraction button & session state ─────────────────────────────────────
    file_key = f"{uploaded_file.name}_{uploaded_file.size}"

    if (
        "current_file_key" not in st.session_state
        or st.session_state["current_file_key"] != file_key
    ):
        st.session_state["current_file_key"] = file_key
        st.session_state["extraction_result"] = None
        st.session_state["extraction_error"] = None
        st.session_state.pop("auto_extracted", None)

    col_btn, _ = st.columns([1, 5])
    with col_btn:
        extract_clicked = st.button(
            "🚀 Extract",
            type="primary",
            use_container_width=True,
        )

    if extract_clicked or st.session_state.get("extraction_result") is None:
        if extract_clicked or "auto_extracted" not in st.session_state:
            with st.spinner("Running extraction pipeline…"):
                try:
                    result = extract_resume(
                        uploaded_file,
                        filename=uploaded_file.name,
                    )
                    st.session_state["extraction_result"] = result
                    st.session_state["extraction_error"] = None
                    st.session_state["auto_extracted"] = True
                except ParserError as err:
                    st.session_state["extraction_error"] = f"Parse error: {err}"
                    st.session_state["extraction_result"] = None
                except Exception as err:
                    st.session_state["extraction_error"] = (
                        f"Unexpected error during extraction: {err}"
                    )
                    st.session_state["extraction_result"] = None

    # ── Error display ─────────────────────────────────────────────────────────
    if st.session_state.get("extraction_error"):
        st.error(st.session_state["extraction_error"])
        return

    # ── Results ───────────────────────────────────────────────────────────────
    result: dict[str, Any] | None = st.session_state.get("extraction_result")
    if not result:
        return

    st.success("✅ Extraction complete.")

    tab_dashboard, tab_json = st.tabs(["📊 Dashboard", "🔍 JSON / Export"])

    with tab_dashboard:
        render_contact_section(result)
        render_profiles_section(result)
        render_skills_section(result.get("skills", []))

        st.markdown("<div class='section-divider'></div>", unsafe_allow_html=True)

        col_edu, col_exp = st.columns(2)
        with col_edu:
            render_education_section(result.get("education", []))
        with col_exp:
            render_experience_section(result.get("experience", []))

    with tab_json:
        st.markdown("#### 📄 Full JSON Output")

        json_str = json.dumps(result, indent=2)

        st.download_button(
            label="📥 Download  resume_extracted.json",
            data=json_str,
            file_name="resume_extracted.json",
            mime="application/json",
            type="primary",
        )

        st.code(json_str, language="json")


if __name__ == "__main__":
    main()
