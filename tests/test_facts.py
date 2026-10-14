"""Facts about real matches, coaches and teams (src/guardrails/facts.py), offline: the errors of
eval/error_log.md one by one (E1, E2: the real case; E3, E4, E5: pairs and thresholds), the agent's
flow with answers written by the test, and the saved answers of real runs as a bench."""

from __future__ import annotations

import json

import pytest
from datapizza.type import ROLE

from scripts.review_chats import card_texts
from src.agent.analyst_agent import MatchAnalyst
from src.core.config import PROJECT_ROOT
from src.guardrails.facts import (CASE_LINE_RE, closing_summary, collapse_real_cases, effect_tails, expand_real_cases,
                                  fact_issues,
                                  perspective_issues, premise_issues, remove_sentences, sentences, unmarked_unknown,
                                  writes_man_down)
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
    frozen = [p for p in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json"))
              if p.stem.split("_")[1] < "20261010"]      # the runs written before this change
    for path in frozen:
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


# ---------------------------------------------------------------- step 2: coach-team pairs and thresholds
def kinds(text: str, cards: dict, consulted: list[str]) -> list[str]:
    return [i.kind for i in fact_issues(text, "\n".join(cards[c] for c in consulted))]


@pytest.mark.parametrize("sentence, expected", [
    ("Italiano pressa alto come l'Atalanta di Italiano [coach_italiano].", ["coach_team"]),          # E4
    ("Nella tesi Pioli descrive il Milan di Pioli campione d'Italia [coach_pioli].", ["coach_team"]),  # E3
    ("Il PSG era allenato da **Lionel Scaloni** in quella finale [coach_scaloni].", ["coach_team"]),  # gold 123326, Q21
    ("Scaloni sulla panchina del PSG ha vinto [coach_scaloni].", ["coach_team"]),
    ("Italiano all'Atalanta cercava la verticale [coach_italiano].", ["coach_team"]),
    ("Italiano's Atalanta pressed high [coach_italiano].", ["coach_team"]),
    ("Pioli spiega come giocava il suo Milan campione d'Italia [coach_pioli].", ["coach_team"]),       # Q18
    ("Questi concetti possono riflettere l'approccio di Pioli anche nel Milan [coach_pioli].", ["coach_team"]),
    ("Guardiola al Bayern chiede a Lahm di accentrarsi [coach_guardiola].", []),
    ("According to Pioli's thesis, his Milan pressed on the flanks [coach_pioli].", ["coach_team"]),
    ("Pioli allenava la Primavera del Chievo con il suo 4-4-2 [coach_pioli].", []),
    ("Gasperini con la sua Atalanta marca a uomo [coach_gasperini].", []),
    ("La tesi non parla del Milan di Pioli, ma del Chievo [coach_pioli].", []),        # a correction, not a claim
    ("L'Atalanta di Gasperini marca a uomo [coach_gasperini].", []),
    ("L'Arsenal era guidato da Mikel Arteta [case_2026_ucl_final_psg_arsenal].", []),    # the pair of the final
    ("Scaloni, allenatore dell'Argentina, sceglie il 4-4-2 [coach_scaloni].", []),
    ("L'Inter di Conte ha registrato un PPDA di 9,08 nel 2019-20 [glossary_metriche].", []),
    ("Guardiola's City kept the ball [coach_guardiola].", []),
    ("Un calcio di stampo italiano, con più di 20 passaggi [coach_italiano].", []),     # an adjective, no metric
])
def test_coach_team_pairs(cards, sentence, expected):
    consulted = ["coach_italiano", "coach_pioli", "coach_gasperini", "glossary_metriche", "coach_guardiola",
                 "coach_scaloni", "case_2026_ucl_final_psg_arsenal"]
    assert kinds(sentence, cards, consulted) == expected


