import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_DIR = Path(__file__).parent.parent.parent / "logs"
_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def _add_file_handler(logger_name: str, filename: str) -> None:
    _LOG_DIR.mkdir(exist_ok=True)
    handler = RotatingFileHandler(
        _LOG_DIR / filename,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_FMT))
    log = logging.getLogger(logger_name)
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)


def setup_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format=_FMT,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    _add_file_handler("app.agents.top_n_selector", "top_n_selector.log")

    if debug:
        from langchain_core.globals import set_debug
        set_debug(True)
        logging.getLogger(__name__).info("LangChain debug mode enabled")
