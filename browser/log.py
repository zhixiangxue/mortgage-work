"""Logging setup for the standalone viewer unit — a trimmed copy of the
desktop app's log.py so this unit keeps zero imports from the parent repo.

Every viewer calls ``setup_logging()`` once at startup and then logs through
``logging.getLogger(__name__)``. Format: ``HH:MM:SS LEVEL [module] message``.

Console + file: output also lands in a rotating ``browser/runtime.log`` so a
viewer started detached (serve.sh) keeps a trail the operator can tail.
Level defaults to INFO; set ``LOG_LEVEL=DEBUG`` for high-frequency chatter.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path

_CONFIGURED = False


def setup_logging() -> None:
    """Configure the root logger. Idempotent — safe to call from every
    viewer (and more than once)."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    # Pad level names to a fixed width so the message column lines up.
    logging.addLevelName(logging.DEBUG, "DEBUG")
    logging.addLevelName(logging.INFO, "INFO ")
    logging.addLevelName(logging.WARNING, "WARN ")
    logging.addLevelName(logging.ERROR, "ERROR")

    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        level = "INFO"

    # Windows consoles default to the ANSI codepage — force UTF-8 so a
    # stray non-ASCII message can't crash the handler.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass  # piped/odd stdout — best effort only

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)

    # Rotating file next to the viewer scripts, so a detached run started by
    # serve.sh still leaves a trail. 2 MB cap, one backup.
    try:
        log_file = Path(__file__).resolve().parent / "runtime.log"
        fh = RotatingFileHandler(str(log_file), maxBytes=2 * 1024 * 1024,
                                 backupCount=1, encoding="utf-8", errors="replace")
        fh.setFormatter(logging.Formatter(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        ))
        fh.setLevel(level)
        root.addHandler(fh)
    except Exception:
        pass  # disk full / permission weird — the console handler still works

    # Third-party noise: we only care when these actually fail.
    for noisy in ("httpx", "httpcore", "uvicorn"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
