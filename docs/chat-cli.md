# Chat with the agent from the terminal (uses the OpenAI API)


The agent (gpt-4o-mini) searches the cards with its tools (`search_cards`, `read_card`), answers
only from the passages it retrieved, cites every claim with its `[document_id]`, and says
"Non lo so" when the cards do not cover the question. Needs Qdrant running and the index built.

```bash
python interactive_cli.py                                   # conversation, follow-ups work
python interactive_cli.py "Come preparo una partita contro un 4-4-2 basso?"   # one question
```

After each answer the CLI lists the cards the agent consulted and, when they intervened, what the
guardrails did.

**Guardrails** (`src/guardrails/`, code that prevents instead of a prompt that asks):
- *input*: prompt-injection attempts, off-topic and oversized questions get a fixed reply and
  never reach the model; greetings get the presentation without a model call (a greeting followed by
  a football question is a football question, E14);
- *output*: the answer must be in the language of the question, its names and numbers must appear
  in the consulted cards (in an English answer, the Title Case words of headings and bold labels are
  not names, E16; their numbers are still checked), and it must cite `[card_id]`s it actually consulted. On a problem the
  model gets a precise note and rewrites the answer once; the rewrite is kept only if it is not
  worse, and what happened is always reported;
- *real case* (`src/guardrails/real_case.py` and the other modules of `facts.py`, no model call): the real match of an advice answer is where
  roles got swapped ("Inter defended a lead in the 2023 final", "Leverkusen's man-to-man press"),
  with every name in the cards. The model now writes only `Caso reale: [case_id]`, and the code writes
  the facts with the card's own sentence on that final (the line of a consulted game-situation card
  that cites it, else the match card's outcome), so its roles cannot be swapped. A line about
  something else (a match of a thesis, a season of a coach) that cites a consulted card stays as
  written and is checked like any sentence; a final no consulted card speaks of is removed.
  **Coach-team pairs** ("the Atalanta of Italiano", "PSG was coached by Scaloni") must be in the cards
  (the team in the coach's card, or the pair of a final), and **thresholds** about a metric ("PPDA
  below 10") must be written in them. **The side** of a game situation: if the coach says "we are down
  to ten" (or behind, or ahead), the card written for the other side (playing 11 v 10, defending a
  lead, coming back) may only describe the opponent's moves, never be the coach's own advice (E17).
  With **a man down**, which has no card, and no score given, the answer is written by code: "Non lo so" for the advice,
  the options of the 11 v 10 card as what the opponent will try (its own words, with a note that
  there "the opponent" is the coach's team), and a real case from the side that was down to ten
  (Argentina in the 2026 final), with no model call. A **score the coach never gave** ("keep your
  lead" when no score was mentioned) is not taken for granted (E6).
  A wrong fact goes into the single rewrite; if it is still there, the sentence is removed. On every saved answer of the real runs (766), the facts flagged are exactly
  the known errors (E3, E4, E5).
  A **closing summary** with no citation ("Queste regole aiutano a mantenere l'equilibrio", "In
  sintesi..."), the most frequent unsupported statement of the reference gold run, is removed: it
  carries no cited fact (a style question's conclusion, "X is the closest to your team", is kept).
  An English question reaches the model with a one-line reminder to answer in English: with the
  rule of the system prompt alone, every English answer was drafted in Italian and rewritten.
  A name the cards write only in part ("Philipp Lahm", "Bayern Monaco") is cut back to their words
  by code, before the checks: asked to the rewrite, the whole name went, Lahm included (E9). A detail
  said to be missing without the words "Non lo so" ("un allenatore non specificato") gets them (E19).
  An **effect added after a comma** ("..., creando opportunità di tiro", "..., evidenziando un pressing
  molto efficace"), the writer's reading and not the card's, is cut (E20); a tail with a number or a
  name stays. Simulated on the judge's verdicts of two gold runs, it raised faithfulness by 0.011 and
  0.019, no required fact lost; it also cuts some right tails, so answers get shorter.
- *verifier*, optional (`src/guardrails/verifier.py`, a second model after the writer: a sequential
  architecture): the checks above see names, numbers and citations, not who did what ("Inter
  defended a lead" passes them, while the card says City won). The verifier runs the gold run's
  claim-by-claim check at answer time, writing who does what to whom in each statement and in its
  evidence before deciding; each unsupported statement goes into the same single rewrite, with what
  the cards say. **Off by default** (`--verifier` in `eval_agent` and `gold_run`): measured on the
  gold set it raised faithfulness from 0.923 to 0.949, under the +0.03 the acceptance gate requires,
  for 5 times the cost (0.0064 $ per answer) and 4 times the latency (p95 32 s). On the known
  errors it works (it catches the swapped roles of E2 and the invented threshold of E5), but a
  single check is not stable: in one run it quoted the right sentence and called the wrong one
  supported (see `eval/error_log.md`).

To check answers automatically on a set of gold questions (citations only to consulted cards,
grounding, language, correct tool use, "Non lo so" when required, required facts; ~$0.02 for
the default 8 questions):

```bash
python -m scripts.eval_agent            # or --ids Q13,Q18, or --all
python -m scripts.eval_agent --all --no-guardrails     # bare agent, to measure the guardrails
python -m scripts.eval_agent --all --model gpt-4.1-mini   # another model
python -m scripts.eval_agent --follow-up                  # two turns: conversation memory
```

`--follow-up` measures the conversation memory: a follow-up question of the gold set ("E se invece
ci pressano alti a uomo?") is asked right after its previous turn ("...noi giochiamo 4-3-3, come
la prepariamo?") in the same conversation; besides the usual checks, the expected card must be
consulted and the answer must use the previous turn.
Result (run `agent_20260929-112013`): the memory works, the follow-up is understood and the expected
card is found. The prompt now tailors the advice to what the coach wrote about their own team, so
the first turn builds on "your 4-3-3". **Known limit:** in the second turn, facing a new situation,
the model reasons about that situation and does not always bring back the coach's formation.
