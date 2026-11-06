"""Secrets and contacts hidden (src/guardrails/redact.py), offline: what is hidden, what is not, and that the
question is masked before the model, the chat's file, the traces and the log; the saved chats kept for a limited
time (scripts/prune_chats.py)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime

import pytest

from scripts import prune_chats
from src.agent.analyst_agent import MatchAnalyst
from src.core.config import GOLD_SET_PATH, PROJECT_ROOT
from src.corpus.cards import load_cards
from src.guardrails.redact import redact, redact_all
from src.observability import logs
from src.ui.chat_log import ChatLog, load_chat
from tests.fakes import ScriptedLLM

KEY = "sk-proj-AbCdEf1234567890GhIjKlMn"
QUESTION = f"Come difendo un 1-0 negli ultimi minuti? La mia chiave è {KEY}, scrivimi a mister@esempio.it"


@pytest.mark.parametrize("text, kind", [
    (f"chiave {KEY} non va", "key"),
    ("OPENAI_API_KEY=sk-abcdefghijklmnop1234", "key"),
    ("api_key: 'abc123def456'", "key"),
    ("password=Segreta!2024", "key"),
    ("Authorization: Bearer abcdefghijklmnopqrstuvwx", "key"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop", "key"),
    ("ghp_abcdefghijklmnopqrstuvwxyz0123", "key"),
    ("AKIAABCDEFGHIJKLMNOP", "key"),
    ("scrivi a mario.rossi@example.it", "email"),
    ("il preparatore: 347 123 4567", "phone"),
    ("il preparatore: 3471234567", "phone"),
    ("dalla Spagna: +34 612 345 678", "phone"),
    ("IBAN IT60 X054 2811 1010 0000 0123 456", "iban"),
    ("IT60X0542811101000000123456", "iban"),
    ("codice fiscale RSSMRA85T10A562S", "tax_code"),
])
def test_a_secret_or_a_contact_is_hidden(text, kind):
    hidden, kinds = redact(text)
    assert kinds == [kind] and "nascost" in hidden
    assert redact(hidden) == (hidden, [])                       # nothing left: idempotent


def test_football_is_not_touched():
    text = ("4-3-3 contro 3-5-2, 1-0 al 73', stagione 2023-2024, finale del 2022-12-18, rev. 1374029048, 60.2% di "
            "possesso, 320 metri, 345 passaggi, il token di squadra, la password del wifi, Calhanoglu e Barella, "
            "[case_2022_wc_final_argentina_france, p. 4] (Spalla, pp. 45-46)")
    assert redact(text) == (text, [])


def test_the_cards_the_gold_set_and_the_saved_answers_have_nothing_to_hide():
    # so the measured answers, the indexed cards and the gold questions are the same as before
    texts = [card.body for card in load_cards()]
    texts += [q["question"] for q in json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))["questions"]]
    for path in sorted((PROJECT_ROOT / "eval" / "runs").glob("*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        rows = run.get("rows") or run.get("results") or []
        texts += [r.get("answer", "") for r in rows if isinstance(r, dict)]
    assert len(texts) > 300
    assert [t[:80] for t in texts if redact(t)[1]] == []


def test_redact_all_walks_what_json_holds():
    value = {"q": f"chiave {KEY}", "n": 3, "turns": [{"text": "mister@esempio.it"}, None, ("ok",)]}
    assert redact_all(value) == {"q": "chiave [chiave nascosta]", "n": 3,
                                 "turns": [{"text": "[email nascosta]"}, None, ["ok"]]}


# ---------------------------------------------------------------- where it is applied
def test_the_model_never_sees_the_key_and_the_coach_is_told(retriever):
    llm = ScriptedLLM()
    chat = MatchAnalyst(client=llm, retriever=retriever, stateless=False)
    chat.analyze(QUESTION)
    sent = json.dumps([turn.to_dict() for turn in chat.agent._memory.memory] + chat.last_turns, ensure_ascii=False)
    assert KEY not in sent and "mister@esempio.it" not in sent and "[chiave nascosta]" in sent
    assert chat.last_guard["redacted"] == ["key", "email"]
    assert chat.guard_note.startswith("Privacy: nascosto dalla domanda prima di inviarla al modello: una chiave, "
                                      "un indirizzo email.")


def test_with_the_guardrails_off_the_key_is_hidden_too(retriever):
    chat = MatchAnalyst(client=ScriptedLLM(), retriever=retriever, guardrails=False, stateless=False)
    chat.analyze(QUESTION)
    assert KEY not in json.dumps([t.to_dict() for t in chat.agent._memory.memory], ensure_ascii=False)


def test_a_question_with_nothing_to_hide_has_no_privacy_note(retriever):
    chat = MatchAnalyst(client=ScriptedLLM(), retriever=retriever)
    chat.analyze("Come difendo un 1-0 negli ultimi minuti?")
    assert "redacted" not in chat.last_guard and not (chat.guard_note or "").startswith("Privacy")


def test_the_chat_file_holds_no_key_even_in_the_question_as_typed(tmp_path):
    log = ChatLog(folder=tmp_path, started=datetime(2026, 11, 6, 15, 0, 0))
    log.append(QUESTION, {"role": "assistant", "content": f"Ok {KEY}", "guard": {"note": "mister@esempio.it"}},
               [{"text": QUESTION}])
    saved = log.path.read_text(encoding="utf-8")
    assert KEY not in saved and "mister@esempio.it" not in saved
    assert load_chat(log.path)[0]["question"].startswith("Come difendo un 1-0 negli ultimi minuti?")


def test_the_trace_and_the_log_hold_no_key(tmp_path, monkeypatch):
    from src.observability import tracing

    class Recorder:
        def __init__(self):
            self.attributes = {}

        def set_attribute(self, key, value):
            self.attributes[key] = value

    span = Recorder()
    tracing.set_output(span, f"answer with {KEY}")
    assert KEY not in span.attributes["output.value"]

    logger = logging.getLogger("src.test_redact")
    for handler in list(logging.getLogger("src").handlers):
        if handler.get_name() == logs.FILE_HANDLER:
            monkeypatch.setattr(logging.getLogger("src"), "handlers",
                                [h for h in logging.getLogger("src").handlers if h is not handler])
    path = logs.setup_logging("INFO", folder=tmp_path)
    try:
        logger.warning("search failed for %s", QUESTION)
        for handler in logging.getLogger("src").handlers:
            handler.flush()
        written = path.read_text(encoding="utf-8")
        assert "search failed for" in written and KEY not in written and "mister@esempio.it" not in written
    finally:
        for handler in [h for h in logging.getLogger("src").handlers if getattr(h, "baseFilename", "") == str(path)]:
            logging.getLogger("src").removeHandler(handler)
            handler.close()


# ---------------------------------------------------------------- how long the chats are kept
def make_chats(folder):
    names = ["2026-09-01_100000.jsonl", "2026-10-20_100000.jsonl", "2026-11-05_100000.jsonl", "senza-data.jsonl"]
    for name in names:
        (folder / name).write_text("{}\n", encoding="utf-8")
    old = datetime(2026, 1, 1).timestamp()
    os.utime(folder / "senza-data.jsonl", (old, old))
    return names


def test_the_chats_older_than_the_limit_are_found_by_their_start(tmp_path):
    make_chats(tmp_path)
    now = datetime(2026, 11, 6, 12, 0, 0)
    assert [p.name for p in prune_chats.old_chats(tmp_path, 30, now)] == ["senza-data.jsonl", "2026-09-01_100000.jsonl"]
    assert [p.name for p in prune_chats.old_chats(tmp_path, 10, now)][-1] == "2026-10-20_100000.jsonl"


def test_without_delete_nothing_is_deleted(tmp_path, capsys):
    names = make_chats(tmp_path)
    assert prune_chats.main(["--folder", str(tmp_path), "--days", "30"]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(names)
    assert "Nothing deleted: add --delete" in capsys.readouterr().out


def test_with_delete_only_the_old_chats_go(tmp_path):
    make_chats(tmp_path)
    (tmp_path / "notes.txt").write_text("not a chat", encoding="utf-8")
    assert prune_chats.main(["--folder", str(tmp_path), "--days", "0", "--delete"]) == 0
    assert sorted(p.name for p in tmp_path.iterdir()) == ["notes.txt"]


def test_no_chats_folder_is_not_an_error(tmp_path, capsys):
    assert prune_chats.main(["--folder", str(tmp_path / "missing")]) == 0
    assert "No saved chats" in capsys.readouterr().out
