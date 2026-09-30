"""Interactive CLI to chat with Match Analyst AI (Italian or English).

    python interactive_cli.py                      # conversation (follow-up questions work)
    python interactive_cli.py "your question"      # single question

Needs Qdrant running (docker compose up -d), the index built (python -m scripts.ingest)
and OPENAI_API_KEY in .env. With Phoenix running (same docker compose), every question is
also a trace at http://localhost:6006.
"""

import logging
import os
import sys

os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels in the chat

from src.agent.analyst_agent import MatchAnalyst  # noqa: E402
from src.core.config import load_settings  # noqa: E402
from src.observability.logs import setup_logging  # noqa: E402
from src.observability.tracing import flush, setup_tracing  # noqa: E402

EXIT_COMMANDS = {"esci", "quit", "exit"}


def show(analyst: MatchAnalyst, question: str) -> None:
    print(analyst.analyze(question))
    if analyst.consulted_cards:
        print("\nSchede consultate: " + ", ".join(analyst.consulted_cards))
    if analyst.guard_note:   # what the guardrails did: never silent
        print(f"\n[{analyst.guard_note}]")


def main() -> None:
    # Windows terminals may default to a legacy code page.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    settings = load_settings()
    setup_logging(settings.log_level)
    print(setup_tracing(settings.phoenix_endpoint, settings.phoenix_project))
    single_question = len(sys.argv) > 1
    try:
        analyst = MatchAnalyst(stateless=single_question)
    except (ValueError, RuntimeError) as e:
        logging.getLogger("src.cli").exception("assistant not ready")
        print(f"Errore di configurazione: {e}")
        return

    if single_question:
        show(analyst, " ".join(sys.argv[1:]))
        flush()   # send the trace before the program ends
        return

    print("MATCH ANALYST AI - descrivi la tua squadra, l'avversario o la situazione di gara.")
    print("Scrivi 'esci' per terminare.")
    while True:
        try:
            user_input = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            break
        if not user_input:
            continue
        if user_input.lower() in EXIT_COMMANDS:
            break
        try:
            show(analyst, user_input)
        except Exception as e:  # keep the session alive on API/network errors
            logging.getLogger("src.cli").exception("question failed")
            print(f"Errore durante l'analisi: {e}")
    flush()
    print("Buon lavoro, Mister!")


if __name__ == "__main__":
    main()
