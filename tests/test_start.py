"""The one-command launcher (offline): waiting for the services."""

from __future__ import annotations

import pytest

from scripts.start import SERVICES, wait_for


def test_wait_for_stops_as_soon_as_the_service_answers():
    calls = iter([False, False, True])
    assert wait_for("Qdrant", lambda: next(calls), timeout_s=5, step_s=0)


def test_wait_for_gives_up_after_the_timeout():
    assert not wait_for("Phoenix", lambda: False, timeout_s=0.05, step_s=0.01)


def test_services_are_the_ports_of_docker_compose():
    assert SERVICES == {"Qdrant": "http://localhost:6337/healthz", "Phoenix": "http://localhost:6006"}


def test_docker_desktop_is_started_only_when_docker_does_not_answer(monkeypatch):
    import scripts.start as start
    started = []
    monkeypatch.setattr(start, "docker_running", lambda: bool(started))      # answers once started
    monkeypatch.setattr(start, "start_docker_desktop", lambda: started.append(1) or True)
    monkeypatch.setattr(start, "docker_compose", lambda *a: 1)               # stop right after Docker
    monkeypatch.setattr(start.time, "sleep", lambda s: None)
    monkeypatch.setattr("sys.argv", ["start"])
    assert start.main() == 1 and started == [1]


def test_closing_the_app_prints_the_review_of_this_session(retriever, chats_dir, monkeypatch, capsys):
    import scripts.start as start
    import src.ui.backend as backend
    from tests.fakes import ScriptedLLM

    chats_dir.mkdir()
    (chats_dir / "2026-01-01_100000.jsonl").write_text("", encoding="utf-8")   # an older chat: not reviewed
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    seen = {}

    def fake_streamlit(cmd, cwd, env):   # the app: one chat with a football and an off-topic question
        seen["env"] = env
        conversation = backend.Conversation("gpt-4o-mini", True, retriever)
        conversation.ask("Come si allena la Primavera del Chievo durante la settimana?")
        conversation.ask("Mi scrivi la ricetta della carbonara?")
        seen["chat"] = conversation.log.path.name
        raise KeyboardInterrupt        # Ctrl+C
    monkeypatch.setattr(start, "docker_running", lambda: True)
    monkeypatch.setattr(start, "docker_compose", lambda *a: 0)
    monkeypatch.setattr(start, "answers", lambda url: True)
    monkeypatch.setattr(start.subprocess, "run", fake_streamlit)
    monkeypatch.setattr("sys.argv", ["start"])
    assert start.main() == 0
    out = capsys.readouterr().out
    assert seen["env"]["LOG_CONSOLE"] == "1"                                  # the log also in the terminal
    assert f"== {seen['chat']}: 2 answers" in out and "stopped (off_topic)" in out
    assert "2026-01-01_100000" not in out and "Log completo:" in out


# ---------------------------------------------------------------- started with the wrong Python
class _Child:
    """A started process: Ctrl+C reaches the parent while it waits (the first wait), then it ends with `code`."""

    def __init__(self, code: int = 0, interrupted: bool = False) -> None:
        self.code, self.interrupted = code, interrupted

    def wait(self) -> int:
        if self.interrupted:
            self.interrupted = False
            raise KeyboardInterrupt
        return self.code


def _venv(root, parent: bool = False):
    import os
    python = (root.parent if parent else root) / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return python


def _without_the_packages(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "rank_bm25", None)     # "import rank_bm25" fails
    monkeypatch.delenv("MATCH_ANALYST_RELAUNCHED", raising=False)


def test_with_the_packages_nothing_is_relaunched(tmp_path):
    import scripts.start as start
    started = []
    assert start.use_project_venv(tmp_path, popen=lambda *a, **k: started.append(a)) is None
    assert started == []


@pytest.mark.parametrize("parent", [False, True])
def test_without_the_packages_it_starts_again_with_the_projects_venv(tmp_path, monkeypatch, capsys, parent):
    import scripts.start as start
    root = tmp_path / "project"
    root.mkdir()
    python = _venv(root, parent)                                          # the venv in the project or in the folder above
    _without_the_packages(monkeypatch)
    monkeypatch.setattr("sys.argv", ["start", "--stop"])
    started = []

    def popen(args, **kwargs):
        started.append((args, kwargs))
        return _Child(code=3, interrupted=True)                          # Ctrl+C is waited out, then the child ends

    with pytest.raises(SystemExit) as stop:
        start.use_project_venv(root, popen=popen)
    assert stop.value.code == 3                                           # the child's own exit code
    [(args, kwargs)] = started
    assert args == [str(python), "-m", "scripts.start", "--stop"] and kwargs["cwd"] == root
    assert kwargs["env"]["MATCH_ANALYST_RELAUNCHED"] == "1" and "riparto" in capsys.readouterr().out


def test_a_venv_without_the_packages_does_not_start_itself_again(tmp_path, monkeypatch):
    import scripts.start as start
    _venv(tmp_path)
    _without_the_packages(monkeypatch)
    monkeypatch.setenv("MATCH_ANALYST_RELAUNCHED", "1")                   # this is the child
    started = []
    with pytest.raises(SystemExit) as stop:
        start.use_project_venv(tmp_path, popen=lambda *a, **k: started.append(a))
    assert started == [] and "pip install -r requirements.txt" in str(stop.value)


def test_without_any_venv_it_says_what_to_do(tmp_path, monkeypatch):
    import scripts.start as start
    root = tmp_path / "project"
    root.mkdir()
    _without_the_packages(monkeypatch)
    with pytest.raises(SystemExit) as stop:
        start.use_project_venv(root, popen=lambda *a, **k: pytest.fail("nothing to start"))
    assert "Mancano i pacchetti del progetto" in str(stop.value)
