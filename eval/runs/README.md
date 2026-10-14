# Evaluation runs

Every run is measured on the frozen `eval/gold_set.json`. Newest last in each table.

## Retrieval (`scripts/eval_retrieval.py`, 40 questions with an expected card)

| Run | What it compares | Result |
|---|---|---|
| `retrieval_20260928-152736` | dense search, with 0 / 2 / 1 chunk per card | recall@5 0.85, MRR 0.79–0.81: the per-card limit adds variety, not recall |
| `retrieval_20260928-153546` | dense, BM25, hybrid RRF (2 and 1 per card) | BM25 0.90 but fails English questions; hybrid RRF 1/card 0.90 |
| `retrieval_20260928-154042` | RRF variants and interleave fusion | interleave: recall@1 0.75, recall@5 0.95, MRR 0.84 (RRF k0=60 0.90 / 0.80) |
| `retrieval_20260928-154233` | final comparison, offline (cached vectors) | chosen default: hybrid interleave, 1 chunk per card |
| `retrieval_20260929-143911` | the same, after re-ingesting two cards saved with LF instead of CRLF line endings | every metric identical (hybrid interleave: recall@1 0.75, recall@5 0.95, MRR 0.84) |
| `retrieval_20260929-153722` | the same, after rebuilding the retrieval as a datapizza `DagPipeline` | identical to the run above, every metric and every question |

## Agent, deterministic checks (`scripts/eval_agent.py`)

"Pass" = answers passing every automatic check, with the checks of that day (later checks, e.g. the
answer language, are stricter).

