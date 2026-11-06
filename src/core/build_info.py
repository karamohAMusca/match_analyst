"""Which version of the system gave an answer: the configuration frozen into every saved answer and every run.

An answer, a gold run or a red team run is evidence only for the configuration that produced it: change a prompt,
a guardrail or a card and the old evidence no longer speaks for the new system. So each of them carries what it
was made with: the commit (and whether the working copy had changes not committed), a fingerprint of the prompts,
of the guardrails' code and of the corpus manifest, then, from the agent, the model, the verifier, the guardrails
on or off and the chat memory. Two answers with the same fingerprints came from the same instructions; "who decided
what" can be answered from the file. Computed once per process; no key, no network (git is asked, when present).
"""

from __future__ import annotations

import hashlib
import subprocess
from functools import lru_cache
from pathlib import Path

from src.core.config import MANIFEST_PATH, PROJECT_ROOT

PROMPTS = PROJECT_ROOT / "src" / "agent" / "prompts.py"
GUARDRAILS = PROJECT_ROOT / "src" / "guardrails"


def fingerprint(paths: list[Path]) -> str:
    """The first 12 hex digits of the SHA-256 of the files (path relative to the project and text with LF line
    endings, so it is the same on every system); "missing" when none exists."""
    digest, found = hashlib.sha256(), False
    for path in sorted(paths):
        if path.is_file():
            found = True
            name = path.relative_to(PROJECT_ROOT).as_posix() if path.is_relative_to(PROJECT_ROOT) else path.name
            digest.update(name.encode() + b"\0")
            digest.update(path.read_bytes().replace(b"\r\n", b"\n") + b"\0")
    return digest.hexdigest()[:12] if found else "missing"


def _git(*args: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(PROJECT_ROOT), *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):   # no git, or it hangs
        return None
    return done.stdout.strip() if done.returncode == 0 else None


@lru_cache(maxsize=1)
def code_version() -> dict[str, str | bool | None]:
    """The commit, whether the working copy had changes (None when git cannot say) and the fingerprints."""
    commit = _git("rev-parse", "--short=10", "HEAD")
    status = _git("status", "--porcelain", "--untracked-files=no") if commit else None
    return {"commit": commit or "unknown",
            "uncommitted_changes": None if status is None else bool(status),
            "prompts": fingerprint([PROMPTS]),
            "guardrails_code": fingerprint(list(GUARDRAILS.glob("*.py"))),
            "corpus": fingerprint([MANIFEST_PATH])}