def test_e5_invented_threshold(cards):
    e5 = ("Un valore di PPDA (Passes Per Defensive Action) inferiore a 10 indica un pressing di livello "
          "d'élite [glossary_metriche].")
    assert kinds(e5, cards, ["glossary_metriche"]) == ["threshold"]
    assert kinds("Con il possesso sotto il 40% servono transizioni [glossary_metriche].", cards,
                 ["glossary_metriche"]) == ["threshold"]
    assert kinds("Un PPDA di 9,08 nel 2019-20, più basso di quello del 2020-21 [glossary_metriche].", cards,
                 ["glossary_metriche"]) == []                                       # a value, not a threshold


def test_sentences_and_removal():
    text = "Primo [coach_pioli, p. 4]. Secondo (Spalla, pp. 45-46) qui. Terzo!"
    assert sentences(text) == ["Primo [coach_pioli, p. 4].", "Secondo (Spalla, pp. 45-46) qui.", "Terzo!"]
    answer = "Intro [a_b].\n- **Soglia:** Un PPDA inferiore a 10 è élite [x_y].\n- Altro [c_d]."
    assert remove_sentences(answer, ["Un PPDA inferiore a 10 è élite [x_y]."]) == "Intro [a_b].\n- Altro [c_d]."
    assert remove_sentences("Solo questa [x_y].", ["Solo questa [x_y]."]) == "Non lo so."


PPDA = "Quale valore di PPDA indica un pressing d'élite?"
E5_SENTENCE = "Un PPDA inferiore a 10 indica un pressing d'élite [glossary_metriche]."


def test_a_wrong_fact_still_there_after_the_rewrite_is_removed(retriever):
    llm = ScriptedLLM(answer=f"Il PPDA misura il pressing [glossary_metriche]. {E5_SENTENCE}",
                      rewrite=f"Il PPDA misura il pressing [glossary_metriche]. {E5_SENTENCE}")   # still there
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    assert analyst.analyze(PPDA) == "Il PPDA misura il pressing [glossary_metriche]."
    assert analyst.last_guard["removed"] == [E5_SENTENCE] and "1 frasi tolte" in analyst.guard_note
    assert not any(r.startswith("threshold") for r in analyst.last_guard["remaining"])


def test_a_wrong_fact_is_removed_also_when_the_rewrite_fails(retriever):
    llm = ScriptedLLM(answer=f"Il PPDA misura il pressing [glossary_metriche]. {E5_SENTENCE}")   # no rewrite: it fails
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    assert analyst.analyze(PPDA) == "Il PPDA misura il pressing [glossary_metriche]."
    assert analyst.last_guard["error"]


def test_every_saved_answer_is_flagged_only_where_wrong(cards):
    """Every answer saved since the first runs (agent runs, gold runs and their re-judges): each
    sentence flagged is one of the known errors (E3, E4, E5), and each of them is flagged."""
    known = {"Q35": ("inferiore a 10",), "Q18": ("di Pioli", "suo Milan"), "Q12": ("Atalanta di Italiano",)}
    runs, seen = PROJECT_ROOT / "eval" / "runs", set()
    for path in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("questions") or data.get("rows") or []:
            consulted, qid = row.get("consulted") or [], row.get("question_id") or row["id"]
            if not consulted:
                continue
            for issue in fact_issues(row["answer"], "\n".join(cards[c] for c in consulted)):
                assert qid in known and any(k in issue.detail for k in known[qid]), (path.name, qid, issue.detail)
                seen.add(qid)
    assert seen == set(known)