| Run | Model | Questions | Pass | What it shows |
|---|---|---|---|---|
| `agent_20260928-160112` | gpt-4o-mini | 8 | 4 | first agent: category filter hid the right card, citations copied as headers |
| `agent_20260928-160918` | gpt-4o-mini | 8 | 6 | filter as a preference; author references used as citations |
| `agent_20260928-162748` | gpt-4o-mini | 8 | 5 | a coach name from the model's memory → grounding check |
| `agent_20260928-163729` | gpt-4o-mini | 44 | 27 | first full run (30 after fixing checker false alarms); English questions answered in Italian |
| `agent_20260928-171548` | gpt-4.1-mini | 44 | 29 | model A/B: more complete facts, worse on traps and format |
| `agent_20260928-172539` | gpt-4o-mini | 44 | 25 | last prompt round: no gain (English still 0/6) |
| `agent_20260928-175508` | gpt-4o-mini + guardrails | 44 | 31 | guardrails: English 6/6, 12 answers rewritten |
| `agent_20260928-175811` | gpt-4o-mini + guardrails | 4 | 2 | targeted check of the "Non lo so" instruction of the rewrite |
| `agent_20260928-180737` | gpt-4.1-mini + guardrails | 44 | 34 | 35 with multi-card citations accepted; fails the trap Q18 |
| `agent_20260929-104445` | gpt-4o-mini + guardrails | 1 (two turns) | 0 | `--follow-up`: Q37 asked right after Q13 in one conversation; it consulted the expected card, but did not use the previous turn (no 4-3-3 in the answer) |
| `agent_20260929-112013` | gpt-4o-mini + guardrails | 44 + two turns | 34 + 0/1 | prompt: advice tailored to the coach's own description. Q13 now builds on "la tua formazione 4-3-3"; Q37 still does not name it. +Q01, Q02, Q21, Q34, −Q38 (mostly required-facts variance); 10 answers rewritten, no invented name left |
| `agent_20261009-105701` | gpt-4o-mini + guardrails, no verifier | 5 known-error questions (Q12, Q18, Q31, Q35, Q37 after Q13) | 3/5 | Q35 states an invented PPDA threshold ("inferiore a 10 indica un pressing d'élite", E5) and passes every check; Q37 gets the roles right this time |
| `agent_20261009-105844` | the same + verifier gpt-4.1-mini | the same 5 | 4/5 | the verifier catches E5 (rewritten to "Non lo so" + the cards' values) and Lahm stays in Q31 (E9); it misses E2 in Q37 ("l'Atalanta ha sfruttato il pressing a uomo del Leverkusen"): it quoted the right sentence as evidence and called it supported. Rechecked apart: caught 4/4; with the roles written out before the verdict, 10/10 as expected (E2 5/5, no false alarm on the right version 3/3, E5 2/2), 0.0036 $ per check |
| `agent_20261014-122917` | gpt-4o-mini + guardrails, real case written by code (branch `known-errors`, step 1) | 9 advice and case questions (Q05, Q09, Q12, Q13, Q14, Q33, Q36, Q37, Q42) | 7/9 | every real-case line is the card's own sentence, roles right (Q37: "il Leverkusen, pressato a uomo dall'Atalanta", E2); Q42 in English keeps the card text in Italian under "Real case (card text, in Italian)". The 2 failures are required facts (Q05 1/3, Q09 3/4), not real cases |
| `agent_20261014-124425` | the same + coach-team pairs and thresholds (step 2) | 4 known-error questions (Q12, Q18, Q21, Q35) | 3/4 | Q35's threshold ("PPDA inferiore a 10 indica un pressing d'élite", E5) caught and rewritten to "Non lo so" + the cards' values; Q21: "allenato da Luis Enrique" caught by the grounding check, rewritten to "un allenatore non specificato" instead of "Non lo so" (fail); no "Atalanta di Italiano" (Q12), no "Milan di Pioli" (Q18) |
| `agent_20261014-124545` | the same, again | the same 4 | 4/4 | Q35's threshold caught twice in one answer and rewritten to "Non lo so" + the cards' values (Conte's Inter 9.08, De Zerbi's Sassuolo 10.30); Q21 answers "Non lo so" on PSG's coach |
| `agent_20261014-134700` | the same + greeting rule (E14), English titles are not names (E16) (step 4) | Q13 and the 4 English questions (Q39-Q42) | 5/5 | no title word flagged in the English answers (bold labels in Q41, Q42); the 4 English answers still drafted in Italian and rewritten by the language check, as before (`-122917` Q42). Then, by hand: "ciao, quali sono i moduli migliori nel calcio di oggi?" searched (`glossary_moduli` first) and passed the output guard (E14); "What if we went down to 10 at the 90th?" answered by code, no model call |
| `agent_20261014-135939` | the same + step 5: English reminder, closing summary removed, prompt rules on embellishments, "secondo X" and one team's details (E18), "il suo Milan" | 17 questions with unsupported statements in gold `-112356` (Q02, Q03, Q05, Q11, Q12, Q15, Q25, Q27, Q28, Q31, Q35) + Q18 + Q34, Q39-Q42 | 12/17 saved, 13/17 rechecked (Q42's "Italian" was the real-case label, a false alarm of the evaluation, fixed) | the 4 English answers drafted in English, no language rewrite (23 of 23 before); Q03's closing summary removed; Q35's threshold caught again. Effects added to cited facts still there in some answers (Q25 "aumentando la fluidità", Q39 "leading to a more dominant style"). Fails: Q02 "fasce" for "fascia" (E10), Q11 3-0 missing (E8, and two card ids in parentheses), Q27 season labels kept by the rewrite, Q31 Lahm and Bayern dropped by the rewrite with the first names the draft added (E9). Against `agent_20260929-112013` on the same 17: 12 -> 13 |

## Gold runs (`scripts/gold_run.py`, 41 questions, LLM judge)

