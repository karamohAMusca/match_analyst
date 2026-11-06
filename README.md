# Match Analyst AI ⚽

An assistant coach built with **`datapizza-ai v0.1.0`** (AITHO GenAI Academy final project).
The coach describes their own team and the opponent; the assistant helps prepare the match and handle
in-game situations, with advice **grounded in cited sources** (Coverciano theses, recent finals,
match data), giving priority to recent (2022–2026) winning tactics. Questions in Italian or English.

> **Status:** complete: knowledge base, hybrid retrieval, the agent with its corpus tools,
> input/output guardrails (the facts of a real match, coaches and teams, the side of a game
> situation, unsupported additions: 20 errors found and handled, see `eval/error_log.md`),
> conversation memory (compact: only questions and answers, the cards are read again when a follow-up needs them),
> tracing in Phoenix, the Streamlit app with its graphics under an answer (the formations on a pitch, a coach's
> change of shape, the timeline, the numbers and the shots of a final, the action of every goal) and the
> evaluation with an LLM judge. Version 1.6. Security: a frozen red team (13 attacks), no external link or image in an answer, personal data hidden before the model.
> The knowledge base is also an MCP server, usable from Claude Desktop and other hosts. Final
> gold run (2026-10-21): faithfulness 0.958, relevancy 0.926, abstention 3/3, recall@5 0.95,
> p95 9.0 s, 0.0011 $ per answer ([results](docs/evaluation.md#results-41-questions-answers-with-guardrails-on-judge-gpt-41-mini)).

---

## Quick start

Prerequisites: Python ≥ 3.10; Docker Desktop (for Qdrant); an OpenAI API key for the index and the agent (not for the tests).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then add OPENAI_API_KEY
python -m pytest                   # offline: no key, no network
docker compose up -d               # Qdrant on localhost:6337 and Phoenix on :6006
python -m scripts.ingest           # embed the 31 cards (about $0.0003)
python -m scripts.start            # Qdrant + Phoenix + the app, then open the page it prints
```

## Guides

| Guide | What it covers |
|---|---|
| [`docs/setup-and-checks.md`](docs/setup-and-checks.md) | offline tests and coverage, maintaining the corpus, building the index, measuring retrieval, the check from a clean install |
| [`docs/app.md`](docs/app.md) | the Streamlit app, the saved chats and the log, tracing with Phoenix |
| [`docs/chat-cli.md`](docs/chat-cli.md) | the chat with the agent from the terminal |
| [`docs/mcp.md`](docs/mcp.md) | the knowledge base as an MCP server, for Claude Desktop and other hosts |
| [`docs/security.md`](docs/security.md) | the red team (attacks and defences), data and privacy, the AI Act hypothesis |
| [`docs/evaluation.md`](docs/evaluation.md) | the gold run judged by an LLM, and its results |
| [`AGENTS.md`](AGENTS.md) | for AI coding agents: context, rules, the procedure for every change |

---

## Project structure

| Path | What it is for |
|---|---|
| `app.py` | **The Streamlit app**: chat, cards, evaluation results (`python -m scripts.start` starts everything) |
| `interactive_cli.py` | chat with the agent from the terminal |
| `mcp_server.py` | the knowledge base as an MCP server, for Claude Desktop and other hosts ([how to use it](docs/mcp.md)) |
| `src/` | application code, one folder per responsibility; file-by-file guide in [`src/README.md`](src/README.md) |
| `src/core/` | paths and settings from `.env`, disk cache (embeddings, judge verdicts) |
| `src/corpus/` | read cards and manifest, split cards into chunks (offline) |
| `src/rag/` | Qdrant store, ingestion, hybrid retrieval (dense + BM25, a datapizza `DagPipeline`) |
| `src/tools/` | the agent's tools: `search_cards`, `read_card` |
| `src/agent/` | the datapizza-ai agent and its system prompt |
| `src/guardrails/` | input guard (off-topic, injection), output guard (language, grounding, citations, no external link or image) and the facts written or checked by code: real case, coaches and teams, the side of a game situation, additions (`facts.py` and its modules) |
| `src/observability/` | traces in Arize Phoenix (OpenTelemetry → OpenInference) |
| `src/evaluation/` | measuring against the gold set: retrieval metrics, answer checks, LLM judge, gold run, cost |
| `src/ui/` | logic of the Streamlit app: the conversation backend, the formatting, the graphics under an answer, the saved chats |
| `src/mcp_server/` | the MCP server: the corpus as read-only tools, `card://` resources and a prompt |
| `design-system/` | the app's tokens, components and answer states as HTML previews, for redesigning it with Claude Design ([`design-system/README.md`](design-system/README.md)) |
| `docs/` | the guides: setup and checks, the app, the terminal chat, the MCP server, security and privacy, evaluation |
| `corpus/` | the knowledge base (ingested): 31 short cards in Italian, in `match_cases/` (recent finals), `game_situations/` (in-game and preparation problems), `coach_profiles/`, `thesis_notes/`, `glossary/` (metrics and formations) |
| `corpus/manifest.json` | catalogue of the cards: ids, metadata, SHA-256 (generated by `scripts/build_manifest.py`) |
| `references/` | upstream sources, not ingested (theses, Wikipedia, StatsBomb, FIFA); `SOURCES.md`: provenance, licences and card-writing rules |
| `eval/gold_set.json` | the evaluation yardstick: 45 questions, Italian with paired English ones (frozen) |
| `eval/red_team.json` | the security yardstick: 13 attacks and 3 controls (frozen), run by `python -m scripts.red_team` |
| `eval/runs/` | every measured run, listed with its result in [`eval/runs/README.md`](eval/runs/README.md) |
| `eval/error_log.md` | wrong answers found, with their cause and fix |
| `scripts/` | commands run as `python -m scripts.<name>`: `start`, `ingest`, `eval_retrieval`, `eval_agent`, `gold_run`, `build_manifest`, `check_corpus`, `build_goal_actions`, `red_team`, `prune_chats`, `preview_graphics` (run with `streamlit run`), `sb_match_report`, `verify` (the output of a command before and after a refactoring) |
| `tests/` | offline tests, no API key and no network (`python -m pytest`) |
| `docker-compose.yml` | Qdrant (vector store) and Phoenix (traces) |
| `.env.example` | settings template: copy it to `.env` and add the key |
| `requirements.txt` | Python packages |
| `AGENTS.md` | instructions for AI coding agents: project context, rules, the procedure for every change, constraints; one file for every assistant |
| `CLAUDE.md`, `.claude/` | Claude Code: `CLAUDE.md` imports `AGENTS.md`; `rules/` holds the rules for the Python files only, `commands/` a reusable chat command (`/refactor-by-criteria`), `skills/chat-graphic/` the recipe for a graphic under an answer |
| `.github/` | the same two files in the GitHub Copilot format: rules for the Python files only (`instructions/`) and a reusable chat command (`prompts/`) |
| `.streamlit/config.toml`, `pytest.ini`, `.gitattributes` | app theme; test settings; LF line endings on every checkout (the manifest hashes the cards' bytes) |

Created locally and not versioned: `.env` (the key), `.cache/` (embeddings and judge verdicts
already paid for), `qdrant_storage/` (the index).

---

## Data and privacy

The coach's questions go to OpenAI (keys, emails, phone numbers, IBANs and tax codes are hidden first); the chats stay on this computer in `chats/` (git-ignored; `python -m scripts.prune_chats` lists the old ones); an answer can hold no external link or image; the app tells the coach that it talks to an AI. The table of where the data goes, the measured attacks, the AI Act hypothesis and the questions for a lawyer are in [`docs/security.md`](docs/security.md#data-and-privacy).

---

## Data and licences

| What | Terms |
|---|---|
| Source code (`src/`, `scripts/`, `tests/`, `app.py`, ...) | No licence is granted: all rights reserved by the author. The repository is public to be read and to show the project |
| Cards (`corpus/`) and Wikipedia extracts (`references/wikipedia/`) | The cards quote and summarise Wikipedia pages, which are CC BY-SA 4.0: the cards and the extracts keep that licence (attribution to the page and revision is in each card's front matter, share-alike for what derives from them) |
| FIGC theses | Public documents of their authors: not redistributed (download them from the URLs in `SOURCES.md`); the cards only quote short passages, each with its page |
| StatsBomb Open Data | Data provided by [StatsBomb](https://github.com/hudl/open-data) under its public data agreement (research and non-commercial use, credit StatsBomb): the raw events are not redistributed |
| FIFA match reports | Public documents, kept locally |

Match statistics are computed from **StatsBomb Open Data**
(data provided by StatsBomb; raw data not redistributed). The app credits StatsBomb in the sidebar, with the logo from StatsBomb's Media Pack
(`src/ui/assets/hudl-statsbomb-logo.png`, a trademark of its owner, used only to credit the data), and in the caption
of every figure drawn from its events (numbers, shots, goal actions). The goal actions the app animates are derived
from the same events by `python -m scripts.build_goal_actions` and stay local as well
(`references/derived/`, git-ignored): without them the app shows no goal action and no shot map,
everything else works.