# ---------------------------------------------------------------- step 3: whose side the advice is for (E17)
@pytest.mark.parametrize("question, answer, flagged", [
    ("E se restassimo in 10 al 90'?",                                       # E17, chat of 2026-10-09
     "Sfruttate la vostra superiorità [situation_giocare_in_superiorita_numerica].", True),
    ("E se restassimo in 10 al 90'?",
     "Non lo so: le schede non hanno consigli per chi resta in 10. L'avversario allargherà il gioco "
     "[situation_giocare_in_superiorita_numerica].", False),
    ("L'avversario resta in 10, cosa facciamo?", "Allargate [situation_giocare_in_superiorita_numerica].", False),
    ("We are down to ten men, what now?", "Use the extra man [situation_giocare_in_superiorita_numerica].", True),
    ("Stiamo perdendo 1-0 al 70'", "Difendete compatti [situation_difendere_un_vantaggio].", True),
    ("Stiamo perdendo 1-0 al 70'", "Alzate il ritmo [situation_rimontare_uno_svantaggio]. Loro si chiuderanno "
                                   "[situation_difendere_un_vantaggio].", False),
    ("Siamo in vantaggio, come difendiamo?", "Abbassate il blocco [situation_difendere_un_vantaggio].", False),
    ("Siamo in 10 e stiamo vincendo 1-0, che facciamo?",                   # a man down with a lead: its card
     "Abbassate il blocco [situation_difendere_un_vantaggio]. Loro allargheranno il gioco "
     "[situation_giocare_in_superiorita_numerica].", False),
])
def test_the_advice_is_for_the_coachs_side(question, answer, flagged):
    assert bool(perspective_issues(answer, question)) == flagged


def test_a_score_given_before_counts_for_the_side():
    answer = ("Abbassate il blocco [situation_difendere_un_vantaggio]. Loro allargheranno il gioco "
              "[situation_giocare_in_superiorita_numerica].")
    assert perspective_issues(answer, "E se restassimo in 10?")
    assert not perspective_issues(answer, "E se restassimo in 10?", "Stiamo vincendo 1-0 al 75'.")


@pytest.mark.parametrize("question, earlier, written", [
    ("E se restassimo in 10 al 90'?", "Domenica affrontiamo un 4-4-2 basso. Noi giochiamo 4-3-3.", True),  # E17
    ("Siamo in 10 e stiamo vincendo 1-0, che facciamo?", "", False),
    ("E se restassimo in 10?", "Siamo in vantaggio 1-0 al 75'.", False),
    ("We are down to ten men and losing, what now?", "", False),
    ("L'avversario resta in 10, come lo sfruttiamo?", "", False),
    ("What if we went down to 10 at the 90th?", "", True),
    ("What if we get a player sent off?", "", True),
    ("What if one of our players is sent off at the 70th?", "", True),
    ("E se ci espellono un difensore?", "", True),
    ("What if they go down to ten men?", "", False),
])
def test_the_man_down_answer_is_written_only_without_a_score(question, earlier, written):
    assert writes_man_down(question, earlier) == written


def test_the_agent_asks_for_the_coachs_side(retriever):
    llm = ScriptedLLM(answer="Difendete compatti [situation_difendere_un_vantaggio].",
                      rewrite="Alzate il ritmo [situation_rimontare_uno_svantaggio].")
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    answer = analyst.analyze("Stiamo perdendo 1-0 al 70', come la riprendiamo?")
    assert any(i.startswith("perspective") for i in analyst.last_guard["issues"])
    assert "written for the other side" in llm.rewrite_requests[0] and answer.startswith("Alzate il ritmo")


def test_a_man_down_gets_the_answer_written_from_the_cards(retriever):
    # E17 after the side check: the model, asked to keep the two sides apart, still mixed them.
    llm = ScriptedLLM(answer="Sfruttate la vostra superiorità [situation_giocare_in_superiorita_numerica].")
    chat = MatchAnalyst(client=llm, retriever=retriever, stateless=False)
    answer = chat.analyze("E se restassimo in 10 al 90'?")
    assert llm.seen == []                                                         # no model call
    assert answer.startswith("Non lo so: nelle schede non ci sono consigli per chi gioca con un uomo in meno.")
    assert "«l'avversario» siete voi" in answer and "- Leggere dove manca l'uomo — " in answer
    assert ("Caso reale dalla parte di chi era in 10: Mondiale 2026 (perso 1-0 d.t.s.)" in answer
            and answer.endswith("in dieci dal 90'+3' [coach_scaloni]."))          # Argentina's side, not Spain's
    assert chat.consulted_cards == ["situation_giocare_in_superiorita_numerica", "coach_scaloni"]
    assert "risposta composta con le schede" in chat.guard_note
    assert [t.role for t in chat.agent._memory][-2:] == [ROLE.USER, ROLE.ASSISTANT]   # the chat goes on


