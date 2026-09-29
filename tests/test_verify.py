"""scripts/verify.py (offline): the baseline is saved, an unchanged output passes, a changed one fails."""

from __future__ import annotations

import sys

import pytest

from scripts.verify import check_baseline, save_baseline

PYTHON = f'"{sys.executable}"'


def exit_code(call, *args) -> int:
    with pytest.raises(SystemExit) as stop:
        call(*args)
    return stop.value.code


def test_unchanged_output_passes_and_a_change_is_shown(tmp_path, capsys):
    baseline = str(tmp_path / "baselines" / "out.txt")          # the folder does not exist yet
    save_baseline(f'{PYTHON} -c "print(chr(232))"', baseline)     # "è": UTF-8 on Windows too
    assert open(baseline, encoding="utf-8").read() == "è\n"
    assert exit_code(check_baseline, f'{PYTHON} -c "print(chr(232))"', baseline) == 0
    assert exit_code(check_baseline, f'{PYTHON} -c "print(1)"', baseline) == 1
    err = capsys.readouterr().err
    assert "the output changed" in err and "-è" in err and "+1" in err   # the diff is shown


def test_missing_baseline_and_failing_program_stop_with_code_2(tmp_path):
    assert exit_code(check_baseline, f'{PYTHON} -c "print(1)"', str(tmp_path / "none.txt")) == 2
    assert exit_code(save_baseline, f'{PYTHON} -c "import sys; sys.exit(3)"', str(tmp_path / "b.txt")) == 2
