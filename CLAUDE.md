# CLAUDE.md

@AGENTS.md

The project instructions are in `AGENTS.md`, imported above: one file for every coding assistant
(Claude Code reads this one, GitHub Copilot reads `AGENTS.md` directly), so the rules never drift apart.

For Claude Code, three more files in `.claude/` work with it:
- `.claude/rules/refactor.md`: rules applied to the Python files only (`paths: **/*.py`);
- `.claude/commands/refactor-by-criteria.md`: the reusable command `/refactor-by-criteria`;
- `.claude/skills/chat-graphic/SKILL.md`: how to add a graphic under a chat answer (where its data may come
  from, how to draw, show and check it), Claude Code only.

The first two say the same as the files in `.github/` (the Copilot flavour): `tests/test_agent_instructions.py`
fails if the two copies differ.

Working notes for Claude Code on this project:
- Run the offline tests with `python -m pytest` (virtual environment active, from the project root).
- Never read `.env` and never call the OpenAI API: the commands that use the key (`scripts.ingest`,
  `scripts.eval_agent`, `scripts.gold_run`, the app and the CLI) are run by the user, who then asks for
  the results to be read.
- Every wrong answer found goes into `eval/error_log.md`; every measured run into `eval/runs/README.md`.
