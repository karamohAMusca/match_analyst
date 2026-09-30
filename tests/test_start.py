"""The one-command launcher (offline): waiting for the services."""

from __future__ import annotations

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