| Run | Answers from | Judge | Faithfulness method | Result |
|---|---|---|---|---|
| `gold_20260928-215839` | live gpt-4o-mini + guardrails | gpt-4o-mini | holistic | recall@5 0.95, MRR 0.84, abstention 3/3, p50 5.0 s / p95 10.1 s, 0.05 $ + 0.027 $ judge; faithfulness 1.00 on all 38, known-wrong answers included |
| `gold_20260928-220924` | replay of `agent_20260928-180737` | gpt-4.1-mini | holistic | faithfulness 1.00 on all 38 again: the one-score judge does not work |
| `gold_20260928-222641` | replay of `agent_20260928-180737` | gpt-4o-mini | claims | faithfulness 0.91; catches the invented PPDA threshold (Q35) and a wrong attribution (Q12), misses Q18; false alarms on the coach's own premise |
| `gold_20260929-094225` | replay of `agent_20260928-180737` | gpt-4o-mini | claims (judge sees the question) | premise false alarms gone; still misses Q18 (0.94) and Q12 |
| `gold_20260929-094857` | replay of `agent_20260928-180737` | gpt-4.1-mini | claims | Q18 0.00 (every sentence attributing the thesis to "his Milan"), Q12 caught → **chosen judge** |
| `gold_20260929-095710` | replay of `agent_20260928-175508` | gpt-4.1-mini | claims | superseded: a cut judge answer (Q27) counted as 0 and a relevancy of 0 on Q17 ("the 2026 World Cup has not happened yet") |
| `gold_20260929-100809` | replay of `agent_20260928-175508` (gpt-4o-mini) | gpt-4.1-mini | claims, fixed judge | **final, agent gpt-4o-mini**: faithfulness 0.910, relevancy 0.934, score 0.922 (1 judge error left out) |
| `gold_20260929-101444` | replay of `agent_20260928-180737` (gpt-4.1-mini) | gpt-4.1-mini | claims, fixed judge | **final, agent gpt-4.1-mini**: faithfulness 0.914, relevancy 0.980, score 0.947; Q18 0.00 |
| `gold_20260929-101624` | replay of `agent_20260928-180737`, 8 known questions | gpt-4.1 | claims | judge check: catches Q18, Q12 and Q35's invented threshold (missed by gpt-4.1-mini), fewer false alarms; 0.16 $ for 8 questions (≈ 0.75 $ a full run vs ≈ 0.13 $) |
| `gold_20260929-110927` | replay of `agent_20260928-175508`, Q17 only | gpt-4.1-mini | claims | judge cache check, first run: 3 judge calls, 0.0020 $, 6.9 s |
| `gold_20260929-110935` | the same, again | gpt-4.1-mini | claims | judge cache check, second run: the same verdicts, 3 calls answered by the cache, 0 $, 0.02 s |
| `gold_20261009-112356` | live gpt-4o-mini + guardrails (tag verifier-off) | gpt-4.1-mini | claims | **current reference**: faithfulness 0.923, relevancy 0.974, abstention 3/3, recall@5 0.95, MRR 0.84, p50 4.1 s / p95 7.2 s, 0.0012 $ per answer. With the changes since 2026-09-29 (prompt tailored to the coach, input guard, E9 rewrite instruction) |
| `gold_20261009-114805` | the same + verifier gpt-4.1-mini with roles (tag verifier-on) | gpt-4.1-mini | claims | faithfulness 0.949 (+0.025), relevancy 0.966, p50 17.7 s / p95 32.3 s, 0.0064 $ per answer: **under the acceptance gate** (+0.03 required; latency and cost far over budget), and the judge shares the verifier's model and method, so the gain is if anything overrated. 9 questions better, 5 worse; Q35's threshold softened by the rewrite but still there. Verifier kept, off by default (`--verifier`) |

Chosen: agent **gpt-4o-mini** (same faithfulness as gpt-4.1-mini at about a third of the cost, and no
wrong attribution on the trap Q18), judge **gpt-4.1-mini** for routine runs, checked against gpt-4.1.
Verifier (2026-10-09): not adopted by default, under the gate on faithfulness gain, latency and cost (`gold_20261009-114805` vs `-112356`).
