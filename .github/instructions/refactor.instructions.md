---
applyTo: "**/*.py"
---

# Refactoring rules for the Python files

These rules cover the Python files only (`**/*.py`); `AGENTS.md` covers the whole project.

Before you edit a Python file here:

- Read the rules and the procedure in `AGENTS.md` and follow them.
- What the program prints and returns must stay the same. Once you are done, `python -m pytest` and both
  `python -m scripts.verify --check` commands listed in `AGENTS.md` have to pass.
- Work in small steps, one reason per step.
- Leave the type hints in place; where a signature has none, add them.
- No new dependency and no new feature.
- Tests run offline, without an API key or network: use the fakes in `tests/fakes.py`.
