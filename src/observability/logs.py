"""The log of the app and the CLI: one line per event, in `logs/match_analyst.log` (git-ignored).

What is written (INFO): a new conversation and its file in `chats/`, every question (its length,
not its text), the input guard's verdict, every search (the cards found and the time), the output
guard's problems and the rewrite, every answer (time, tokens, cost). WARNING: questions stopped,
rewrites discarded, a search or a save that failed. ERROR: exceptions, with their stack trace.
The text of the questions and answers stays in the chat's file; the search queries only at DEBUG.

Python's standard `logging` (the one datapizza uses): the handlers are attached to the `src`
logger, so only this project's modules write to them; the file is rotated at 1 MB, 5 old files
kept. Level from `LOG_LEVEL` in .env (default INFO). `console=True` also prints the lines in the
terminal (`scripts.start` asks for it, so the chat can be followed live).
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import src.core.config as config

__all__ = ["CONSOLE_HANDLER", "FILE_HANDLER", "LOG_FILE", "setup_logging"]

LOG_FILE = "match_analyst.log"
FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
CONSOLE_FORMAT = "[log] %(asctime)s %(levelname)-7s %(message)s"
FILE_HANDLER = "match_analyst_file"
CONSOLE_HANDLER = "match_analyst_console"


def setup_logging(level: str = "INFO", folder: Path | None = None, console: bool = False) -> Path:
    """Write the project's log to `folder` (default `logs/`), and to the terminal if `console`;
    call once at start. Returns the file."""
    logger = logging.getLogger("src")
    for handler in logger.handlers:   # Streamlit reruns the script: one handler only
        if handler.get_name() == FILE_HANDLER:
            return Path(handler.baseFilename)
    folder = folder or config.LOGS_DIR
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    handler.set_name(FILE_HANDLER)
    handler.setFormatter(logging.Formatter(FORMAT))
    logger.addHandler(handler)
    if console:
        terminal = logging.StreamHandler(sys.stderr)
        terminal.set_name(CONSOLE_HANDLER)
        terminal.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt="%H:%M:%S"))
        logger.addHandler(terminal)
    logger.setLevel(level)
    return Path(handler.baseFilename)
