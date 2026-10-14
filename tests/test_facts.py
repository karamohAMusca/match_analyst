"""The real case written from the card (src/guardrails/facts.py), offline: E1 and E2 of
eval/error_log.md, the agent's flow with answers written by the test, and the real-case lines of the
saved answers of real runs."""

from __future__ import annotations

import json

import pytest

from scripts.review_chats import card_texts
from src.agent.analyst_agent import MatchAnalyst
from src.core.config import PROJECT_ROOT
from src.guardrails.facts import CASE_LINE_RE, collapse_real_cases, expand_real_cases
from tests.fakes import ScriptedLLM

UEL = "case_2024_uel_final_atalanta_leverkusen"
UCL23 = "case_2023_ucl_final_city_inter"


@pytest.fixture(scope="module")
def cards():
    return card_texts()


def test_e2_swapped_roles_become_the_cards_sentence(cards):
    answer = ("- Muovete la palla [situation_uscire_dal_pressing_alto].\n\nCaso reale: nell'Europa League 2024, "
              "l'Atalanta ha sfruttato il pressing a uomo del Leverkusen per segnare due gol [" + UEL + "].")
    out = expand_real_cases(answer, ["situation_uscire_dal_pressing_alto"], cards.get)
    assert "pressing a uomo del Leverkusen" not in out
    assert ("Caso reale: Europa League 2024: il Leverkusen, pressato a uomo dall'Atalanta, perde palla in uscita"
            in out and out.endswith(f"[{UEL}]."))
    assert out.startswith("- Muovete la palla [situation_uscire_dal_pressing_alto].")   # the rest untouched


def test_e1_inter_defending_a_lead_becomes_the_cards_sentence(cards):
    answer = f"- **Caso reale:** l'Inter, nella Champions 2023, ha difeso un vantaggio [{UCL23}]."
    out = expand_real_cases(answer, ["situation_difendere_un_vantaggio"], cards.get)
    assert "ha difeso un vantaggio" not in out
    assert "nella Champions 2023 l'Inter regge un tempo" in out and "il City poi difende l'1-0" in out


def test_a_real_case_no_consulted_card_speaks_of_is_removed(cards):
    answer = "Pressate alto [coach_klopp].\nCaso reale: [case_2026_wc_final_spain_argentina]"
    assert expand_real_cases(answer, ["coach_klopp"], cards.get) == "Pressate alto [coach_klopp]."


def test_the_match_card_alone_gives_its_outcome_and_english_keeps_the_card_text(cards):
    out = expand_real_cases(f"Real case: [{UCL23}]", [UCL23], cards.get)
    assert out.startswith("Real case (card text, in Italian): Finale Champions League 2023: Manchester City 1-0 Inter.")
    assert "Il City vince la sua prima Champions League" in out


def test_a_case_line_citing_the_situation_card_is_led_back_to_its_final(cards):
    # Run agent_20260929-112013 (Q13): the model cited the situation card, not the final.
    line = ("- **Caso reale**: Nella finale del Mondiale 2026, la Spagna ha battuto l'Argentina, un 4-4-2 basso "
            "[situation_attaccare_un_blocco_basso].")
    out = expand_real_cases(line, ["situation_attaccare_un_blocco_basso"], cards.get)
    assert out.endswith("[case_2026_wc_final_spain_argentina].") and "Mondiale 2026: la Spagna batte" in out


def test_collapse_and_expand_are_stable(cards):
    consulted = ["situation_uscire_dal_pressing_alto"]
    once = expand_real_cases(f"Testo [situation_uscire_dal_pressing_alto].\nCaso reale: [{UEL}]", consulted, cards.get)
    assert expand_real_cases(once, consulted, cards.get) == once                  # writing it again changes nothing
    assert collapse_real_cases(once) == f"Testo [situation_uscire_dal_pressing_alto].\nCaso reale: [{UEL}]"


# ---------------------------------------------------------------- the agent's flow
PRESSING = "Come usciamo dal pressing alto a uomo dell'avversario?"
SWAPPED = f"Caso reale: l'Atalanta ha subito il pressing a uomo del Leverkusen [{UEL}]."


def test_the_agent_writes_the_real_case_from_the_card(retriever):
    llm = ScriptedLLM(answer=f"Muovete la palla velocemente [situation_uscire_dal_pressing_alto].\n{SWAPPED}")
    chat = MatchAnalyst(client=llm, retriever=retriever, stateless=False)
    answer = chat.analyze(PRESSING)
    assert "pressing a uomo del Leverkusen" not in answer and answer.endswith(f"[{UEL}].")
    assert "pressing a uomo dell'Atalanta" in answer or "pressato a uomo dall'Atalanta" in answer   # a card's sentence
    remembered = [b.content for t in chat.agent._memory for b in t if hasattr(b, "content")]
    assert answer in remembered                               # the next turn builds on what the coach saw


def test_the_rewrite_sees_the_real_case_as_label_and_id(retriever):
    # An invented name ("Pippo") makes the output guard ask for a rewrite: the model gets back its
    # real-case line as label and id, not the card's sentence, and the rewrite gets the card's again.
    llm = ScriptedLLM(answer=f"Muovete la palla come Pippo [situation_uscire_dal_pressing_alto].\n{SWAPPED}",
                      rewrite=f"Muovete la palla [situation_uscire_dal_pressing_alto].\nCaso reale: [{UEL}]")
    answer = MatchAnalyst(client=llm, retriever=retriever).analyze(PRESSING)
    assert f"Caso reale: [{UEL}]" in llm.rewrite_requests[0] and "a uomo del Leverkusen" not in llm.rewrite_requests[0]
    assert answer.startswith("Muovete la palla [situation_uscire_dal_pressing_alto].\nCaso reale: Europa League 2024")


# ---------------------------------------------------------------- real answers
def test_every_real_case_line_of_the_saved_answers(cards):
    """The real-case lines of the saved answers of real runs (124): a line about a final becomes the
    card's sentence ending with its id; a line about something else that cites a consulted card stays
    as written; only a line citing no card goes (and every line of the old runs that did not save
    the consulted cards)."""
    runs, outcome = PROJECT_ROOT / "eval" / "runs", {"card": 0, "kept": 0, "removed": 0}
    for path in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("questions") or data.get("rows") or []:
            for match in CASE_LINE_RE.finditer(row["answer"]):
                out = expand_real_cases(match.group(0), row.get("consulted") or [], cards.get)
                if not out:
                    outcome["removed"] += 1
                    assert row.get("consulted") is None or "[" not in match.group("rest"), (path.name, match.group(0))
                elif out == match.group(0).strip():
                    outcome["kept"] += 1
                else:
                    outcome["card"] += 1
                    assert out.rstrip(".").endswith("]") and "[case_" in out, (path.name, out)
    assert outcome == {"card": 92, "kept": 24, "removed": 8}
