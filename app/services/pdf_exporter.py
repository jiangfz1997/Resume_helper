import asyncio
import logging
import sys
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="playwright")

# Uniform scale applied only during PDF export to compensate for the slight
# size difference between browser preview rendering and Playwright/print DPI.
_PDF_SCALE: float = 0.95


def _render_pdf_sync(html: str) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.set_viewport_size({"width": 794, "height": 1123})
            page.emulate_media(media="screen")
            page.set_content(html, wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            page.add_style_tag(content=f"""
                @page {{ size: A4; margin: 0; }}
                html, body {{
                    width: 210mm !important;
                    margin: 0 !important;
                    padding: 0 !important;
                    box-sizing: border-box !important;
                }}
                .page {{
                    zoom: {_PDF_SCALE};
                }}
            """)
            pdf_bytes = page.pdf(
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            browser.close()
        logger.debug("pdf_exporter | done | bytes=%d", len(pdf_bytes))
        return pdf_bytes
    except Exception:
        logger.exception("pdf_exporter | _render_pdf_sync failed")
        raise


class PdfExporter:
    async def export(self, html: str) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _render_pdf_sync, html)
