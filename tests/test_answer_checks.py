"""Automatic checks on agent answers (offline)."""

from __future__ import annotations

from src.evaluation.answer_checks import check_answer, follow_up_problems, problems

FOOTBALL = {"type": "trap", "expected_tool_use": "retrieval", "requires_abstention": False,
            "relevant_sources": ["coach_pioli"], "required_facts": [["chievo"], ["primavera"]],
            "forbidden_claims": ["scudetto"]}
OUT_OF_CORPUS = {"type": "out_of_corpus", "expected_tool_use": "retrieval", "requires_abstention": True,
                 "relevant_sources": [], "required_facts": [], "forbidden_claims": []}
GREETING = {"type": "chitchat", "expected_tool_use": "none", "requires_abstention": False,
            "relevant_sources": [], "required_facts": [], "forbidden_claims": []}


def test_good_answer_passes():
    answer = "La tesi parla della Primavera del Chievo, non del Milan [coach_pioli]."
    check = check_answer(answer, FOOTBALL, ["coach_pioli"], tool_calls=1)
    assert problems(check) == [] and check["facts_found"] == "2/2"


def test_citation_problems_are_caught():
    answer = "Gioco di posizione [note_gioco_di_posizione] e scudetto [Soncin, p. 19]."
    issues = problems(check_answer(answer, FOOTBALL, ["coach_pioli"], tool_calls=1))
    assert any("did not consult" in i for i in issues)
    assert any("card-internal references" in i for i in issues)
    assert any("forbidden" in i for i in issues)
    assert any("required facts" in i for i in issues)


def test_malformed_and_invented_ids_are_caught():
    # Seen in run 160112: the whole source line copied, and an id that does not exist.
    answer = "Duelli uomo contro uomo [=== FONTE: coach_gasperini ===]. PPDA [glossario_metriche]."
    check = check_answer(answer, FOOTBALL, ["coach_gasperini", "glossary_metriche"], tool_calls=1)
    assert check["malformed_citations"] == ["=== FONTE: coach_gasperini ==="]
    assert check["invalid_citations"] == ["glossario_metriche"]


def test_copied_source_lines_do_not_count_as_citations():
    # Seen in run 160918: no inline citation, the tool header pasted at the end.
    for footer in ("--- Fonte: [coach_pioli] · Profilo allenatore: Stefano Pioli · scheda intera ---",
                   "[coach_pioli] Profilo allenatore: Stefano Pioli · scheda intera"):
        check = check_answer(f"La tesi parla della Primavera del Chievo.\n\n{footer}", FOOTBALL, ["coach_pioli"], 1)
        assert check["copied_headers"] and check["cited"] == []
        assert any("source line copied" in p for p in problems(check))


def test_abstention():
    assert problems(check_answer("Non lo so.", OUT_OF_CORPUS, [], tool_calls=1)) == []
    issues = problems(check_answer("Non ho trovato informazioni.", OUT_OF_CORPUS, [], tool_calls=1))
    assert 'missing "Non lo so"' in issues


def test_tool_use():
    assert problems(check_answer("Ciao!", GREETING, [], tool_calls=0)) == []
    assert any("tool use" in i for i in problems(check_answer("Ciao!", GREETING, [], tool_calls=1)))
    assert any("tool use" in i for i in problems(check_answer("Chievo Primavera [coach_pioli]", FOOTBALL, [], 0)))


def test_long_advice_is_flagged():
    advice = dict(FOOTBALL, type="situational", required_facts=[], forbidden_claims=[])
    long_answer = " ".join(["parola"] * 200) + " [coach_pioli]"
    assert any("too long" in p for p in problems(check_answer(long_answer, advice, ["coach_pioli"], 1)))
    assert problems(check_answer("Breve consiglio [coach_pioli].", advice, ["coach_pioli"], 1)) == []


def test_several_ids_in_one_bracket_are_citations():
    # Run agent_20260928-171548: "[coach_klopp, coach_italiano]" was flagged as malformed.
    answer = "Riaggressione immediata [coach_klopp, coach_italiano]."
    check = check_answer(answer, FOOTBALL, ["coach_klopp", "coach_italiano"], 1)
    assert check["cited"] == ["coach_klopp", "coach_italiano"] and check["malformed_citations"] == []
    assert check_answer("Pressing [coach_klopp, Pioli]", FOOTBALL, ["coach_klopp"], 1)["malformed_citations"]
    # Run agent_20260928-180737: ids separated by ";", with pages.
    check = check_answer("PPDA 9,08 [coach_conte, p. 51; glossary_metriche].", FOOTBALL,
                         ["coach_conte", "glossary_metriche"], 1)
    assert check["cited"] == ["coach_conte", "glossary_metriche"] and check["malformed_citations"] == []


def test_answer_language_must_match_the_question():
    # Run agent_20260928-163729: all six English questions got Italian answers.
    english = dict(FOOTBALL, type="single_hop", required_facts=[], forbidden_claims=[], language="en")
    italian_answer = "Le catene laterali sono formate dal terzino e dall'esterno dello stesso lato [coach_pioli]."
    english_answer = "The flank chains are the full-back, the central midfielder and the wide midfielder [coach_pioli]."
    assert "answer in the wrong language (it)" in problems(check_answer(italian_answer, english, ["coach_pioli"], 1))
    assert problems(check_answer(english_answer, english, ["coach_pioli"], 1)) == []
    assert check_answer(italian_answer, dict(english, language="it"), ["coach_pioli"], 1)["language_ok"]


def test_follow_up_checks():
    q = dict(FOOTBALL, type="follow_up", relevant_sources=["situation_uscire_dal_pressing_alto"],
             required_facts=[], forbidden_claims=[])
    previous = "Domenica affrontiamo un 4-4-2 basso. Noi giochiamo 4-3-3. Come la prepariamo?"
    good = "Con il tuo 4-3-3 cerca la verticale [situation_uscire_dal_pressing_alto]."
    check = check_answer(good, q, ["situation_uscire_dal_pressing_alto"], 1)
    assert follow_up_problems(good, previous, check) == []
    generic = "Cerca la verticale e il terzo uomo [coach_gasperini]."
    check = check_answer(generic, q, ["coach_gasperini"], 1)
    assert follow_up_problems(generic, previous, check) == [
        "expected card not consulted: ['situation_uscire_dal_pressing_alto']",
        "previous turn not used (no 4-4-2, 4-3-3)"]
    typographic = "Con il tuo 4–3–3 cerca la verticale [situation_uscire_dal_pressing_alto]."   # en dashes
    check = check_answer(typographic, q, ["situation_uscire_dal_pressing_alto"], 1)
    assert follow_up_problems(typographic, previous, check) == []


def test_grounding_knows_the_earlier_questions_of_a_conversation():
    q = dict(FOOTBALL, type="follow_up", question="E se invece ci pressano alti?", required_facts=[],
             forbidden_claims=[])
    answer = "Contro la Juventus la tesi resta valida [coach_pioli]."
    source = "Tesi: Primavera del Chievo."
    assert check_answer(answer, q, ["coach_pioli"], 1, source)["ungrounded"] == ["Juventus"]
    assert check_answer(answer, q, ["coach_pioli"], 1, source, "Affrontiamo la Juventus.")["ungrounded"] == []
