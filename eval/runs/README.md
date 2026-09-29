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

Chosen: agent **gpt-4o-mini** (same faithfulness as gpt-4.1-mini at about a third of the cost, and no
wrong attribution on the trap Q18), judge **gpt-4.1-mini** for routine runs, checked against gpt-4.1.
