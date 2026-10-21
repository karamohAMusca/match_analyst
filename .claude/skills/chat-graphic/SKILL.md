---
name: chat-graphic
description: Add or change a graphic drawn under a chat answer of the Match Analyst app (the pitch with the formations, the timeline of a final, the action of a goal, or a new one). Use when the user asks for a chart, a drawing, an animation or any visual in the chat or in the cards tab of the Streamlit app.
---

# A graphic under a chat answer

The graphics of the app are SVG strings written by pure functions in the package `src/ui/graphics/`,
rendered by `app.py` under the answer. One module per graphic (`formations.py`, `timeline.py`,
`goal.py`): a new graphic gets a module of its own. What every graphic shares is in `svg.py` and
`badges.py`, `answer.py` chooses the graphics under an answer, and `__init__.py` exports the names the
app, the scripts and the tests import. Follow these steps, in this order.

## 1. Where the data comes from (decide first, write it in the docstring)

A graphic never draws what the model wrote. Its data comes from one of these, and only these:
- **the coach's own questions** (`formations_in`: "noi giochiamo 4-3-3"); when a fact cannot be
  read for sure (whose formation is it?), draw nothing: a wrong graphic is worse than none;
- **a card's front matter**, written only from that card's text with the exact words in a `quote`
  (`timeline:` of the match cards), and a test in `tests/test_corpus.py` that every quote, name and
  number is in the card (after editing a card: `python -m scripts.build_manifest`, the tests,
  `python -m scripts.check_corpus`, then the user runs `python -m scripts.ingest`);
- **third-party data derived by a script** (`scripts/build_goal_actions.py`), with its licence
  respected: StatsBomb's raw data is not redistributed, so the derived file stays git-ignored and
  the graphic is simply absent where the file is missing (tests skip).

## 2. Draw it

- One pure function `<thing>_svg(..., english=False, animate=True) -> str` in the graphic's module,
  empty string when there is nothing to draw. Reuse `svg.py`: the colours `RED`, `INK`, `CARD`,
  `MUTED` (the design system's CSS variables with a fallback: light and dark come for free), `TEXT`
  (the font, `IBM Plex Sans Condensed`), `esc` for every text of a card or of the data, `pitch_svg`
  on the pitch units `W`, `H` (and `formation_places` from `formations.py` for where a formation puts
  its players), `figcaption` for the caption.
- Teams through `team_badge` only: a national team's flag, a club's neutral shield with its initials.
  Never a real club crest or a competition logo (trademarks, protected artwork), never an image
  downloaded from the web: everything is drawn by code.
- Identity never by colour alone: the coach's team red and filled, the other ink and hollow, plus
  direct labels; a `<title>` tooltip on every mark (with the card's own words when there are some);
  a caption that says where the data comes from and what it is not.
- Motion: CSS `@keyframes` only (no JavaScript), class and keyframe names unique per figure
  (`ma-<key>-...`, with `key = figure_key(<the content>, english, animate)`), written with
  `motion_style(css, key)`, which adds the `@media (prefers-reduced-motion: reduce)` rule that stops
  them; the still state complete (with `animate=False` the whole graphic is visible).
- Labels: kept inside the figure, never overlapping (rows), at least ~10 px on a phone.

## 3. Show it

- In `app.py`: `st.markdown(svg, unsafe_allow_html=True)`. Not `st.html`: its sanitizer removes `<svg>`.
- Under an answer through `answer_figures` in `answer.py` (only for questions the agent answered;
  only the newest answer animated); in the cards tab through `show_card`. Export the new names from
  `__init__.py`.

## 4. Check it

- Tests in `tests/test_graphics.py` (or a file of its own): the data read, the SVG (marks, labels,
  tooltips, caption, no `<script>`), the still version; an `AppTest` in `tests/test_app.py` for the
  app. `python -m pytest` must stay green.
- Look at it: `streamlit run scripts/preview_graphics.py` (no API key: the real functions on a written
  conversation, every timeline, every goal action), light and dark, wide and narrow window; restart it
  after changing `src/` (Streamlit does not reload modules outside the script's folder).
- Run the palette check of the dataviz skill when a colour is added.
- Docs: the row of `ui/graphics/` in `src/README.md` (and `src/LEGGIMI.md`), the app paragraph of
  `README.md`, a preview in `design-system/previews/` (group "Graphics") when the graphic is new.
