# AGENTS.md — Project Instructions for Match Analyst AI

Instructions for AI coding agents working on `match_analyst`: the project context, the rules to
respect, the procedure to follow for every change, and the constraints. It is the one file for every
coding assistant: Claude Code reads it through `CLAUDE.md` (which imports it), GitHub Copilot directly.
Two more instruction files per assistant work with this one, with the same content: the rules applied
to the Python files only (`.claude/rules/refactor.md`, `.github/instructions/refactor.instructions.md`)
and a reusable command for the chat (`.claude/commands/refactor-by-criteria.md`,
`.github/prompts/refactor-by-criteria.prompt.md`); `tests/test_agent_instructions.py` fails if they differ.

---

## 1. Project Context

`match_analyst` is an assistant coach built as an agentic RAG application:
- The user DESCRIBES their own team and the opponent (no live team data) and asks for match preparation or in-game advice.
- The agent retrieves cited knowledge from a curated card corpus (`corpus/`) stored in a vector store (`Qdrant`).
- Advice must be grounded in retrieved sources, with priority on recent (2022–2026) winning tactics.
- When the corpus does not contain the answer, the agent says so ("Non lo so") instead of inventing facts.

Tech stack:
- **Framework**: `datapizza-ai v0.1.0` (core, clients-openai, embedders-openai, vectorstores-qdrant).
- **Language**: Python 3.10+ with strict type hints.
- **Vector Store**: Qdrant running locally via Docker (`docker-compose.yml`) on port `6337` (collection: `match_analyst_tactics`, named vector `content_embedding`).
- **Embeddings**: `text-embedding-3-small`.
- **LLM Engine**: `gpt-4o-mini`; clients are built by datapizza's `ClientFactory` (`LLM_PROVIDER` in `src/core/config.py`).
- **Observability**: OpenTelemetry bridge exporting traces to Arize Phoenix on `http://localhost:6006/v1/traces`.
- **Frontend**: Streamlit.
- **MCP server**: `mcp_server.py` with the reference SDK `mcp>=2` (`MCPServer`, spec 2026-07-28, stateless); datapizza-ai 0.1.0 has no MCP server and its MCP client (`datapizza.tools.mcp_client`) speaks only the 1.x protocol: do not use it.

Useful commands (from the project root, virtual environment active):

| Command | What it does | API key |
|---|---|---|
| `python -m pytest` | offline tests | no |
| `python -m pytest --cov=src --cov=scripts --cov-report=term-missing` | the lines the tests never run | no |
| `python -m scripts.ingest --dry-run` | chunks of the corpus and cost estimate | no |
| `python -m scripts.review_chats [--all \| <file>]` | automatic checks on the chats saved by the app (`chats/`) | no |
| `python -m scripts.eval_retrieval --offline --no-save` | retrieval results of every configuration, from the cached question vectors | no (Qdrant running) |
| `streamlit run scripts/preview_graphics.py` | the graphics under an answer, the timelines and the goal actions, without the model | no |
| `python -m scripts.build_goal_actions` | the touches before each goal and the shots of the finals with StatsBomb data, for the app's animation and shot map (`references/derived/`, git-ignored: StatsBomb's licence) | no (needs the raw StatsBomb events) |
| `python -m scripts.verify --save / --check --cmd "<command>" --baseline <file>` | saves the output of a command, then checks that it did not change | no |
| `python mcp_server.py` | the knowledge base as an MCP server for Claude Desktop and other hosts (stdio; `MCP_HTTP=1` for Streamable HTTP) | only `search_cards` (and Qdrant) |
| `python -m scripts.prune_chats [--days N] [--delete]` | the saved chats older than N days (default 30): listed, deleted only with `--delete` | no |
| `python -m scripts.red_team` | the fixed set of attacks (`eval/red_team.json`): the input guard on each, the output handling and the page on a hijacked answer; offline, exit 1 if a deterministic defence fails | no |
| `python -m scripts.red_team --live` | the same attacks through the bare agent and the guarded one, and three control questions (about 30 calls, a few cents); saved to `eval/runs/red_team_*.json`; `--compare <a> <b>` retests two runs | yes |
| `python -m scripts.start` | Qdrant + Phoenix + the app; the log live in the terminal, the review of the session's chats on Ctrl+C | yes |
| `python -m scripts.ingest`, `scripts.eval_agent`, `scripts.gold_run` | index sync, answer checks, gold run with the LLM judge | yes |

---

## 2. Rules

