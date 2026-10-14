"""Grounding check: names and numbers must come from the consulted cards (offline)."""

from __future__ import annotations

from src.evaluation.answer_checks import check_answer, problems
from src.guardrails.grounding import ungrounded_terms

CARD = ("Finale Champions League 2026: Paris Saint-Germain 1-1 Arsenal (4-3 d.c.r.). "
        "0-1 al 6', con Havertz; al 61' Dembélé trasforma il rigore.")
QUESTION = "Chi ha vinto la finale di Champions League 2026 e con chi era in panchina il PSG?"


def test_name_from_memory_is_caught():
    # Run agent_20260928-162748: a coach name no card gives, next to a real citation.
    answer = "Il PSG ha vinto 4-3 ai rigori. Il PSG era guidato in panchina da Luis Enrique [case_x]."
    assert ungrounded_terms(answer, CARD, QUESTION) == ["Luis", "Enrique"]


def test_grounded_answer_passes():
    answer = ("Il Paris Saint-Germain ha battuto l'Arsenal 4-3 ai rigori dopo l'1-1 [case_x]. "
              "Havertz segna al 6', Dembélé pareggia su rigore al 61' [case_x].")
    assert ungrounded_terms(answer, CARD, QUESTION) == []


def test_sentence_start_words_are_not_names_but_multiword_names_are():
    card = "La squadra difende a uomo."
    assert ungrounded_terms("Difende a uomo su tutto il campo.", card) == []           # sentence start
    assert ungrounded_terms("Gian Piero allena così.", card) == ["Gian", "Piero"]      # name at start
    assert ungrounded_terms("- **Mantieni** l'ampiezza.", card) == []                   # bullet + bold


def test_invented_number_and_elision():
    assert ungrounded_terms("Pressing dell'Atalanta con PPDA 7,5.", "PPDA 9,08 e 13,44") == ["Atalanta", "7,5"]


def test_decimal_comma_and_dot_are_the_same_number():
    # Run agent_20260928-163729: the card writes 13.48, the Italian answer 13,48.
    assert ungrounded_terms("Il PPDA scende da 13,48 a 10,30.", "Il PPDA: 13.48 poi 10.30") == []
    assert ungrounded_terms("PPDA sotto 10.", "PPDA 10.30") == ["10"]                  # still whole numbers


def test_connective_before_a_name_is_not_a_name():
    # Run agent_20260928-163729: "Inoltre, Guardiola ..." flagged "Inoltre".
    card = "Guardiola sposta Lahm in mezzo al campo."
    assert ungrounded_terms("Inoltre, Guardiola sposta Lahm.", card) == []
    assert ungrounded_terms("Luis Enrique sposta Lahm.", card) == ["Luis", "Enrique"]


def test_check_answer_reports_ungrounded_only_with_sources():
    q = {"type": "out_of_corpus", "question": QUESTION, "expected_tool_use": "retrieval",
         "requires_abstention": False, "relevant_sources": [], "required_facts": [], "forbidden_claims": []}
    answer = "Allenatore: Luis Enrique [case_x]."
    assert check_answer(answer, q, ["case_x"], 1)["ungrounded"] == []                 # no source text given
    check = check_answer(answer, q, ["case_x"], 1, source_text=CARD)
    assert check["ungrounded"] == ["Luis", "Enrique"]
    assert any("not in the consulted cards" in p for p in problems(check))


def test_page_citation_and_indirect_citation_are_accepted():
    q = {"type": "situational", "question": "Come si attacca un blocco basso?", "expected_tool_use": "retrieval",
         "requires_abstention": False, "relevant_sources": [], "required_facts": [], "forbidden_claims": []}
    source = "Caso reale: la Spagna batte il 4-4-2 basso (case_2026_wc)."
    answer = "Occupa la zona di rifinitura [situation_a, p. 19]. La Spagna batte il 4-4-2 basso [case_2026_wc]."
    check = check_answer(answer, q, ["situation_a"], 1, source_text=source)
    assert check["cited"] == ["situation_a", "case_2026_wc"]
    assert check["indirect_citations"] == ["case_2026_wc"] and problems(check) == []


def test_english_answer_may_translate_countries_and_competitions():
    card = "Finale del Mondiale 2026: la Spagna batte l'Argentina."
    assert ungrounded_terms("In the 2026 World Cup final, Spain beat Argentina.", card) == []
    assert ungrounded_terms("In the final, Spain beat Brazil.", card) == ["Brazil"]


def test_english_titles_are_not_names_but_their_numbers_are_checked():
    # E16, chat of 2026-10-01: a right answer got a rewrite attempt for its Title Case headings.
    card = "Finale Mondiale 2026: la Spagna batte l'Argentina; Cubarsì completa 124 passaggi."
    answer = ("### Key Aspects of Spain's Victory\n"
              "- **Offensive Strategy**: Spain built from the back, Cubarsì completing 124 passes.")
    assert ungrounded_terms(answer, card) == []
    assert ungrounded_terms("### Key Aspects of the 2022 Final\n- Spain beat Argentina.", card) == ["2022"]
    # Italian labels capitalise their first word only: a name there is still checked
    assert {"Luis", "Enrique"} <= set(ungrounded_terms("- **Il PSG di Luis Enrique**: la Spagna batte l'Argentina.", card))


def test_hyphenated_chain_of_names():
    # Run agent_20260928-171548: "(Vitinha-Doué-Hakimi)" flagged although the card names all three.
    card = "Vitinha imbuca per Doué, che serve Hakimi."
    assert ungrounded_terms("Un'azione rapida (Vitinha-Doué-Hakimi).", card) == []
    assert ungrounded_terms("Un'azione rapida (Vitinha-Dembélé).", card) == ["Vitinha-Dembélé"]
