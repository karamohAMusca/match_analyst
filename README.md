# Match Analyst AI ⚽

An assistant coach built with **`datapizza-ai v0.1.0`** (AITHO GenAI Academy final project).
The coach describes their own team and the opponent; the assistant helps prepare the match and handle
in-game situations, with advice **grounded in cited sources** (Coverciano theses, recent finals,
match data), giving priority to recent (2022–2026) winning tactics. Questions in Italian or English.

**What it does** (version 1.6, complete):
- **RAG** on 31 cards, with hybrid retrieval (dense + BM25) on Qdrant; an **agent** that searches and reads the cards, with a compact conversation **memory**.
- **Guardrails** in and out: off-topic questions and injections stopped, every claim checked against the cards it cites, personal data hidden before the model, no external link or image in an answer (20 errors found and fixed, in [`eval/error_log.md`](eval/error_log.md); 13 attacks in a frozen red team).
- A **Streamlit app** that draws graphics under an answer (formations, timeline, numbers and shots of a final, the action of every goal), **traces** in Phoenix, and the knowledge base as an **MCP server** for Claude Desktop and other hosts.
- **Evaluated** by an LLM judge on 41 questions: faithfulness 0.958, relevancy 0.926, abstention 3/3, recall@5 0.95, p95 9.0 s, 0.0011 $ per answer ([results](docs/evaluation.md#results-41-questions-answers-with-guardrails-on-judge-gpt-41-mini)); no regression after the security work (2026-11-06: faithfulness 0.960).

---

## Quick start

Prerequisites: Python ≥ 3.10; Docker Desktop (for Qdrant and Phoenix); an OpenAI API key for the index and the agent (not for the tests).

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env; then add OPENAI_API_KEY
python -m pytest                   # offline: no key, no network
docker compose up -d               # Qdrant on localhost:6337 and Phoenix on :6006
python -m scripts.ingest           # embed the 31 cards (about $0.0003)
python -m scripts.start            # Qdrant + Phoenix + the app, then open the page it prints
```

**On Windows**, the pitfalls of a clean install:
- **Python**: install it with `winget install Python.Python.3.12 --source winget` (or the "Windows installer (64-bit)" from python.org, with "Add python.exe to PATH" ticked), then reopen PowerShell and create the environment with `py -3.12 -m venv .venv`. The *embeddable* zip does not work: it has no `pip` and no `venv`. "Python was not found; run without arguments to install from the Microsoft Store" only means that Python is not installed yet.
- **Activating the environment is blocked**: run `Set-ExecutionPolicy -Scope Process RemoteSigned` first. Once active, the prompt starts with `(.venv)`.
- **`No module named 'dotenv'`** (or any other package): the environment is not active, or `pip install` stopped before the end. Activate it and install again.
- **`UnicodeEncodeError: 'ascii' codec can't encode character`** on the first call to OpenAI: a value in `.env` holds a character that is not ASCII, usually a key pasted with a stray character. Paste it again by hand, with no quotes and no spaces.
- **Docker**: Docker Desktop must be open and show "Engine running" before `docker compose up -d`.

### Goal animations and shot maps (optional, one-time)

The app animates the goals and draws the shots of two finals (World Cup 2022, Euro 2024) from
StatsBomb event data. Its licence forbids redistributing the raw data, so the events are not in this
repository: **without these two commands the app shows no goal animation and no shot map** (everything
else works). The first downloads the events of the two matches, the second builds the file the app draws
(no API key); the same commands work in bash and PowerShell:

```bash
python -c "import pathlib, urllib.request as u; d = pathlib.Path('references/data/statsbomb/events'); d.mkdir(parents=True, exist_ok=True); [u.urlretrieve(f'https://raw.githubusercontent.com/statsbomb/open-data/master/data/events/{i}.json', d / f'{i}.json') for i in (3869685, 3943043)]"
python -m scripts.build_goal_actions
```

Then restart the app. Both folders (`references/data/`, `references/derived/`) are git-ignored. If the
download answers 404, use `hudl/open-data` instead of `statsbomb/open-data`.

---

## Guides

| Guide | What it covers |
|---|---|
| [`docs/setup-and-checks.md`](docs/setup-and-checks.md) | offline tests and coverage, maintaining the corpus, building the index, measuring retrieval, the check from a clean install |
| [`docs/app.md`](docs/app.md) | the Streamlit app, the saved chats and the log, tracing with Phoenix |
| [`docs/chat-cli.md`](docs/chat-cli.md) | the chat with the agent from the terminal |
| [`docs/mcp.md`](docs/mcp.md) | the knowledge base as an MCP server, for Claude Desktop and other hosts |
| [`docs/security.md`](docs/security.md) | the red team (attacks and defences), data and privacy, the AI Act hypothesis |
| [`docs/evaluation.md`](docs/evaluation.md) | the gold run judged by an LLM, and its results |
| [`AGENTS.md`](AGENTS.md) | for AI coding agents (Claude Code, GitHub Copilot): context, rules, the procedure for every change |

---

## Project structure

| Path | What it is for |
|---|---|
| `app.py` | the Streamlit app: chat, cards, evaluation results |
| `interactive_cli.py` | the chat with the agent from the terminal |
| `mcp_server.py` | the knowledge base as an MCP server |
| `src/` | the application code, one folder per responsibility (core, corpus, rag, tools, agent, guardrails, observability, evaluation, ui, mcp_server): file by file in [`src/README.md`](src/README.md) |
| `corpus/` | the knowledge base: 31 short cards in Italian (recent finals, game situations, coaches, theses, glossary) and `manifest.json`, their catalogue |
| `references/` | the upstream sources, not ingested; [`SOURCES.md`](references/SOURCES.md): provenance, licences and card-writing rules |
| `eval/` | the frozen yardsticks (`gold_set.json`: 45 questions; `red_team.json`: 13 attacks), every measured run in [`runs/`](eval/runs/README.md), the wrong answers found in `error_log.md` |
| `scripts/` | the commands, run as `python -m scripts.<name>` (the main ones, with what they do, in [`AGENTS.md`](AGENTS.md#1-project-context)) |
| `tests/` | offline tests, no API key and no network |
| `design-system/` | the app's tokens and components as HTML previews ([`design-system/README.md`](design-system/README.md)) |

Created locally and not versioned: `.env` (the key), `.cache/` (embeddings and judge verdicts
already paid for), `qdrant_storage/` (the index), `chats/` and `logs/`.

---

## Built with

The project was designed and written by Gaetano Cultrera with AI coding assistants, used on purpose
and with the same rules for each:

| Assistant | What it reads | Used for |
|---|---|---|
| **Claude Code** (Anthropic) | [`CLAUDE.md`](CLAUDE.md), which imports `AGENTS.md`; `.claude/` (rules for the Python files, the `/refactor-by-criteria` command, the `chat-graphic` skill) | code, refactoring, tests, documentation; the commits it wrote carry a `Co-Authored-By: Claude` line |
| **GitHub Copilot** | [`AGENTS.md`](AGENTS.md) and `.github/` (the same rules and command in Copilot's format) | the same project rules, from the editor |
| **Claude Design** | [`design-system/`](design-system/README.md) | the redesign of the app's look (tokens and components) |

[`AGENTS.md`](AGENTS.md) is the one file of instructions for every assistant: project context, rules,
the procedure for every change (baseline, small steps, a check after each) and the constraints, such as
never reading `.env` and never calling the OpenAI API (those commands are run by the author).
`tests/test_agent_instructions.py` fails if the Claude Code and Copilot copies of the rules drift apart.
Whichever assistant makes a change, the offline tests must pass before it is committed.

---

## Privacy

The coach's questions go to OpenAI (keys, emails, phone numbers, IBANs and tax codes are hidden first); the chats stay on this computer in `chats/` (git-ignored; `python -m scripts.prune_chats` lists the old ones); an answer can hold no external link or image; the app tells the coach that it talks to an AI. Where the data goes, the measured attacks, the AI Act hypothesis and the questions for a lawyer are in [`docs/security.md`](docs/security.md#data-and-privacy).

---

## Data and licences

| What | Terms |
|---|---|
| Source code (`src/`, `scripts/`, `tests/`, `app.py`, ...) | No licence is granted: all rights reserved by the author. The repository is public to be read and to show the project |
| Cards (`corpus/`) and Wikipedia extracts (`references/wikipedia/`) | The cards quote and summarise Wikipedia pages, which are CC BY-SA 4.0: the cards and the extracts keep that licence (attribution to the page and revision is in each card's front matter, share-alike for what derives from them) |
| FIGC theses | Public documents of their authors: not redistributed (download them from the URLs in `SOURCES.md`); the cards only quote short passages, each with its page |
| StatsBomb Open Data | Data provided by [StatsBomb](https://github.com/hudl/open-data) under its public data agreement (research and non-commercial use, credit StatsBomb): the raw events and what is derived from them stay local |
| FIFA match reports | Public documents, kept locally |

The app credits StatsBomb in the sidebar, with the logo from StatsBomb's Media Pack
(`src/ui/assets/hudl-statsbomb-logo.png`, a trademark of its owner, used only to credit the data), and in
the caption of every figure drawn from its events (numbers, shots, goal actions).
