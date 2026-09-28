"""Interactive CLI to chat with Match Analyst AI (Italian or English).

    python interactive_cli.py                      # conversation (follow-up questions work)
    python interactive_cli.py "your question"      # single question

Needs Qdrant running (docker compose up -d), the index built (python -m scripts.ingest)
and OPENAI_API_KEY in .env.
"""

import os
import sys

os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels in the chat

from src.agent.analyst_agent import MatchAnalyst  # noqa: E402

EXIT_COMMANDS = {"esci", "quit", "exit"}


def show(analyst: MatchAnalyst, question: str) -> None:
    print(analyst.analyze(question))
    if analyst.consulted_cards:
        print("\nSchede consultate: " + ", ".join(analyst.consulted_cards))


def main() -> None:
    # Windows terminals may default to a legacy code page.
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    single_question = len(sys.argv) > 1
    try:
        analyst = MatchAnalyst(stateless=single_question)
    except (ValueError, RuntimeError) as e:
        print(f"Errore di configurazione: {e}")
        return

    if single_question:
        show(analyst, " ".join(sys.argv[1:]))
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
            print(f"Errore durante l'analisi: {e}")
    print("Buon lavoro, Mister!")


if __name__ == "__main__":
    main()
