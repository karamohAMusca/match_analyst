---
mode: agent
description: Refactor the file or the selection by the criteria of AGENTS.md, keeping the output unchanged.
---

# Reusable prompt: refactoring by criteria

Invoke it in the chat with `/refactor-by-criteria`. Unlike `AGENTS.md` and the scoped
instructions, which apply automatically, this runs only when you call it.

Refactor the file (or the selection) applying the rules and the procedure of `AGENTS.md`.

Execution rules:

1. Before changing anything, summarise in two lines the rule violations you found.
2. Proceed one step at a time, from the safest to the riskiest.
3. After every step run `python -m pytest` and the two `python -m scripts.verify --check`
   commands of `AGENTS.md`; stop and undo the step if the output changed.
4. Do not add features, do not change the domain, do not rewrite from scratch.
5. At the end list the changes made and the rules satisfied.
