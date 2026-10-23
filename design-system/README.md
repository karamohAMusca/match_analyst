# Design system — Match Analyst

The visual building blocks of the Streamlit app, as a design system that Claude Design can read
and redesign: the tokens (colours, type, shape), the components and the states of an answer, each
with an HTML preview.

It shows the app as it is today, after the redesign made with Claude Design: a sports paper, with
pink paper, a red accent, black ink and square corners; titles and the chat input in Inter, the
answers in Newsreader, labels and badges in IBM Plex Sans Condensed. It was generated on
2026-10-01 from the app itself: part 1 of `components.css` is the CSS block of `src/ui/view.py`
copied as it is, the HTML of the previews comes from the formatting functions of the same file
(`header_html`, `answer_html`, `guard_html`, `card_header_html`, `feature_html`), and the answers
are real ones, from run `eval/runs/agent_20260929-112013.json`. Refreshed on 2026-10-21 for the graphics under an
answer (`src/ui/graphics/`: they use the same `--ma-*` variables) and the welcome tiles in one grid, two by two (four tiles, the last one about the graphics).

## Structure

| Path | What it is |
|---|---|
| `tokens.css` | colours (light and dark theme, the values of `.streamlit/config.toml`), fonts, sizes, rules, spacing, as CSS variables |
| `components.css` | part 1: the classes of the app (`.ma-hero`, `.ma-cite`, `.ma-card-head`, `.ma-tag`, `.ma-feature`, `.ma-chip`, `.ma-unknown`, `.ma-guard`), the CSS block of `src/ui/view.py`; part 2 (`.ds-*`): how the Streamlit components around them look, for the previews only |
| `previews/` | one page per card, grouped by the `@dsCard` comment on its first line: Colors, Type, Components, Answer states, Graphics, Screens |

| Group | Previews |
|---|---|
| Colors, Type | `colors.html`, `typography.html` |
| Components | `hero.html` (masthead), `citation-badges.html` (numbered), `card-header.html` (with the number of its citations), `welcome-tiles.html`, `metrics.html`, `sidebar.html` |
| Answer states | `answer-normal.html` (cited, with a real case), `answer-dont-know.html` (the "Senza fonte" box), `answer-blocked.html` (off topic, dark guardrail box), `answer-rewritten.html` (fixed by the guardrail), `answer-loading.html` |
| Graphics | `graphics-pitch.html` (the formations the coach wrote, on a pitch, the players running to their place), `graphics-timeline.html` (the timeline of the real case, from the card), `graphics-shape.html` (a coach's change of shape, from the card: the players moving from one formation to the other), `graphics-numbers.html` (the numbers of a final, from the card's table, as bars split between the two teams); drawn by `src/ui/graphics/`. The action of a goal and the shot map are not previewed: they carry StatsBomb coordinates, which stay local (licence) |
| Screens | `screen-chat.html`: sidebar, masthead, tabs, the chat and the cited card side by side |

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
  `textColor`, `borderColor`, `font`, `headingFont`, `codeFont`, `baseRadius`, for both themes)
  and the variables of the CSS block;
- part 1 of `components.css` → the `CSS` block of `src/ui/view.py`, same class names.

Part 2 (`.ds-*`) only imitates Streamlit for the previews: layout, widgets and the chat input are
Streamlit's own and can be restyled, not rebuilt. The app tests (`tests/test_app.py`,
`tests/test_ui.py`) must stay green: a redesign changes the look, not the behaviour.
