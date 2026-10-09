# Error log

Wrong answers found while using and measuring the assistant, kept as evidence: every candidate fix
is tried on these cases first, then measured on the gold run. Add a row for every new error: the
case (where it was found), the symptom (the wrong sentence and what the card says), the cause, the
fix and the outcome.

The verifier (a second model that checks every statement of the answer against the cards before
it is shown, `src/guardrails/verifier.py`) was measured on 2026-10-09: it catches swapped roles
and invented thresholds (E2, E5), but on the gold set it raised faithfulness by 0.025 (under the
+0.03 of the acceptance gate) for 5 times the cost and 4 times the latency, so it is off by default
(`--verifier`). Runs: `eval/runs/README.md`.

| Id | Case | Symptom | Cause | Fix | Outcome |
|---|---|---|---|---|---|
| E1 | App, second turn of a chat (2026-09-29, clean-install check) | Real case: *"l'Inter, nella Champions 2023, ha difeso un vantaggio"*. The card `case_2023_ucl_final_city_inter`: City won 1-0 (goal by Rodri), Inter was chasing the game | The right card was read; the sentence swapped the roles | Verifier (tried 2026-10-09, optional); to try: the real case quoted verbatim from the card | Open: the verifier catches this kind of error but stays off by default (under the gate) |
| E2 | Q37, run `agent_20260929-112013` | Real case: *"l'Atalanta ha sfruttato il pressing a uomo del Leverkusen"*. The card `case_2024_uel_final_atalanta_leverkusen`: the man-to-man press was Atalanta's | As E1 | Verifier with the roles written out before the verdict (`agent_20261009-105844`, rechecks) | Caught 5/5 in rechecks, but the plain check missed it once in a run; verifier off by default (gold `20261009-114805`) |
| E3 | Q18 (trap), agent gpt-4.1-mini, run `agent_20260928-180737` | Pioli's thesis described as *"il Milan campione d'Italia di Pioli"* in every sentence: faithfulness 0.00 (gold `-094857`). The card `coach_pioli`: the thesis is about the Chievo youth team | The false premise of the question was accepted | Agent gpt-4o-mini (0.78 on the same question, gold `-100809`); verifier | Mitigated by the model choice |
| E4 | Q12, run `agent_20260928-180737` | *"L'Atalanta di Italiano ha prodotto gol da palloni recuperati"*. In the cards Atalanta is Gasperini's team | A coach and a team taken from two different cards | Verifier | Open |
| E5 | Q35, run `agent_20260928-180737` | *"Un valore di PPDA indicativo di un pressing di livello d'élite è intorno a 9 o inferiore"*. The cards give single values (Conte's Inter 9.08), never a threshold | An example turned into a rule, which the prompt forbids | Verifier: caught in `agent_20261009-105844` and in rechecks 2/2 | Mitigated only with the verifier on; in gold `20261009-114805` the rewrite softened the threshold but kept it |
| E6 | App, same chat as E1 | To "and if we were down to 10 at the 90th minute?": *"dovete difendere il vantaggio"*. The coach never gave the score | A premise invented in a follow-up | Prompt rule for follow-ups: when the situation is not clear, cover the cases or ask (the verifier would probably not see it: defending a lead is in the card) | Open |
| E7 | Q17, every run | Spain's possession given as 60.2%, without the 65% of the other source that the card reports | A source conflict left out | Seen only by the required facts of `eval_agent`: a claim-by-claim judge cannot see an omission | Known limit |
| E8 | Q11, run `agent_20260929-112013` | Gasperini's principles explained, but not the final itself (Lookman, 3-0), though both cards were read whole | An incomplete answer to a two-card question | To try: the agent plans its searches before answering | Open |
| E9 | Q31, run `agent_20260929-112013` | The rewrite deleted *"Lahm"* and *"Bayern"*, the answer to the question | The grounding check flagged "Philipp" and "Monaco" (the card writes "Lahm" and "Bayern") and the rewrite removed the whole sentence | The rewrite removes only the flagged words | Fixed: Lahm stays in Q31 (`agent_20261009-105844`); part of the reference gold run `20261009-112356` |
| E10 | Q05, Q25, Q43, run `agent_20260929-112013` | Correct answers counted as "required facts missing" (Q05: "lo spazio tra i centrocampisti e i difensori" for "alle spalle dei centrocampisti e davanti ai difensori") | The required-facts check looks for exact words; the answers paraphrase | None: the gold set is frozen. Read these failures before counting them | Not an agent error |
| E11 | App, chat of 2026-09-30 | *"sto giocando 352 e devo affrontare 433 cosa faccio?"* stopped as off topic, before the model | The input guard knew formations only with dashes (3-5-2), and "giocando" / "affrontare" were not in its vocabulary | Formations without dashes (3 or 4 digits from 1 to 5 adding up to 10), stems `gioc`, `affront`; test in `test_guardrails.py` | Fixed; verdicts on the gold set unchanged (45/45) |
| E12 | App, chat of 2026-09-30 | *"sto perdendo e sono al 90esimo, che devo fare?"* stopped as off topic | An in-game situation with no football word: the score and the minute were not in the vocabulary | Game situations in the input guard: minute (90esimo, 90'), score (1-0, sotto di uno), phase (secondo tempo), a man down, changes and cards; test | Fixed; verdicts on the gold set unchanged (45/45) |
| E13 | App, chat of 2026-10-01, turn 3 | *"quali sono i suoi punti deboli?"*, right after a question on Gasperini, stopped as off topic | A follow-up of 6 words (over the 4 of a short follow-up) with no football word: "suoi" points back, but it was not among the words that do | Possessive and personal pronouns (suo, suoi, lui, his, their, ...) count as pointing back, in a conversation only; test | Fixed; outside a conversation the question is still stopped |
| E14 | App, chat of 2026-10-01, turn 1 | *"ciao, quali sono i moduli migliori nel calcio di oggi?"* answered "Non lo so" without any search, while `glossary_moduli` covers formations | Probably the greeting: the prompt answers greetings without tools, and the question came in the same line | To try: the prompt rule "a greeting followed by a question: answer the question, with the tools" | Open |
| E15 | App, chat of 2026-10-01, turn 15 | *"Inzaghi utilizza le sovrapposizioni dei braccetti (terzini)"*. The card `coach_inzaghi`: the wing-backs ("terzini" in the source) join the attack; the back-three's outside centre-backs are never mentioned | A role taken from the question (the coach spoke of braccetti) and given to the wrong players: the same family as E1 and E2 | Verifier (optional); to try: the real case or the coach's trait quoted verbatim | Open |
| E16 | App, chat of 2026-10-01, turn 11 (English question) | A correct answer (every number in the card) got a rewrite attempt, not kept: "Key", "Aspects", "Victory", "Offensive", ... flagged as names not in the cards | The grounding check reads capitalised words as proper nouns; English headings in Title Case are not names | To try: ignore the words of headings and bold labels in the grounding check | Open (a false alarm, costs one rewrite call) |

The deterministic guardrails check names, numbers and citations: they cannot see E1–E6 and E15,
where every name is in the cards and the sentence puts them together wrongly. The claim-by-claim judge of
the gold run sees most of them (E3, E4 with gpt-4.1-mini; E5 only with gpt-4.1).

Football questions wrongly stopped by the input guard (E11, E12) show up in the review printed by
`python -m scripts.start` when the app is closed, marked `stopped (off_topic)`: the words to add
are read there.
