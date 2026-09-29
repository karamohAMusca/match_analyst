#!/usr/bin/env python3
"""verify.py - protects the observable behaviour during a refactoring.

A refactoring must not change what the program prints. This script captures the output of a
command and compares it with a baseline saved before the refactoring.

Typical use, from the project root (no API key needed):

    # 1) BEFORE the refactoring: save the baseline
    python -m scripts.verify --save --cmd "python -m scripts.eval_retrieval --offline --no-save" --baseline .cache/verify_retrieval.txt

    # 2) AFTER every step of the refactoring: check that the output did not change
    python -m scripts.verify --check --cmd "python -m scripts.eval_retrieval --offline --no-save" --baseline .cache/verify_retrieval.txt

The command must print the same text at every run: `eval_retrieval --offline --no-save` (the
retrieval results of every configuration) and `ingest --dry-run` (the chunks of the corpus) do.
Output and baseline are read and written as UTF-8 (the default encoding of Windows cannot hold
every character the scripts print; bytes that are not UTF-8, like an error of the Windows shell,
are replaced instead of stopping the check), and the folder of the baseline is created if missing.

Exit codes:
    0  output identical to the baseline (or baseline saved)
    1  output different from the baseline (prints the diff)
    2  the program exited with an error / baseline missing
"""
import argparse
import difflib
import os
import subprocess
import sys

DEFAULT_BASELINE = "baseline_output.txt"


def run_program(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if result.returncode != 0:
        sys.stderr.write("[verify] The program exited with an error (rc=%d):\n%s\n"
                         % (result.returncode, result.stderr))
        sys.exit(2)
    return result.stdout


def save_baseline(cmd, baseline):
    output = run_program(cmd)
    os.makedirs(os.path.dirname(baseline) or ".", exist_ok=True)
    with open(baseline, "w", encoding="utf-8") as f:
        f.write(output)
    print("[verify] Baseline saved to '%s' (%d lines)."
          % (baseline, output.count("\n")))


def check_baseline(cmd, baseline):
    if not os.path.exists(baseline):
        sys.stderr.write("[verify] Baseline '%s' not found. Run --save first.\n"
                         % baseline)
        sys.exit(2)
    with open(baseline, encoding="utf-8") as f:
        expected = f.read()
    actual = run_program(cmd)
    if actual == expected:
        print("[verify] OK - output unchanged from the baseline.")
        sys.exit(0)
    diff = difflib.unified_diff(
        expected.splitlines(keepends=True),
        actual.splitlines(keepends=True),
        fromfile="baseline",
        tofile="after_refactoring",
    )
    sys.stderr.write("[verify] WARNING - the output changed:\n")
    sys.stderr.writelines(diff)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Check that a refactoring does not change the output.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save", action="store_true", help="save the baseline")
    group.add_argument("--check", action="store_true", help="compare with the baseline")
    parser.add_argument("--cmd", required=True, help="command that runs the program")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE, help="baseline file (default: %s)" % DEFAULT_BASELINE)
    args = parser.parse_args()

    if args.save:
        save_baseline(args.cmd, args.baseline)
    else:
        check_baseline(args.cmd, args.baseline)


if __name__ == "__main__":
    main()
