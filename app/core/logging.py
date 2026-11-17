import logging
import sys


def _preparar_stream(stream):
    """Evita UnicodeEncodeError en consolas Windows (cp1252) con logs UTF-8."""
    try:
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError, OSError):
        pass


def setup_logging() -> logging.Logger:
    _preparar_stream(sys.stdout)
    _preparar_stream(sys.stderr)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d) - %(message)s",
    )
    return logging.getLogger(__name__)