def test_a_man_down_with_a_lead_is_answered_by_the_model(retriever):
    llm = ScriptedLLM(answer="Abbassate il blocco [situation_difendere_un_vantaggio].")
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    answer = analyst.analyze("Siamo in 10 e stiamo vincendo 1-0 all'80', che facciamo?")
    assert llm.seen and answer.startswith("Abbassate il blocco") and "composed" not in analyst.last_guard


@pytest.mark.parametrize("answer, coach, flagged", [
    ("Dovete gestire la situazione con attenzione per mantenere il vantaggio.",          # E17 chat, 2026-10-14
     "Noi giochiamo 4-3-3 contro un 4-4-2 basso.\nE se restassimo in 10 al 90'?", True),
    ("Dovete difendere il vantaggio [situation_difendere_un_vantaggio].", "Siamo in vantaggio 1-0 al 80'.", False),
    ("Per recuperare lo svantaggio alzate il ritmo [situation_rimontare_uno_svantaggio].", "Stiamo perdendo 2 a 1.", False),
    ("Abbassate il blocco [situation_difendere_un_vantaggio].", "Come chiudiamo le partite?", False),
])
def test_a_score_the_coach_never_gave_is_not_taken_for_granted(answer, coach, flagged):
    assert bool(premise_issues(answer, coach)) == flagged


def test_no_side_flag_on_the_saved_answers():
    # The chat of E17 is git-ignored (chats/): its turn is the first case above.
    runs = PROJECT_ROOT / "eval" / "runs"
    for path in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("questions") or data.get("rows") or []:
            assert not perspective_issues(row["answer"], row["question"]), (path.name, row.get("question_id"))


# ---------------------------------------------------------------- step 5: the closing summary
@pytest.mark.parametrize("answer, closing", [
    ("Con palla libera la linea scivola [coach_pioli].\n\nQueste regole aiutano a mantenere l'equilibrio.",   # Q03
     "Queste regole aiutano a mantenere l'equilibrio."),
    ("- Possesso dal 54% al 60,8% [coach_de_zerbi].\nQuesti cambiamenti riflettono un'evoluzione.",             # Q27
     "Questi cambiamenti riflettono un'evoluzione."),
    ("Possession rose to 60.8% [coach_de_zerbi].\nThis evolution led to a more solid defense.",
     "This evolution led to a more solid defense."),
    ("Il PPDA sale a 13,44 [glossary_metriche].\nIn sintesi, il pressing cala [glossary_metriche].", None),     # cited
    ("Il PPDA sale a 13,44 [glossary_metriche].\n- Questo indica meno pressing.", None),                       # a bullet
    ("Abbassate il blocco [situation_difendere_un_vantaggio].\nCaso reale: [case_2023_ucl_final_city_inter]", None),
    ("Queste regole aiutano.", None),                                                                          # nothing else
    ("La linea scivola.\nQuesto aiuta.", None),                                                              # no citation at all
    ("Inzaghi usa i braccetti [coach_inzaghi].\nIn sintesi, Inzaghi potrebbe essere più affine al tuo stile.", None),
])
def test_the_closing_summary(answer, closing):
    assert closing_summary(answer) == closing


