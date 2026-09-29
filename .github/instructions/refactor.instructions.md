---
applyTo: "**/*.py"
---

# Scoped instructions: refactoring by criteria

These rules apply only to the Python files of the project (field `applyTo`); `AGENTS.md` applies
to the whole project.

When you change a Python file in this project:

- Follow the rules and the procedure of `AGENTS.md`.
- Do not change the observable behaviour: after the change, `python -m pytest` and the two
  `python -m scripts.verify --check` commands of `AGENTS.md` must stay green.
- Apply one change at a time, small and motivated.
- Keep the type hints, and add them where they are missing.
- Do not add new dependencies or new features.
- Tests stay offline: no API key and no network (use the fakes in `tests/fakes.py`).
