# Match Analyst AI ⚽

An assistant coach built with **`datapizza-ai v0.1.0`** (AITHO GenAI Academy final project).
The coach describes their own team and the opponent; the assistant helps prepare the match and handle
in-game situations, with advice **grounded in cited sources** (Coverciano theses, recent finals,
match data), giving priority to recent (2022–2026) winning tactics. Questions in Italian or English.

> **Status:** knowledge base, evaluation set, hybrid retrieval, the agent with its corpus tools,
> the input/output guardrails, tracing in Phoenix and the Streamlit app are ready. The validation
> of the LLM judge is in progress (course milestones S12–S15).

---

## Project structure

```
match_analyst/
├── corpus/                 # RAG knowledge base (ingested) — 31 short cards, in Italian
│   ├── match_cases/        #   recent finals: how the winner won
│   ├── game_situations/    #   in-game / preparation problems: options, risks, cases
│   ├── coach_profiles/     #   one file per coach, merging every source about that coach
│   ├── thesis_notes/       #   concepts from the theses
│   ├── glossary/           #   metrics (PPDA, xG, field tilt…) and formations
│   └── manifest.json       #   catalogue: ids, metadata, SHA-256 (generated)
├── references/             # upstream sources, NOT ingested (theses, Wikipedia, StatsBomb, FIFA)
│   └── SOURCES.md          #   provenance, licences and card-writing rules
├── eval/                   # gold_set.json (45 questions, it + paired en) and runs/ (results)
├── src/                    # application code — file-by-file guide in src/README.md
│   ├── core/               # paths and settings from .env, disk cache (embeddings, judge verdicts)
│   ├── corpus/             # read cards and manifest, split cards into chunks (offline)
│   ├── rag/                # Qdrant store, ingestion, hybrid retrieval (dense + BM25)
│   ├── evaluation/         # metrics against the gold set
│   ├── guardrails/         # input guard (off-topic, injection) and output guard (language, grounding, citations)
│   ├── observability/      # traces in Arize Phoenix (OpenTelemetry → OpenInference)
│   ├── tools/              # agent tools: search_cards, read_card
│   ├── agent/              # datapizza-ai agent and system prompt
│   └── ui/                 # Streamlit app logic: the conversation backend and the formatting
├── scripts/                # ingest, eval_retrieval, eval_agent, gold_run, build_manifest, check_corpus, sb_match_report
├── tests/                  # offline checks (corpus, gold set, retrieval, tools, guardrails, agent loop, app)
├── .streamlit/config.toml  # app theme
├── docker-compose.yml      # Qdrant vector store + Phoenix (traces)
├── app.py                  # Streamlit app: chat, cards, evaluation results
└── interactive_cli.py      # chat with the agent from the terminal
```

---

## Getting started

Prerequisites: Python ≥ 3.10; Docker Desktop (for Qdrant); an OpenAI API key for ingestion and
the agent (not for tests and maintenance scripts).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add OPENAI_API_KEY
```

### Offline checks (no API key, no network)

```bash
python -m pytest                   # corpus, manifest and gold set consistency
python -m scripts.check_corpus     # quotes and cited pages vs references/ (needs the PDFs in references/theses)
```

### Maintaining the corpus

After adding or editing a card, regenerate the manifest and re-run the tests:

```bash
python -m scripts.build_manifest
python -m pytest
```

Writing rules for cards are in [`references/SOURCES.md`](references/SOURCES.md).
The manifest stores the SHA-256 of each card's bytes, so line endings matter: `.gitattributes` makes
git check out every text file with LF line endings, also on Windows (with CRLF, a clone would see
every card as changed, in the tests and in the ingestion).

### Building the index (Qdrant + OpenAI embeddings)

Each card is split into one chunk per `##` section (about 110 chunks); the front matter is stored
as payload, not embedded. The sync is incremental: only new or changed cards are embedded again.

```bash
docker compose up -d                       # start Qdrant on localhost:6337
python -m scripts.ingest --dry-run         # preview chunks and cost (no key, no Qdrant)
python -m scripts.ingest                   # embed and store the cards (about $0.0003)
python -m scripts.ingest --query "Come si attacca un 4-4-2 basso?"   # retrieval check
```

`python -m scripts.ingest --reset` rebuilds the collection from scratch.
Qdrant dashboard: http://localhost:6337/dashboard

### Measuring retrieval on the gold set

```bash
python -m scripts.eval_retrieval
```

Retrieval is hybrid: dense search (Qdrant) + BM25 keyword search, fused into one ranking, at most
1 chunk per card. The script compares dense, BM25 and hybrid variants on recall@1, recall@5 and
MRR@10 (course definitions), also by question type and language; each run is saved in `eval/runs/`.
Question vectors are cached in `.cache/`: the first run embeds them in one call (well under
$0.001), later runs are free, and `python -m scripts.eval_retrieval --offline` needs no API key.

### The app (uses the OpenAI API)

