"""Check that a change did not alter what a command prints.

A command's output is saved once as a baseline and compared with a new run after every step of a refactoring:

    python -m scripts.verify --save  --cmd "python -m scripts.eval_retrieval --offline --no-save" --baseline .cache/verify_retrieval.txt
    python -m scripts.verify --check --cmd "python -m scripts.eval_retrieval --offline --no-save" --baseline .cache/verify_retrieval.txt

Only a command that prints the same text every time can be checked: `eval_retrieval --offline --no-save` (the
retrieval results) and `ingest --dry-run` (the chunks) do, and need no API key. The baseline is the command's
standard output as UTF-8, bytes that are not UTF-8 replaced; its folder is created when missing.

Exit code: 0 the output is the baseline (or the baseline was saved), 1 it differs (the diff is printed),
2 the command failed or the baseline does not exist.
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_BASELINE = Path("baseline_output.txt")
SAME, DIFFERENT, BROKEN = 0, 1, 2


class CommandFailed(Exception):
    """The command exited with an error: its output cannot be compared."""


def capture(command: str) -> str:
    """The standard output of a shell command, as UTF-8 text."""
    done = subprocess.run(command, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if done.returncode:
        raise CommandFailed(f"the command exited with code {done.returncode}:\n{done.stderr}")
    return done.stdout


def save_baseline(command: str, baseline: Path) -> int:
    """Run the command and keep its output as the baseline."""
    baseline = Path(baseline)
    try:
        output = capture(command)
    except CommandFailed as failure:
        print(f"[verify] {failure}", file=sys.stderr)
        return BROKEN
    baseline.parent.mkdir(parents=True, exist_ok=True)
    baseline.write_text(output, encoding="utf-8", newline="")
    print(f"[verify] Baseline saved to '{baseline}' ({len(output.splitlines())} lines).")
    return SAME


def check_baseline(command: str, baseline: Path) -> int:
    """Run the command again and compare its output with the baseline."""
    baseline = Path(baseline)
    if not baseline.is_file():
        print(f"[verify] Baseline '{baseline}' not found: run --save first.", file=sys.stderr)
        return BROKEN
    try:
        now = capture(command)
    except CommandFailed as failure:
        print(f"[verify] {failure}", file=sys.stderr)
        return BROKEN
    before = baseline.read_text(encoding="utf-8", errors="replace")
    if now == before:
        print("[verify] OK - output unchanged from the baseline.")
        return SAME
    print("[verify] The output changed:", file=sys.stderr)
    sys.stderr.writelines(difflib.unified_diff(before.splitlines(keepends=True), now.splitlines(keepends=True),
                                               fromfile="baseline", tofile="now"))
    return DIFFERENT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Save the output of a command, then check it did not change.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--save", action="store_true", help="save the output as the baseline")
    mode.add_argument("--check", action="store_true", help="compare the output with the baseline")
    parser.add_argument("--cmd", required=True, help="the command to run")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help=f"baseline file (default: {DEFAULT_BASELINE})")
    args = parser.parse_args(argv)
    return (save_baseline if args.save else check_baseline)(args.cmd, args.baseline)


if __name__ == "__main__":
    raise SystemExit(main())