### Architecture
- One folder per responsibility, no loose modules in `src/`:
  - `src/core/`: paths and settings (`config.py`); the version of the system (`build_info.py`: commit, uncommitted changes, fingerprints of the prompts, of the guardrails' code and of the corpus manifest), saved with every answer of the app and every run, so that each piece of evidence says what it was made with; the disk cache with datapizza's `Cache` interface (`disk_cache.py`: embeddings and judge verdicts already paid for, in `.cache/`).
  - `src/corpus/`: reading cards and manifest, splitting cards into chunks. Offline only: no API keys, no network.
  - `src/rag/`: Qdrant store, embeddings, search (a datapizza `DagPipeline`), and ingestion. Ingest only the cards listed in `corpus/manifest.json`; the YAML front matter goes into the payload, not into the embedded text.
  - `src/evaluation/`: measuring the system against `eval/gold_set.json`: retrieval metrics, deterministic answer checks, LLM judge, gold run, cost. Two entry points: `scripts/eval_agent.py` (fast deterministic checks, guardrail questions included) and `scripts/gold_run.py` (all metrics with the LLM judge; `--rejudge` re-judges a saved run; verdicts already given are read from `.cache/`, `--no-judge-cache` asks again).
  - `src/agent/`: only agent initialization, loop orchestration, and system prompts.
  - `src/tools/`: clean, typed `@tool` functions with explicit docstrings explaining inputs and outputs.
  - `src/guardrails/`: strict input/output validation; non-football queries MUST be intercepted before reaching the LLM. The facts written or checked by code are imported from `facts.py`, one module per family (`real_case.py`, `coaches.py`, `sides.py`, `additions.py`, with `text.py` shared): the real case of an advice answer is written by code from the card, the model writes only `Caso reale: [case_id]`. Coach-team pairs and thresholds are checked against the cards, the advice must be for the coach's side of a game situation (not the mirror card's; a man down, which has no card, gets an answer written by code when no score was given), a score the coach never gave is not taken for granted, a closing summary with no citation is removed, a name the cards write only in part is cut back to their words, a detail said to be missing gets the words "Non lo so", an effect added after a comma with no number or name is cut, an answer that repeats the system prompt is replaced by a refusal (`prompt_leak.py`, OWASP LLM07), no external link or image reaches the coach (`links.py`: the browser fetches an image as soon as the answer is shown, a channel out of the conversation; also applied by the page, with the guardrails off), and a wrong fact still there after the rewrite is removed. The verifier (`verifier.py`, a second model after the writer: a sequential architecture; optional, off by default, `--verifier`: under the acceptance gate on 2026-10-09) checks every statement against the consulted cards; its calls count in the answer's cost, priced with its own model, and since it shares method and model with the gold run's judge, measure it also with another judge (`gold_run --rejudge <run> --judge-model gpt-4.1`).
  - `src/observability/`: tracing to Arize Phoenix (OpenTelemetry spans translated to OpenInference), optional at runtime; the log of the app and the CLI (`logs.py`: Python `logging`, `logs/match_analyst.log`, git-ignored). Never log the API key; the text of the questions only goes to `chats/`. A key or a contact the coach writes (`src/guardrails/redact.py`: API keys and tokens, emails, phone numbers, IBANs, tax codes) is hidden from the question before the model, and again in the chat's file, in the traces and in every log line.
  - `src/ui/`: logic of the Streamlit app (`app.py` at the root only renders): `backend.py` (a conversation and the numbers of each answer), `view.py` (pure formatting functions, tested offline), `graphics/` (SVG graphics under an answer, from the coach's questions, the cards or StatsBomb's data, never from the model: one module per graphic, with `svg.py` and `badges.py` shared and `answer.py` choosing the graphics under an answer; rendered with `st.markdown`, as `st.html` strips `<svg>`). `chat_log.py` saves every conversation to `chats/` (git-ignored: it holds what the users typed). The app is tested with Streamlit's `AppTest` and the scripted fake model.
  - `src/mcp_server/`: the MCP server (`mcp_server.py` at the root only starts it): read-only tools `search_cards` (the agent's `CorpusTools`), `read_card`, `list_cards` (cards read from `corpus/`, no Qdrant), `card://{document_id}` resources and the `prepare_match` prompt. It never involves the agent, so it does not change the measured answers. In stdio, stdout is the protocol channel: nothing may print there (datapizza's console log handler is moved to stderr at start). Tested in-process with `mcp.Client` and with one real stdio session.
  - `design-system/`: tokens, components and answer states of the app as HTML previews (for Claude Design); a new design comes back only through `.streamlit/config.toml` and the `CSS` block of `src/ui/view.py`.
  - `scripts/`: maintenance scripts, run as `python -m scripts.<name>`.
  - `tests/`: offline tests (no API keys, no network), run with `python -m pytest`.

