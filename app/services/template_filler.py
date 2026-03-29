# DEPRECATED: Jinja2/LaTeX template filling replaced by HTML rendering (resume_renderer.py).
# Kept for reference. Do not use in new code.

import re

import jinja2

from app.models.data_models import TailoredResumeDraft

_LATEX_CHARS = str.maketrans(
    {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\^{}",
        "\\": r"\textbackslash{}",
    }
)


def latex_escape(value: object) -> str:
    text = str(value).translate(_LATEX_CHARS)
    # Collapse newlines: a bare newline is a space in LaTeX; a blank line is a paragraph break
    # which is illegal inside command arguments — replace both with a space.
    text = text.replace("\r\n", " ").replace("\n", " ")
    return text


def _make_env() -> jinja2.Environment:
    env = jinja2.Environment(
        variable_start_string="<<",
        variable_end_string=">>",
        block_start_string="<%",
        block_end_string="%>",
        comment_start_string="<#",
        comment_end_string="#>",
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )
    env.filters["e"] = latex_escape
    return env


_ENV = _make_env()


def build_jinja2_template(source: str, source_type: str) -> str:
    """Return a complete Jinja2 template string ready for TemplateFiller.

    - ``source_type == "global"``: source is already a complete ``.tex.j2`` — return as-is.
    - ``source_type == "user"``: source is only the LaTeX preamble (stops before
      ``\\begin{document}``).  Combine it with the default Jinja2 body so that the
      user's custom commands / packages are preserved while content injection still works.
    """
    if source_type == "global":
        return source

    from pathlib import Path
    default = (
        Path(__file__).parent.parent / "latex_templates" / "classic.tex.j2"
    ).read_text(encoding="utf-8")

    match = re.search(r"\\begin\{document\}", default)
    if match is None:
        return default

    default_body = default[match.start():]

    # Strip any \begin{document} already present in the user preamble (shouldn't happen
    # since the client splits there, but be defensive).
    user_preamble = re.split(r"\\begin\{document\}", source, maxsplit=1)[0].rstrip()

    return user_preamble + "\n" + default_body


class TemplateFiller:
    def __init__(self, template_content: str) -> None:
        self._tmpl = _ENV.from_string(template_content)

    def render(self, draft: TailoredResumeDraft) -> str:
        return self._tmpl.render(draft.model_dump())
