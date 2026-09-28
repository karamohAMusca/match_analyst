"""Start everything with one command: Qdrant and Phoenix (Docker), then the Streamlit app.

    python -m scripts.start            # services up, wait until they answer, open the app
    python -m scripts.start --stop     # stop Qdrant and Phoenix (the index and the traces are kept)

If Docker is not running, Docker Desktop is started (Windows: its standard install path; macOS:
`open -a Docker`) and the script waits for it. Ctrl+C stops the app; Qdrant and Phoenix keep
running for the next start (stop them with --stop).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable

from src.core.config import PROJECT_ROOT

SERVICES = {"Qdrant": "http://localhost:6337/healthz", "Phoenix": "http://localhost:6006"}
APP_URL = "http://localhost:8501"
DOCKER_DESKTOP_WINDOWS = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                                      "Docker", "Docker", "Docker Desktop.exe")


def docker_running() -> bool:
    """True if the Docker engine answers (`docker info`)."""
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def start_docker_desktop() -> bool:
    """Launch Docker Desktop; False if it cannot be found on this system."""
    if sys.platform == "win32":
        if not os.path.exists(DOCKER_DESKTOP_WINDOWS):
            return False
        subprocess.Popen([DOCKER_DESKTOP_WINDOWS])
        return True
    if sys.platform == "darwin":
        return subprocess.run(["open", "-a", "Docker"]).returncode == 0
    return False


def answers(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except OSError:
        return False


def wait_for(name: str, ready: Callable[[], bool], timeout_s: float = 90, step_s: float = 2) -> bool:
    """Poll `ready` until it is true or `timeout_s` passes; prints the outcome."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if ready():
            print(f"  ✓ {name} pronto")
            return True
        time.sleep(step_s)
    print(f"  ✗ {name} non risponde dopo {timeout_s:.0f} s")
    return False


def docker_compose(*args: str) -> int:
    try:
        return subprocess.run(["docker", "compose", *args], cwd=PROJECT_ROOT).returncode
    except FileNotFoundError:
        print("Docker non trovato: installa e apri Docker Desktop.")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--stop", action="store_true", help="stop Qdrant and Phoenix")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    if args.stop:
        return docker_compose("down")

    if not docker_running():
        print("0/3 Docker non è attivo: avvio Docker Desktop…")
        if not start_docker_desktop():
            print("Docker Desktop non trovato: aprilo a mano e rilancia.")
            return 1
        if not wait_for("Docker", docker_running, timeout_s=150, step_s=3):
            return 1
    print("1/3 Avvio Qdrant e Phoenix (Docker)…")
    if docker_compose("up", "-d") != 0:
        print("Docker compose non è partito: Docker Desktop è aperto?")
        return 1
    print("2/3 Attendo che i servizi rispondano…")
    if not all(wait_for(name, lambda url=url: answers(url)) for name, url in SERVICES.items()):
        return 1
    print(f"3/3 Apro l'app: {APP_URL}  (tracce: http://localhost:6006)  — Ctrl+C per chiuderla")
    try:
        return subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"], cwd=PROJECT_ROOT).returncode
    except KeyboardInterrupt:
        return 0
    finally:
        print("App chiusa. Qdrant e Phoenix restano accesi: `python -m scripts.start --stop` per spegnerli.")


if __name__ == "__main__":
    sys.exit(main())
