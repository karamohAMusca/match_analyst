# Setup, corpus and offline checks

Everything that needs no model: the offline tests, the corpus, the index, the retrieval measure and the check from a clean install. The quick start is in the [README](../README.md#quick-start).

## Offline checks (no API key, no network)

```bash
python -m pytest                   # corpus, retrieval, agent loop (fake model), guardrails, evaluation, app, MCP server
python -m pytest --cov=src --cov=scripts --cov-report=term-missing   # which lines the tests never run
python -m scripts.check_corpus     # quotes and cited pages vs references/ (needs the PDFs in references/theses), and nothing in a card that acts as an instruction
```

Coverage is read, not just accepted: the core (retrieval, tools, guardrails, judge, gold run) is
at 96–100%; what stays uncovered is the code that talks to Qdrant, OpenAI or Phoenix, checked by
running the project. Line coverage does not test the limits, so the thresholds (question length,
follow-up words, advice words) have tests on the exact value.

## Maintaining the corpus

After adding or editing a card, regenerate the manifest and re-run the tests:

```bash
python -m scripts.build_manifest
python -m pytest
```

Writing rules for cards are in [`references/SOURCES.md`](../references/SOURCES.md).
The manifest stores the SHA-256 of each card's bytes, so line endings matter: `.gitattributes` makes
git check out every text file with LF line endings, also on Windows (with CRLF, a clone would see
every card as changed, in the tests and in the ingestion).

## Building the index (Qdrant + OpenAI embeddings)

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

## Measuring retrieval on the gold set

```bash
python -m scripts.eval_retrieval
```

Retrieval is hybrid: dense search (Qdrant) + BM25 keyword search, fused into one ranking, at most
1 chunk per card. The script compares dense, BM25 and hybrid variants on recall@1, recall@5 and
MRR@10 (the standard definitions), also by question type and language; each run is saved in `eval/runs/`.
Question vectors are cached in `.cache/`: the first run embeds them in one call (well under
$0.001), later runs are free, and `python -m scripts.eval_retrieval --offline` needs no API key.

## Checks from a clean install

**Tracked files only (2026-11-06, version 1.5).** The repository cloned into a new folder and the offline
tests run there with the project's environment: 937 passed and 45 skipped, all of them tests of data that git
does not hold (the raw StatsBomb events and what is derived from them for the goal actions and the shot map).
`pip check` found no broken requirement, `check_corpus` 0 problems out of 31 cards (in the working copy, which
has the PDFs of the sources), and no file that must stay local (`.env`, PDFs, chats, logs, StatsBomb data) is tracked.

**Final version (2026-10-21).** The `develop` branch cloned into a new folder outside OneDrive, with a
fresh Python 3.12 environment, a copy of `.env` and the Qdrant of the project already running (a
second `docker compose` would clash with its containers): `pip install -r requirements.txt` without
errors (including `mcp` 2.x and Streamlit), `ingest` found the 31 cards unchanged (0 chunks embedded,
113 points in the collection), the CLI answered a preparation question with citations, the real case
written from the card and the guardrail's note, with a trace in Phoenix, and the app answered a
conversation of three questions: preparation, "and if we were down to 10?" (answered by code, no
model call) and an off-topic one (stopped). The offline tests (720) passed on the same commit in the
project's own environment; the retrieval numbers were not measured again in the clone. The
check ended by deleting the clone, which held a copy of the key.

**First check (2026-09-29).** The whole project, cloned into a new folder on Windows with a fresh
Python 3.12 environment and following the setup of the README step by step: `pip install -r requirements.txt` without errors, 571 offline
tests passed, `ingest --dry-run` 31 cards / 113 chunks, `ingest` found every card unchanged (0
chunks embedded), `eval_retrieval` gave the same numbers from an empty cache (hybrid interleave:
recall@1 0.75, recall@5 0.95, MRR 0.84), the CLI answered with citations and a trace in Phoenix,
and the app worked with a two-turn conversation (the first answer builds on "your 4-3-3").
The check had first found one problem, fixed before it: with Windows line endings in a clone every
card looked changed, see [Maintaining the corpus](#maintaining-the-corpus).

What the app's second turn showed then, and the automatic checks did not see (the guardrails
checked names, numbers and citations, not who did what; both errors are fixed since, E1 and E6):
- **an invented premise**: to "and if we were down to 10 men at the 90th minute?" it answered
  "defend your lead", which the coach never said;
- **a real case with the roles swapped**: "Inter defended a lead in the 2023 Champions League
  final", while the card says City won 1-0 and Inter was chasing the game (the same kind of error
  as Q37: Atalanta's man-to-man press attributed to Leverkusen).
The claim-by-claim judge of the gold run is the check that catches this kind of error. Every
error found is collected, with its source and the candidate fixes, in
[`eval/error_log.md`](../eval/error_log.md).
