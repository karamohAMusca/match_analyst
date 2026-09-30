# Design system — Match Analyst

The visual building blocks of the Streamlit app, as a design system that Claude Design can read
and redesign: the tokens (colours, type, shape), the components and the states of an answer, each
with an HTML preview.

It was generated on 2026-09-29 from the app itself: the HTML comes from the formatting functions
of `src/ui/view.py` (`header_html`, `cite_badges`, `card_header_html`) and the answers are real
ones, from run `eval/runs/agent_20260929-112013.json`. It shows the app as it is today: the
starting point of the redesign, not the goal.

## Structure

| Path | What it is |
|---|---|
| `tokens.css` | colours (light and dark theme), font, sizes, radii, spacing, as CSS variables |
| `components.css` | part 1: the classes of the app (`.ma-hero`, `.ma-cite`, `.ma-card-head`, `.ma-tag`, `.ma-feature`, `.ma-chip`) written with the tokens; part 2 (`.ds-*`): how the Streamlit components around them look, for the previews only |
| `previews/` | one page per card, grouped by the `@dsCard` comment on its first line: Colors, Type, Components, Answer states, Screens |

| Group | Previews |
|---|---|
| Colors, Type | `colors.html`, `typography.html` |
| Components | `hero.html` (header), `citation-badges.html`, `card-header.html`, `welcome-tiles.html`, `metrics.html`, `sidebar.html` |
| Answer states | `answer-normal.html` (cited, with a real case), `answer-dont-know.html`, `answer-blocked.html` (off topic), `answer-rewritten.html` (fixed by the guardrail), `answer-loading.html` |
| Screens | `screen-chat.html`: sidebar, header, tabs, the chat and the cited card side by side |

## Working with Claude Design

From this folder, start Claude Code and sync the design system:

```bash
cd design-system
claude
/design-sync
```

The sync shows the list of files before uploading anything. Then redesign in Claude Design,
starting from the Chat screen, and sync again when the result is ready.

## Back into the app

The app is Streamlit, so a new design comes back in two places only:
- the tokens → `.streamlit/config.toml` (`primaryColor`, `backgroundColor`, `secondaryBackgroundColor`,
  `textColor`, `font`) and the variables of the CSS block;
- part 1 of `components.css` → the `CSS` block of `src/ui/view.py`, same class names.

Part 2 (`.ds-*`) only imitates Streamlit for the previews: layout, widgets and the chat input are
Streamlit's own and can be restyled, not rebuilt. The app tests (`tests/test_app.py`,
`tests/test_ui.py`) must stay green: a redesign changes the look, not the behaviour.

Known detail of today's design, visible in `answer-normal.html`: a citation badge never breaks
across lines, so the full stop after it can wrap alone to the next line.