def test_the_agent_removes_the_closing_summary(retriever):
    llm = ScriptedLLM(answer="Con palla libera la linea scivola indietro [situation_attaccare_un_blocco_basso].\n\n"
                             "Queste regole aiutano a mantenere l'equilibrio.")
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    answer = analyst.analyze("Come si attacca un blocco basso?")
    assert "Queste regole" not in answer and analyst.last_guard["closing"].startswith("Queste regole")
    assert "tolta la frase di chiusura senza fonte" in analyst.guard_note


def test_an_english_question_carries_the_reminder(retriever):
    llm = ScriptedLLM()
    chat = MatchAnalyst(client=llm, retriever=retriever, stateless=False)
    chat.analyze("How do we attack a deep low block with a 4-3-3?")
    assert llm.seen[0][0].endswith("(Answer in English: translate what you take from the Italian cards.)")
    assert chat.coach_questions == ["How do we attack a deep low block with a 4-3-3?"]   # the coach's words only
    chat.analyze("Come si attacca un blocco basso?")
    assert not llm.seen[-1][0].endswith("cards.)")


def test_closing_summaries_on_the_saved_answers():
    # Every closing sentence found in the saved answers is a summary or an evaluation, never a cited fact.
    runs = PROJECT_ROOT / "eval" / "runs"
    found = 0
    for path in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("questions") or data.get("rows") or []:
            closing = closing_summary(row["answer"])
            if closing:
                found += 1
                assert "[" not in closing and closing in row["answer"], (path.name, closing)
    assert found >= 40


# ---------------------------------------------------------------- step 5b: an unknown said without "Non lo so" (Q21)
@pytest.mark.parametrize("answer, unknown", [
    ("Il PSG ha vinto ai rigori [case_2026_ucl_final_psg_arsenal].\n\nIl PSG era guidato in panchina da un allenatore "
     "non specificato [case_2026_ucl_final_psg_arsenal].",                      # gold 20261014-141635, Q21
     "Il PSG era guidato in panchina da un allenatore non specificato [case_2026_ucl_final_psg_arsenal]."),
    ("Non ho informazioni specifiche sul PPDA della Fiorentina.", "Non ho informazioni specifiche sul PPDA della Fiorentina."),
    ("PSG won on penalties [x_y]. The cards do not name PSG's coach.", "The cards do not name PSG's coach."),
    ("Non lo so. Non ci sono informazioni specifiche sul PPDA della Fiorentina.", None),   # already said
    ("Abbassate il blocco [situation_difendere_un_vantaggio].\nCaso reale: Mondiale 2026 — nessun tiro, "
     "nome non indicato [case_2026_wc_final_spain_argentina].", None),          # the card's own sentence
    ("Il PSG ha vinto ai rigori [case_2026_ucl_final_psg_arsenal].", None),
])
def test_an_unknown_said_without_non_lo_so(answer, unknown):
    assert unmarked_unknown(answer) == unknown


def test_the_agent_marks_the_unknown_with_non_lo_so(retriever):
    llm = ScriptedLLM(answer="Il PSG ha vinto ai rigori [case_2026_ucl_final_psg_arsenal].\n\nIl PSG era guidato in "
                             "panchina da un allenatore non specificato [case_2026_ucl_final_psg_arsenal].")
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    answer = analyst.analyze("Chi ha vinto la finale di Champions League 2026 e chi era in panchina il PSG?")
    assert "\n\nNon lo so. Il PSG era guidato in panchina da un allenatore non specificato" in answer
    assert "segnato con «Non lo so»" in analyst.guard_note


def test_unmarked_unknowns_on_the_saved_answers():
    # On every saved answer, an unknown said without "Non lo so" is an abstention missed: Q19 and Q21 only.
    runs, seen = PROJECT_ROOT / "eval" / "runs", set()
    for path in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("questions") or data.get("rows") or []:
            if unmarked_unknown(row["answer"]):
                seen.add(row.get("question_id") or row["id"])
    assert seen == {"Q19", "Q21"}


