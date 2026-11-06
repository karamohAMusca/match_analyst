---
description: Refactor the file or the selection by the criteria of AGENTS.md, keeping the output unchanged.
---

# Reusable command: refactor by the project's criteria

Call it from the chat with `/refactor-by-criteria`. `AGENTS.md` and the scoped rules apply on their own;
this command runs only when you ask for it.

Refactor the open file, or the selection, following the rules and the procedure in `AGENTS.md`.

How to proceed:

1. First write two lines: which rules the code breaks today.
2. Go step by step, starting with the change that can break the least.
3. After each step run `python -m pytest` and both `python -m scripts.verify --check` commands in `AGENTS.md`.
   If the output changed, undo that step before going on.
4. Add no feature, leave the domain alone, and never start the file over.
5. Finish with the list of what you changed and which rules each change satisfies.
