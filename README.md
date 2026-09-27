# Match Analyst AI ⚽

An assistant coach built with **`datapizza-ai v0.1.0`** (AITHO GenAI Academy final project).
The coach describes their own team and the opponent; the assistant helps prepare the match and handle
in-game situations, with advice **grounded in cited sources** (Coverciano theses, recent finals,
match data), giving priority to recent (2022–2026) winning tactics. Questions in Italian or English.

> **Status:** knowledge base, evaluation set and maintenance tooling are ready. Retrieval tool,
> guardrail, observability and UI are being built (course milestones S12–S15).

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
├── eval/gold_set.json      # 45 evaluation questions (it + paired en)
├── src/
│   ├── config.py           # paths and settings from .env
│   ├── agent/              # datapizza-ai agent and system prompt
│   └── rag/corpus.py       # card / manifest loading
├── scripts/                # maintenance: build_manifest, check_corpus, sb_match_report
├── tests/                  # offline checks (corpus, manifest, gold set)
└── interactive_cli.py      # chat with the agent from the terminal
```

---

## Getting started

Prerequisites: Python ≥ 3.10; an OpenAI API key only for the agent (not for tests and scripts).

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

### Chat with the agent (uses the OpenAI API)

```bash
python interactive_cli.py
```

---

## Data and licences

Theses are public FIGC documents (not redistributed: download them from the URLs in `SOURCES.md`).
Wikipedia extracts are CC BY-SA 4.0. Match statistics computed from **StatsBomb Open Data**
(data provided by StatsBomb; raw data not redistributed). FIFA match reports are public documents.
