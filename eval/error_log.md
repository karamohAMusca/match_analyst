# Error log

Wrong answers found while using and measuring the assistant, kept as evidence: every candidate fix
is tried against these cases first, then measured on the gold run. Add an entry for every new
error (where it was found, the wrong sentence, what the card says, which check saw it).

Fixes are on hold until more material on agents is available; the first attempt, a
verifier that checks every statement of the answer against the cards before it is shown, is saved
on the local branch `verifier-wip` (not measured yet).

| Id | Kind | Where it was found | Seen by |
|---|---|---|---|
| E1 | wrong attribution | app, 2026-09-29 (clean-install check) | nobody (found by hand) |
| E2 | wrong attribution | `agent_20260929-112013`, Q37 | nobody (found by hand) |
| E3 | wrong attribution | `agent_20260928-180737` (gpt-4.1-mini), Q18 | judge (claims), gold `-094857` |
| E4 | wrong attribution | `agent_20260928-180737` (gpt-4.1-mini), Q12 | judge (claims), gold `-094857` |
| E5 | invented rule | `agent_20260928-180737` (gpt-4.1-mini), Q35 | gpt-4.1 judge only (`gold_20260929-101624`) |
| E6 | invented premise | app, 2026-09-29 (clean-install check) | nobody (found by hand) |
| E7 | omission | every run, Q17 | required facts of `eval_agent` |
| E8 | omission | `agent_20260929-112013`, Q11 | required facts of `eval_agent` |
| E9 | guardrail side effect | `agent_20260929-112013`, Q31 | required facts of `eval_agent` |
| E10 | false alarm of a check | `agent_20260929-112013`, Q05, Q25, Q43 | (not an agent error) |

The deterministic guardrails check names, numbers and citations: they cannot see E1–E6, where
every name is in the cards and the sentence puts them together wrongly.

## Wrong attribution: the right card, the roles swapped

**E1 · Inter "defended a lead" in the 2023 Champions League final.** Second turn of a chat
("e se al 90esimo fossimo in 10?"), real case: *"l'Inter, nella Champions 2023, ha difeso un
vantaggio con una difesa organizzata"*. The card `case_2023_ucl_final_city_inter`: City won 1-0
(goal by Rodri), Inter was behind and chasing the game.

**E2 · Leverkusen's man-to-man press.** Q37, real case: *"l'Atalanta ha sfruttato il pressing a uomo
del Leverkusen per segnare due gol da palloni recuperati"*. The card
`case_2024_uel_final_atalanta_leverkusen`: the man-to-man press was Atalanta's, two of the three
goals came from balls it won back.

**E3 · Pioli's thesis given to "his Milan".** Q18 is a trap question (the thesis describes the
Chievo youth team). gpt-4.1-mini answered about *"il Milan campione d'Italia di Pioli"* in every
sentence: faithfulness 0.00. The card `coach_pioli` says the thesis describes the 4-4-2 of the
Chievo youth team, not his later teams. gpt-4o-mini, the chosen agent, scored 0.78 on the same
question (`gold_20260929-100809`).

**E4 · "Italiano's Atalanta".** Q12: *"L'Atalanta di Italiano ha prodotto gol da palloni recuperati
con pressing a uomo aggressivo"*. Atalanta is Gasperini's team in the cards.

Candidate fixes: the verifier (branch `verifier-wip`: claim-by-claim check before the answer is
shown, then a rewrite that corrects the statement); typed citations, a structured answer where
every statement names the card it comes from.

## Invented rule or premise

**E5 · An "elite" PPDA threshold.** Q35: *"Un valore di PPDA indicativo di un pressing di livello
d'élite è intorno a 9 o inferiore"*. The cards give single values (Conte's Inter 9.08 and others),
never a threshold. The gpt-4.1-mini judge missed it; the gpt-4.1 judge caught it.

**E6 · "Defend your lead", never said by the coach.** Same chat as E1: to "and if we were down to 10
at the 90th minute?" the answer was *"dovete difendere il vantaggio"*, while the coach had not said
the score. Candidate fix: a prompt rule for follow-ups (when the situation is not clear, cover the
cases or ask); the verifier would probably not see it, since defending a lead is in the card.

## Omission

**E7 · A source conflict left out.** Q17: the answer gives Spain's possession as 60.2% and leaves
out the 65% of the other source that the card reports. Statement by statement, nothing is wrong:
the claim-by-claim judge cannot see an omission.

**E8 · The match details of a two-card question.** Q11 explains Gasperini's principles but not
the final itself (Lookman, 3-0), though both cards were read whole.

## Guardrail side effect

**E9 · The rewrite deleted the answer.** Q31 (where the "false full-back" comes from): the draft said
*"Philipp Lahm al Bayern Monaco"*; the grounding check flagged "Philipp" and "Monaco" (the card writes
"Lahm" and "Bayern"), and the rewrite removed the whole sentence, with the surname and the team the
question asked for. Fix on `verifier-wip`: the rewrite instruction says to remove only the flagged
words.

## False alarm of a check (not an agent error)

**E10 · Paraphrases counted as missing facts.** The required-facts check of `eval_agent` looks for
exact words: Q05 answered "lo spazio tra i centrocampisti e i difensori" (the card: "alle spalle dei
centrocampisti e davanti ai difensori"), and Q25 and Q43 are correct in other words. The gold set is
frozen, so the check stays as it is: read its failures before counting them as errors.
