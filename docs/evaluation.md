# Gold run: the whole system judged by an LLM


```bash
python -m scripts.gold_run --tag baseline              # ~$0.2 with gpt-4o-mini
python -m scripts.gold_run --tag gpt41 --model gpt-4.1-mini
python -m scripts.gold_run --tag verifier-on --verifier      # with the verifier (off by default)
python -m scripts.gold_run --rejudge eval/runs/agent_20260928-180737.json --judge-model gpt-4.1-mini
```

The same gold set, one table of metrics: recall@1, recall@5 and MRR of the first expected card,
faithfulness and relevancy given by an LLM judge with typed outputs, abstention on out-of-corpus
questions, latency p50/p95, cost per query and of the run, and one score,
(faithfulness + relevancy) / 2. Faithfulness is judged claim by claim, as in RAGAS: the answer is
split into statements, each is checked against the cards the agent consulted, and the score is
the share of supported statements; the statements that are not supported are listed. (A single
score per answer, `--faithfulness holistic`, gave 1.0 to answers we know are wrong.) The detail
marks the questions below 0.7, and a reminder maps each low metric to what to try. Off-topic, greeting and follow-up questions test the
guardrails and the conversation and stay in `eval_agent`. With Phoenix running, the run is one
trace, `gold_run <tag>`, with every question inside. Runs are saved as `eval/runs/gold_<time>.json`.
`--rejudge` judges the saved answers of an earlier run again (on the cards that run consulted), to
compare judges on exactly the same answers: a judge is trusted only if it catches the answers we
know are wrong. The default judge is gpt-4.1-mini; a judge error is left out of the averages and
counted. Every run is listed in [`eval/runs/README.md`](../eval/runs/README.md).
The judge's verdicts are saved in `.cache/`: its client gets a disk cache with datapizza's `Cache`
interface (`src/core/disk_cache.py`), and datapizza looks every call up there before asking the
model. Judging the same answer again with the same judge costs nothing, so a `--rejudge` stopped
halfway starts again without paying what it already judged; the "judge cost" line says how many
calls the cache answered, and `--no-judge-cache` asks the judge again (e.g. to see how much its
verdicts vary). The clients of the agent and of the judge are built by datapizza's `ClientFactory`.

## Results (41 questions, answers with guardrails on, judge gpt-4.1-mini)

| Agent model | Faithfulness | Relevancy | Score | Abstention out of corpus | Trap Q18 (thesis attributed to a later team) |
|---|---|---|---|---|---|
| **gpt-4o-mini** (default) | 0.910 | 0.934 | 0.922 | 2/3 | 0.78 |
| gpt-4.1-mini | 0.914 | 0.980 | 0.947 | 2/3 | 0.00 |

Retrieval on the same questions: recall@1 0.76, recall@5 0.95, MRR 0.84. Live run with gpt-4o-mini:
latency p50 5.0 s / p95 10.1 s, about 0.0012 $ per answer. gpt-4o-mini is the default: the same
faithfulness at about a third of the cost, and no wrong attribution on the trap question;
gpt-4.1-mini gives more complete answers and can be chosen in the app.

**Final run** (live run `gold_20261021-111545`, gpt-4o-mini with guardrails, after the fixes of the
errors in `eval/error_log.md`) against the reference of 2026-10-09 (`gold_20261009-112356`, before
them), same judge, same agent model:

| Metric | Reference 2026-10-09 | Final 2026-10-21 | Rule of acceptance |
|---|---|---|---|
| faithfulness | 0.923 | **0.958** (+0.035) | at least +0.03 and at least 0.85: passes |
| relevancy | 0.974 | 0.926 (−0.047) | lower, see below |
| abstention out of corpus | 3/3 | 3/3 | — |
| recall@5 / MRR | 0.95 / 0.84 | 0.95 / 0.84 | at most −0.02: passes (retrieval untouched) |
| latency p50 / p95 | 4.1 s / 7.2 s | 4.8 s / 9.0 s | p95 about 10 s: passes |
| cost per answer | 0.0012 $ | 0.0011 $ | within budget |

The runs in between (`-141635`, `-143834`, `-145440`, `eval/runs/README.md`) show the gain step by
step: 0.944, 0.946, 0.953, 0.958. The first of them also showed what a fix can break: the abstention
fell to 2/3 until a missing detail said without "Non lo so" got the words by code (E19).
With the verifier (`-114805`, before these fixes): faithfulness 0.949, relevancy 0.966, p95 32.3 s,
0.0064 $ per answer, so it stays off by default.

**What the numbers do not say.** The gold set holds few of the errors found in the app (the real
case, the side of a game situation, the greeting, the premise): they are checked by tests on the
saved answers and in the app, not by this table. Faithfulness moved by +0.035 while 20 errors were
fixed. The relevancy fell because of a few right answers marked down, not because answers got
worse: Q35 asks for a PPDA threshold that the cards do not give and the answer says "Non lo so"
(the reference answered with an invented threshold and had 1.0), Q07 and Q32 leave a half
unanswered or do not name the source. Known limits, in the error log: a source conflict left out
(E7), questions on two cards answered with one (E8), a role taken from the question (E15), and the
relevancy judge, which rewards an answer that sounds complete.

**Choosing the judge**, on answers whose errors are known (runs `gold_20260929-094225`, `-094857`,
`-101624`):

| Judge | Catches the known errors (Q18, Q12, Q35) | False alarms on correct answers | Cost of one full judgement |
|---|---|---|---|
| gpt-4o-mini, one score per answer | 0 of 3 (1.0 to every answer) | — | ≈ 0.03 $ |
| gpt-4o-mini, claim by claim | at most 1 of 3, not stable between runs | several | ≈ 0.05 $ |
| **gpt-4.1-mini**, claim by claim | 2 of 3 (misses the invented threshold of Q35) | few | ≈ 0.13 $ |
| gpt-4.1, claim by claim | 3 of 3 | fewest | ≈ 0.75 $ |

gpt-4.1 is the best judge but costs about six times more: routine runs use gpt-4.1-mini, and its
limits are known. Two more limits of the judge: an omission (a source conflict left out, Q17) is
not seen statement by statement, and it is covered by the required-facts check of `eval_agent`;
gpt-4.1-mini judging its own answers may favour them slightly, which would only overrate the model
we did not choose. A judge from another provider (`--judge-provider`, e.g. `anthropic`) would
remove that doubt: not tried, it needs that provider's datapizza client package and its key in `.env`.
