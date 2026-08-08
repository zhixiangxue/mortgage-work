"""Unified logging configuration — the single place that decides what the
app's console output looks like.

Every process in the system (main app, DB viewers, agent service) calls
``setup_logging()`` once at startup and then logs through
``logging.getLogger(__name__)``. Plain ``print()`` is banned in app code —
it has no timestamp, no level, and no module attribution.

Format: ``HH:MM:SS LEVEL [module] message``, e.g.::

    09:12:03 INFO  [index.indexer] dataset ready
    09:12:04 INFO  [integration.rag] RAG upload ok · sheet.pdf · doc_id=5c7b…

Key lifecycle events carry a leading emoji so they're scannable at a glance.
The vocabulary is fixed — one event type, one emoji, never decorative use::

    📥 pull landed      📦 commit          📤 push
    ✏️ file edited       ➕ file created    🗑️ deleted
    🚚 moved/renamed    ⬆️ uploaded         ♻️ version restored
    👤 client record    🧩 skill install    🖋️ clerk started
    🧠 RAG indexing     🌐 KG ingesting     💾 memory

Emoji are plain UTF-8 characters, so writing logs to a file later is safe —
a future ``FileHandler`` only has to follow the same rule as the console
stream below: ``encoding="utf-8", errors="replace"``.

Console + file: the terminal is still the primary log viewer; a rotating
file at ``runtime.log`` feeds the in-app Console panel so the LO can watch
output without leaving the window.
Level defaults to INFO; set ``LOG_LEVEL=DEBUG`` to see high-frequency
chatter (task-status polling etc.).
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
    process (and more than once)."""
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

    # File handler — feeds the in-app Console panel. Rotates at 2 MB, keeps
    # one backup so the file never grows unbounded.
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
        # Start-of-session marker so the console panel shows a clean boundary
        logging.getLogger(__name__).info("logging to %s", log_file)
    except Exception:
        pass  # disk full / permission weird — the console handler still works

    # Third-party noise: we only care when these actually fail.
    for noisy in ("httpx", "httpcore", "uvicorn", "watchdog", "fakeredis"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