def test_a_name_written_in_part_is_cut_back_without_a_rewrite(retriever):
    # E9, Q31: asked to remove "Philipp" and "Monaco", the rewrite removed Lahm and Bayern too.
    llm = ScriptedLLM(answer="Il falso terzino nasce al Bayern Monaco, con Philipp Lahm in mezzo al campo [coach_guardiola].")
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    answer = analyst.analyze("Da dove nasce il falso terzino di Guardiola?")
    assert "coach_guardiola" in analyst.consulted_cards
    assert answer == "Il falso terzino nasce al Bayern, con Lahm in mezzo al campo [coach_guardiola]."
    assert llm.rewrite_requests == [] and analyst.last_guard["trimmed"] == ["Monaco", "Philipp"]
    assert "tolto: Monaco, Philipp" in analyst.guard_note


# ---------------------------------------------------------------- step 5c: effects the cards do not state (E20)
@pytest.mark.parametrize("answer, tails", [
    ("È importante perché permette combinazioni e tagli, creando opportunità di tiro o passaggi filtranti "
     "[situation_attaccare_un_blocco_basso].", [", creando opportunità di tiro o passaggi filtranti"]),   # Q05
    ("L'Inter di Conte ha un PPDA di 9,08, evidenziando un pressing molto efficace [glossary_metriche].",
     [", evidenziando un pressing molto efficace"]),                                                       # Q35
    ("Al City passa da un 3-2-5 a un 2-3-5, creando così superiorità numerica [coach_guardiola].",
     [", creando così superiorità numerica"]),                                                             # Q31
    ("The PPDA rose to 13.44, showing a shift to a more compact defense.", [", showing a shift to a more compact defense"]),
    ("La Spagna avanza, creando 182 linee rotte [case_2026_wc_final_spain_argentina].", []),               # a number
    ("Pressing alto, evidenziando la superiorità della Spagna [x_y].", []),                                # a name
    ("Gli attaccanti indirizzano il gioco, trasformando la squadra in un 3-4-3 [coach_pioli].", []),        # not an effect
    ("Abbassate il blocco [situation_difendere_un_vantaggio].\nCaso reale: Reggere e poi colpire, creando poco "
     "[case_2023_ucl_final_city_inter].", []),                                                             # the card's own line
])
def test_effect_tails(answer, tails):
    assert effect_tails(answer) == tails


def test_the_agent_cuts_the_effect_tails(retriever):
    llm = ScriptedLLM(answer="Il blocco basso si attacca nella zona di rifinitura, creando opportunità di tiro "
                             "[situation_attaccare_un_blocco_basso].")
    analyst = MatchAnalyst(client=llm, retriever=retriever)
    answer = analyst.analyze("Come si attacca un blocco basso?")
    assert answer == "Il blocco basso si attacca nella zona di rifinitura [situation_attaccare_un_blocco_basso]."
    assert "tolta un'aggiunta non scritta nelle schede" in analyst.guard_note


def test_cutting_the_effect_tails_keeps_every_required_fact():
    # Every saved answer of a gold question: the facts the gold set requires are still there after the cut.
    gold = {q["question_id"]: q for q in json.loads((PROJECT_ROOT / "eval" / "gold_set.json").read_text(encoding="utf-8"))["questions"]}
    runs, cut = PROJECT_ROOT / "eval" / "runs", 0
    for path in sorted(runs.glob("agent_2026*.json")) + sorted(runs.glob("gold_2026*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for row in data.get("questions") or data.get("rows") or []:
            qid, after = row.get("question_id") or row["id"], row["answer"]
            for tail in effect_tails(row["answer"]):
                after, cut = after.replace(tail, "", 1), cut + 1
            for group in gold[qid]["required_facts"] if qid in gold else []:
                before_has = any(alt.lower() in row["answer"].lower() for alt in group)
                assert not before_has or any(alt.lower() in after.lower() for alt in group), (path.name, qid, group)
    assert cut > 100
