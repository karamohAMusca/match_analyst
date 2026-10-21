"""The instruction files for the two coding assistants say the same (offline).

`AGENTS.md` is the one file for every assistant; `.github/` holds the Copilot flavour of the scoped
rules and of the reusable command, `.claude/` the Claude Code flavour, and `CLAUDE.md` imports
`AGENTS.md`. Only the front matter differs: the bodies must not drift apart.
"""

from __future__ import annotations

from pathlib import Path

from src.core.config import PROJECT_ROOT

PAIRS = [
    (".github/instructions/refactor.instructions.md", ".claude/rules/refactor.md"),
    (".github/prompts/refactor-by-criteria.prompt.md", ".claude/commands/refactor-by-criteria.md"),
]


def body(path: Path) -> str:
    """The file without its front matter."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert text.startswith("---\n"), path
    return text.split("\n---\n", 1)[1].strip()


def test_the_two_flavours_of_each_instruction_file_say_the_same():
    for copilot, claude in PAIRS:
        assert body(PROJECT_ROOT / copilot) == body(PROJECT_ROOT / claude), (copilot, claude)


def test_claude_md_imports_agents_md_and_the_rules_are_scoped_to_python():
    assert "@AGENTS.md" in (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
    rules = (PROJECT_ROOT / ".claude/rules/refactor.md").read_text(encoding="utf-8")
    assert '"**/*.py"' in rules.split("\n---\n", 1)[0]
    assert 'applyTo: "**/*.py"' in (PROJECT_ROOT / ".github/instructions/refactor.instructions.md").read_text(encoding="utf-8")
