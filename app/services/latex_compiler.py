import asyncio
import logging
import re
import subprocess
import tempfile
from functools import partial
from pathlib import Path

from app.interfaces.base import ILatexCompiler

logger = logging.getLogger(__name__)


class LatexCompilationError(Exception):
    pass


class TectonicCompiler(ILatexCompiler):
    def __init__(self, timeout: int = 120) -> None:
        self._timeout = timeout

    # pdflatex-only primitives that tectonic does not ship / handle
    _PDFTEX_ONLY = re.compile(
        r"^\s*(?:\\input\{glyphtounicode\}|\\pdfgentounicode\s*=\s*\d+)\s*$",
        re.MULTILINE,
    )

    @staticmethod
    def _strip_fences(text: str) -> str:
        text = text.strip()
        text = re.sub(r"^```[a-zA-Z]*\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
        return text.strip()

    @classmethod
    def _strip_pdftex_only(cls, text: str) -> str:
        return cls._PDFTEX_ONLY.sub("", text)

    def _run_sync(self, latex_content: str) -> bytes:
        latex_content = self._strip_fences(latex_content)
        latex_content = self._strip_pdftex_only(latex_content)
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "resume.tex"
            tex_path.write_text(latex_content, encoding="utf-8")

            logger.debug("latex_compiler | starting tectonic | tex_len=%d", len(latex_content))

            try:
                result = subprocess.run(
                    ["tectonic", str(tex_path)],
                    cwd=tmpdir,
                    capture_output=True,
                    timeout=self._timeout,
                )
            except FileNotFoundError as exc:
                raise LatexCompilationError(
                    "tectonic is not installed or not on PATH. "
                    "Install it from https://tectonic-typesetting.github.io"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise LatexCompilationError(
                    f"Compilation timed out after {self._timeout}s"
                ) from exc

            if result.returncode != 0:
                error_text = result.stderr.decode(errors="replace").strip()
                logger.warning(
                    "latex_compiler | tectonic failed | rc=%d | stderr=%s",
                    result.returncode, error_text[:500],
                )
                raise LatexCompilationError(error_text or "tectonic exited with non-zero status")

            pdf_path = Path(tmpdir) / "resume.pdf"
            if not pdf_path.exists():
                raise LatexCompilationError("Compilation reported success but no PDF was produced")

            pdf_bytes = pdf_path.read_bytes()
            logger.debug("latex_compiler | done | pdf_size=%d bytes", len(pdf_bytes))
            return pdf_bytes

    async def compile(self, latex_content: str) -> bytes:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, partial(self._run_sync, latex_content))
