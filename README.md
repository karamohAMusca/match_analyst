# Match Analyst AI ⚽

An assistant coach built with **`datapizza-ai v0.1.0`** (AITHO GenAI Academy final project).
The coach describes their own team and the opponent; the assistant helps prepare the match and handle
in-game situations, with advice **grounded in cited sources** (Coverciano theses, recent finals,
match data), giving priority to recent (2022–2026) winning tactics. Questions in Italian or English.

> **Status:** knowledge base, evaluation set, hybrid retrieval and the agent with its corpus
> tools are ready. Guardrail, observability, full evaluation and UI are being built (course
> milestones S12–S15).

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
│   ├── core/               # paths and settings from .env
│   ├── corpus/             # read cards and manifest, split cards into chunks (offline)
│   ├── rag/                # Qdrant store, ingestion, hybrid retrieval (dense + BM25)
│   ├── evaluation/         # metrics against the gold set
│   ├── tools/              # agent tools: search_cards, read_card
│   └── agent/              # datapizza-ai agent and system prompt
├── scripts/                # ingest, eval_retrieval, build_manifest, check_corpus, sb_match_report
├── tests/                  # offline checks (corpus, gold set, retrieval, tools, agent loop)
├── docker-compose.yml      # Qdrant vector store
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

### Chat with the agent (uses the OpenAI API)

The agent (gpt-4o-mini) searches the cards with its tools (`search_cards`, `read_card`), answers
only from the passages it retrieved, cites every claim with its `[document_id]`, and says
"Non lo so" when the cards do not cover the question. Needs Qdrant running and the index built.

```bash
python interactive_cli.py                                   # conversation, follow-ups work
python interactive_cli.py "Come preparo una partita contro un 4-4-2 basso?"   # one question
```

After each answer the CLI lists the cards the agent consulted.

To check answers automatically on a set of gold questions (citations only to consulted cards,
correct tool use, "Non lo so" when required, required facts; ~$0.02 for the default 8 questions):

```bash
python -m scripts.eval_agent            # or --ids Q13,Q18, or --all; --model gpt-4.1-mini to compare models
```

---

## Data and licences

Theses are public FIGC documents (not redistributed: download them from the URLs in `SOURCES.md`).
Wikipedia extracts are CC BY-SA 4.0. Match statistics computed from **StatsBomb Open Data**
(data provided by StatsBomb; raw data not redistributed). FIFA match reports are public documents.
