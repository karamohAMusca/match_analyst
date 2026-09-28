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
