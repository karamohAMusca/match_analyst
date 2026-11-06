"""scripts/verify.py (offline): the baseline is saved, an unchanged output passes, a changed one fails."""

from __future__ import annotations

import sys

from scripts.verify import BROKEN, DIFFERENT, SAME, check_baseline, main, save_baseline

PYTHON = f'"{sys.executable}"'
PRINTS_E_GRAVE = f'{PYTHON} -c "print(chr(232))"'    # "è": UTF-8 on Windows too


def test_unchanged_output_passes_and_a_change_is_shown(tmp_path, capsys):
    baseline = tmp_path / "baselines" / "out.txt"                # the folder does not exist yet
    assert save_baseline(PRINTS_E_GRAVE, baseline) == SAME
    assert baseline.read_text(encoding="utf-8") == "è\n"
    assert check_baseline(PRINTS_E_GRAVE, baseline) == SAME
    assert check_baseline(f'{PYTHON} -c "print(1)"', baseline) == DIFFERENT
    err = capsys.readouterr().err
    assert "The output changed" in err and "-è" in err and "+1" in err   # the diff is shown


def test_missing_baseline_and_failing_command_are_broken(tmp_path):
    assert check_baseline(f'{PYTHON} -c "print(1)"', tmp_path / "none.txt") == BROKEN
    assert save_baseline(f'{PYTHON} -c "import sys; sys.exit(3)"', tmp_path / "b.txt") == BROKEN
    assert not (tmp_path / "b.txt").exists()                      # a failed command leaves no baseline


def test_command_line_saves_then_checks(tmp_path, capsys):
    baseline = str(tmp_path / "out.txt")
    assert main(["--save", "--cmd", PRINTS_E_GRAVE, "--baseline", baseline]) == SAME
    assert main(["--check", "--cmd", PRINTS_E_GRAVE, "--baseline", baseline]) == SAME
    assert "unchanged" in capsys.readouterr().out
