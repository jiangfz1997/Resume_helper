import html
from typing import Final

from app.models.data_models import ContactInfo, LayoutSettings, TailoredResumeDraft

_FONT_SIZE_PX: Final[dict[int, int]] = {1: 10, 2: 11, 3: 12, 4: 13, 5: 14}
_SECTION_GAP_PX: Final[dict[int, int]] = {1: 6, 2: 10, 3: 14, 4: 18, 5: 24}
_ITEM_GAP_PX: Final[dict[int, int]] = {1: 2, 2: 4, 3: 6, 4: 10, 5: 14}
_LINE_HEIGHT: Final[dict[int, float]] = {1: 1.15, 2: 1.25, 3: 1.35, 4: 1.45, 5: 1.55}

_SAFE_FONTS: Final[set[str]] = {
    "Georgia", "Times New Roman", "Arial", "Helvetica", "Calibri", "Garamond",
}


def _css_vars(s: LayoutSettings) -> str:
    factor = 0.6 if s.compact_mode else 1.0
    fs = _FONT_SIZE_PX[s.font_size]
    sg = round(_SECTION_GAP_PX[s.section_gap] * factor)
    ig = round(_ITEM_GAP_PX[s.item_gap] * factor)
    lh = _LINE_HEIGHT[s.line_height]
    font = s.font_family if s.font_family in _SAFE_FONTS else "Georgia"
    accent = s.accent_color if s.accent_color.startswith("#") else "#1a1a1a"
    return (
        f"--font-family: '{font}', serif;"
        f"--font-size-base: {fs}px;"
        f"--section-gap: {sg}px;"
        f"--item-gap: {ig}px;"
        f"--line-height: {lh};"
        f"--margin-h: {s.margin_h}mm;"
        f"--margin-v: {s.margin_v}mm;"
        f"--accent: {accent};"
    )


_CSS = """
@page { size: A4; margin: 0; }
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: var(--font-family);
  font-size: var(--font-size-base);
  line-height: var(--line-height);
  color: #111;
  background: #fff;
}
.page {
  width: 210mm;
  padding: var(--margin-v) var(--margin-h);
  margin: 0 auto;
  background: #fff;
}
.resume-header {
  text-align: center;
  margin-bottom: var(--section-gap);
  padding-bottom: 6px;
  border-bottom: 1.5px solid var(--accent);
}
.resume-name {
  font-size: calc(var(--font-size-base) * 1.8);
  font-weight: 700;
  letter-spacing: 2px;
  text-transform: uppercase;
  color: var(--accent);
}
.section {
  margin-bottom: var(--section-gap);
}
.section-title {
  font-size: calc(var(--font-size-base) * 1.0);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--accent);
  border-bottom: 0.75px solid #bbb;
  padding-bottom: 2px;
  margin-bottom: calc(var(--item-gap) * 1.2);
}
.item {
  margin-bottom: var(--item-gap);
}
.item-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.item-org { font-weight: 600; }
.item-date {
  font-size: calc(var(--font-size-base) * 0.88);
  color: #555;
  flex-shrink: 0;
  margin-left: 8px;
}
.item-sub {
  font-style: italic;
  color: #333;
  font-size: calc(var(--font-size-base) * 0.95);
}
ul.bullets {
  margin: calc(var(--item-gap) * 0.4) 0 0 0;
  padding-left: 15px;
}
ul.bullets li { margin-bottom: 1px; }
.skill-row { margin-bottom: 3px; }
.skill-cat { font-weight: 600; }
.summary-text { text-align: justify; }
[data-hl].hl-active {
  outline: 2px solid rgba(99,179,237,0.85);
  outline-offset: 2px;
  background: rgba(99,179,237,0.10);
  border-radius: 2px;
}
.contact-line {
  font-size: calc(var(--font-size-base) * 0.85);
  color: #444;
  margin-top: 4px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 4px 10px;
}
.contact-line a { color: #444; text-decoration: none; }
.contact-line a:hover { text-decoration: underline; }
"""


def _e(text: str) -> str:
    return html.escape(text or "")


def _contact_html(ci: ContactInfo | None) -> str:
    if ci is None:
        return ""
    items: list[str] = []
    if ci.email:
        items.append(f'<a href="mailto:{_e(ci.email)}">{_e(ci.email)}</a>')
    if ci.phone:
        items.append(_e(ci.phone))
    if ci.location:
        items.append(_e(ci.location))
    if ci.linkedin:
        label = ci.linkedin.rstrip("/").rsplit("/", 1)[-1] or "LinkedIn"
        items.append(f'<a href="{_e(ci.linkedin)}" target="_blank">LinkedIn/{_e(label)}</a>')
    if ci.github:
        label = ci.github.rstrip("/").rsplit("/", 1)[-1] or "GitHub"
        items.append(f'<a href="{_e(ci.github)}" target="_blank">GitHub/{_e(label)}</a>')
    if ci.website:
        items.append(f'<a href="{_e(ci.website)}" target="_blank">{_e(ci.website)}</a>')
    if not items:
        return ""
    return '<div class="contact-line">' + "".join(f"<span>{it}</span>" for it in items) + "</div>"