```bash
python -m scripts.start           # Qdrant + Phoenix (Docker), wait until ready, then the app
python -m scripts.start --stop    # stop Qdrant and Phoenix (index and traces are kept)
streamlit run app.py              # only the app, if the services are already running
```

The app opens at http://localhost:8501.

Three tabs. **Chat**: the conversation with the assistant coach (follow-up questions work);
citations appear as badges with the card title, the cards of the answer can be read in full next
to it, and every answer shows what the guardrails did and, under "Dettagli", its time, tokens,
cost and the searches the agent made. The sidebar starts a new conversation, switches model and
guardrails (to show them at work) and has example questions, one in English and one off topic.
**Schede**: the 31 cards by category. **Valutazione**: the measured results of the saved runs
(no API call). With Phoenix running, every question is also a trace.

### Chat with the agent from the terminal (uses the OpenAI API)

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
  never reach the model; greetings get the presentation without a model call;
- *output*: the answer must be in the language of the question, its names and numbers must appear
  in the consulted cards, and it must cite `[card_id]`s it actually consulted. On a problem the
  model gets a precise note and rewrites the answer once; the rewrite is kept only if it is not
  worse, and what happened is always reported.

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

### Gold run: the whole system judged by an LLM

```bash
python -m scripts.gold_run --tag baseline              # ~$0.2 with gpt-4o-mini
python -m scripts.gold_run --tag gpt41 --model gpt-4.1-mini
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
counted. Every run is listed in [`eval/runs/README.md`](eval/runs/README.md).
The judge's verdicts are saved in `.cache/`: its client gets a disk cache with datapizza's `Cache`
interface (`src/core/disk_cache.py`), and datapizza looks every call up there before asking the
model. Judging the same answer again with the same judge costs nothing, so a `--rejudge` stopped
halfway starts again without paying what it already judged; the "judge cost" line says how many
calls the cache answered, and `--no-judge-cache` asks the judge again (e.g. to see how much its
verdicts vary). The clients of the agent and of the judge are built by datapizza's `ClientFactory`.

#### Results (41 questions, answers with guardrails on, judge gpt-4.1-mini)

| Agent model | Faithfulness | Relevancy | Score | Abstention out of corpus | Trap Q18 (thesis attributed to a later team) |
|---|---|---|---|---|---|
| **gpt-4o-mini** (default) | 0.910 | 0.934 | 0.922 | 2/3 | 0.78 |
| gpt-4.1-mini | 0.914 | 0.980 | 0.947 | 2/3 | 0.00 |

Retrieval on the same questions: recall@1 0.76, recall@5 0.95, MRR 0.84. Live run with gpt-4o-mini:
latency p50 5.0 s / p95 10.1 s, about 0.0012 $ per answer. gpt-4o-mini is the default: the same
faithfulness at about a third of the cost, and no wrong attribution on the trap question;
gpt-4.1-mini gives more complete answers and can be chosen in the app.

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

### Tracing with Phoenix

`docker compose up -d` also starts [Arize Phoenix](http://localhost:6006). With Phoenix running,
the CLI and `eval_agent` turn every question into one trace: input guardrail, each agent step,
the searches with the chunks found (card id and score), every model call with its messages and
tokens, the output guardrail and the rewrite with the cards it was given. datapizza-ai emits
OpenTelemetry spans with its own attribute names; `src/observability/tracing.py` translates them
to the OpenInference names Phoenix reads. If Phoenix is not running, tracing is switched off and
the scripts say so; `eval_agent --no-trace` switches it off on purpose.

### First end-to-end check from a clean install (2026-09-29)

The whole project, cloned into a new folder on Windows with a fresh Python 3.12 environment and
following this README step by step: `pip install -r requirements.txt` without errors, 571 offline
tests passed, `ingest --dry-run` 31 cards / 113 chunks, `ingest` found every card unchanged (0
chunks embedded), `eval_retrieval` gave the same numbers from an empty cache (hybrid interleave:
recall@1 0.75, recall@5 0.95, MRR 0.84), the CLI answered with citations and a trace in Phoenix,
and the app worked with a two-turn conversation (the first answer builds on "your 4-3-3").
The check had first found one problem, fixed before it: with Windows line endings in a clone every
card looked changed, see [Maintaining the corpus](#maintaining-the-corpus).

What the app's second turn showed, and the automatic checks do not see (the guardrails check
names, numbers and citations, not who did what):
- **an invented premise**: to "and if we were down to 10 men at the 90th minute?" it answered
  "defend your lead", which the coach never said;
- **a real case with the roles swapped**: "Inter defended a lead in the 2023 Champions League
  final", while the card says City won 1-0 and Inter was chasing the game (the same kind of error
  as Q37: Atalanta's man-to-man press attributed to Leverkusen).
The claim-by-claim judge of the gold run is the check that catches this kind of error.

---

## Data and licences

Theses are public FIGC documents (not redistributed: download them from the URLs in `SOURCES.md`).
Wikipedia extracts are CC BY-SA 4.0. Match statistics computed from **StatsBomb Open Data**
(data provided by StatsBomb; raw data not redistributed). FIFA match reports are public documents.