### Code
- **Language**: all code, comments, docstrings, prompts and documentation in English. Exceptions: the corpus cards (`corpus/`) and the answers shown to the user are in Italian (the users are Italian coaches); English questions are supported.
- **Reuse first**: prefer a datapizza-ai component or code already in the project to new code.
- **Secrets**: read an API key only through `src.core.config.require_api_key(provider)`, right before the call that needs it. Never load `.env` files outside the project root.
- **Error handling**: tools handle network/API errors gracefully and return structured failure explanations instead of crashing.

### Answers
- **No hallucinations**: every claim in an answer must be supported by a retrieved card and cite its `document_id`; the only other allowed source is what the coach wrote about their own team and the opponent.

### Corpus
- Cards follow the writing rules in `references/SOURCES.md` (facts only from cited sources, verbatim quotes, labelled interpretation). A match card's `timeline:` (drawn under an answer that cites the final) and a coach card's `shape_changes:` (drawn under an answer whose line citing the card writes the formation it becomes) are written only from the card's own text, each entry with its `quote`: `tests/test_corpus.py` checks them. The `## Numeri` table of a match card is drawn as bars: each value a number as the card writes it (`src/ui/graphics/match_numbers.py` leaves out a row it cannot read).
- A card is data the agent and other MCP hosts read, so nothing in it may act as an instruction (`src/guardrails/corpus_scan.py`, run by `scripts/check_corpus.py` and `tests/test_corpus_safety.py`): no "ignore the instructions" phrasing, no invisible character, no HTML comment or tag, no external address or image in the text (the `sources` of the front matter cite documents by address). The definitions of the MCP tools are pinned by a fingerprint in the same tests: read a changed definition, then update the fingerprint.
- After editing a card: `python -m scripts.build_manifest`, then `python -m pytest` and `python -m scripts.check_corpus`, then re-sync the index with `python -m scripts.ingest` (only changed cards are embedded).
- Save cards with LF line endings (`.gitattributes` enforces it on checkout): the manifest hashes their bytes.

### Evaluation
- `eval/gold_set.json` is the evaluation yardstick: do not edit it while tuning prompts or retrieval.
- `eval/red_team.json` is the security yardstick, frozen the same way: the attacks (vector, target, channel) are not edited to make a defence pass. A defence is evidence only when the same attacks are run before and after it (`scripts/red_team.py`); an attack no deterministic barrier stops is listed as a residual risk, not hidden.
- Every run and every saved answer carries its `build` (`src/core/build_info.py`): compare two runs only when their `prompts`, `guardrails_code` and `corpus` fingerprints say what changed between them.
- List every run in `eval/runs/README.md`; record every wrong answer found in `eval/error_log.md` and try each fix on those cases first.
- A change that alters the answers is kept only if the gold run (same judge) shows: faithfulness up by at least 0.03 and at least 0.85; recall@k down by at most 0.02; latency and cost within budget (today about 0.0012 $ per answer, p95 about 10 s).

---

## 3. Procedure

Follow these steps, in this order, for every change:

1. **Baseline.** Before touching the code, `python -m pytest` must be green; then save the output of retrieval and chunking:
   - `python -m scripts.verify --save --cmd "python -m scripts.eval_retrieval --offline --no-save" --baseline .cache/verify_retrieval.txt`
   - `python -m scripts.verify --save --cmd "python -m scripts.ingest --dry-run" --baseline .cache/verify_chunks.txt`
2. **Map.** List what to change: file and function, the rule it serves, the risk of the change.
3. **Small steps.** Start from the low-risk changes (names, dead code, constants), then the structural ones. One step at a time.
4. **Check after every step.** `python -m pytest` and the same two commands with `--check` instead of `--save`. If an output changed, undo the step before going on.
   A change meant to alter the answers (prompt, guardrails, retrieval) is not a refactoring: it is measured with `scripts/eval_agent.py` and `scripts/gold_run.py` and accepted only by the rule of *Evaluation* above. These commands use the OpenAI key: the user runs them.
5. **Summary.** List the changes made, the rules they satisfy, the runs added to `eval/runs/README.md` and the errors added to `eval/error_log.md`.

After editing a card the chunks change on purpose: save a new chunks baseline after `build_manifest`.

---

## 4. Constraints

- A refactoring does not change the observable behaviour: the `--check` commands stay green.
- No new features and no change of domain during a refactoring; refactor incrementally, never rewrite from scratch.
- Explain the cause of a problem before changing the code.
- No new dependencies without asking the user.
- Never call the OpenAI API: the commands that need the key are run by the user.