def _date_range(start: str, end: str | None) -> str:
    return f"{_e(start)} – {_e(end) if end else 'Present'}"


class ResumeRenderer:
    def render(
        self,
        draft: TailoredResumeDraft,
        settings: LayoutSettings,
        full_name: str = "",
    ) -> str:
        parts: list[str] = []

        # header
        name_html = f'<div class="resume-name">{_e(full_name or "Your Name")}</div>'
        contact_html = _contact_html(draft.contact_info)
        parts.append(f'<div class="resume-header">{name_html}{contact_html}</div>')

        # summary
        if draft.show_summary and draft.summary.strip():
            parts.append(
                '<div class="section">'
                '<div class="section-title">Summary</div>'
                f'<p class="summary-text" data-hl="summary">{_e(draft.summary)}</p>'
                "</div>"
            )

        # experience
        if draft.show_experiences and draft.experiences:
            items = []
            for ei, exp in enumerate(draft.experiences):
                bullets = "".join(
                    f'<li data-hl="exp-{ei}-b-{bi}">{_e(b.text)}</li>'
                    for bi, b in enumerate(exp.bullets)
                    if b.text.strip()
                )
                bullets_html = f'<ul class="bullets">{bullets}</ul>' if bullets else ""
                items.append(
                    f'<div class="item" data-hl="exp-{ei}">'
                    '<div class="item-row">'
                    f'<span class="item-org">{_e(exp.company)}</span>'
                    f'<span class="item-date">{_date_range(exp.start_date, exp.end_date)}</span>'
                    "</div>"
                    f'<div class="item-sub">{_e(exp.title)}'
                    + (f' · {_e(exp.location)}' if exp.location else "")
                    + "</div>"
                    + bullets_html
                    + "</div>"
                )
            parts.append(
                '<div class="section">'
                '<div class="section-title">Experience</div>'
                + "".join(items)
                + "</div>"
            )

        # education
        if draft.show_education and draft.education:
            items = []
            for edu in draft.education:
                deg = " ".join(filter(None, [edu.degree, edu.field_of_study]))
                gpa_html = f" · GPA {_e(edu.gpa)}" if edu.gpa else ""
                items.append(
                    '<div class="item">'
                    '<div class="item-row">'
                    f'<span class="item-org">{_e(edu.institution)}</span>'
                    f'<span class="item-date">{_date_range(edu.start_date, edu.end_date)}</span>'
                    "</div>"
                    f'<div class="item-sub">{_e(deg)}{gpa_html}</div>'
                    "</div>"
                )
            parts.append(
                '<div class="section">'
                '<div class="section-title">Education</div>'
                + "".join(items)
                + "</div>"
            )

        # projects
        if draft.show_projects and draft.projects:
            items = []
            for pi, proj in enumerate(draft.projects):
                bullets = "".join(
                    f'<li data-hl="proj-{pi}-b-{bi}">{_e(b.text)}</li>'
                    for bi, b in enumerate(proj.bullets)
                    if b.text.strip()
                )
                bullets_html = f'<ul class="bullets">{bullets}</ul>' if bullets else ""
                tech = (
                    f'<div class="item-sub">{_e(", ".join(proj.tech_stack))}</div>'
                    if proj.tech_stack
                    else ""
                )
                items.append(
                    f'<div class="item" data-hl="proj-{pi}">'
                    f'<div class="item-org">{_e(proj.name)}</div>'
                    f'<div class="item-sub">{_e(proj.description)}</div>'
                    + tech
                    + bullets_html
                    + "</div>"
                )
            parts.append(
                '<div class="section">'
                '<div class="section-title">Projects</div>'
                + "".join(items)
                + "</div>"
            )

        # skills
        if draft.show_skills and draft.skills:
            by_cat: dict[str, list[str]] = {}
            for sk in draft.skills:
                by_cat.setdefault(sk.category, []).append(sk.name)
            rows = "".join(
                f'<div class="skill-row"><span class="skill-cat">{_e(cat)}:</span> {_e(", ".join(names))}</div>'
                for cat, names in by_cat.items()
            )
            parts.append(
                '<div class="section">'
                '<div class="section-title">Skills</div>'
                + rows
                + "</div>"
            )

        # custom sections
        for cs in draft.custom_sections:
            if not cs.title.strip():
                continue
            bullets = "".join(f"<li>{_e(b)}</li>" for b in cs.bullets if b.strip())
            bullets_html = f'<ul class="bullets">{bullets}</ul>' if bullets else ""
            parts.append(
                '<div class="section">'
                f'<div class="section-title">{_e(cs.title)}</div>'
                + bullets_html
                + "</div>"
            )

        body = "\n".join(parts)
        css_vars = _css_vars(settings)

        return (
            "<!DOCTYPE html>"
            "<html><head>"
            '<meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<style>:root{{{css_vars}}}{_CSS}</style>"
            "</head><body>"
            f'<div class="page preview-page">{body}</div>'
            "</body></html>"
        )
