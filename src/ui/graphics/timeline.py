"""The timeline of a final, from its card.

The events come from the `timeline:` of the card's front matter, each with the card's own words
(`quote`): a test checks that the quote, the names and the minutes are in the card's text and that
the goals add up to the title (tests/test_corpus.py). An event with no minute in the card has its
period instead, and is drawn dashed, spaced between the events around it.
"""

from __future__ import annotations

from src.ui.graphics.badges import team_badge
from src.ui.graphics.svg import (CARD, INK, MUTED, RED, TEXT, TITLE_TEAMS_RE, esc, figcaption, figure_key,
                                 motion_style)

PERIODS = {1: (0, 45), 2: (45, 90), 3: (90, 105), 4: (105, 120)}
# The label says when, the score and who; the shape of the mark says what (legend in the caption), the
# tooltip says it in words, with the card's own sentence.
_KIND_WORDS = {
    "it": {"goal": "gol", "penalty": "gol su rigore", "save": "parata su", "post": "palo di", "red": "espulso",
           "sub": "entrano"},
    "en": {"goal": "goal", "penalty": "penalty goal", "save": "save on", "post": "post by", "red": "sent off",
           "sub": "on"},
}
_LEGEND = {
    "it": "● gol · ○ parata o palo · ▽ cambio · ▮ espulsione; tratteggiato: la scheda non dà il minuto.",
    "en": "● goal · ○ save or post · ▽ change · ▮ sent off; dashed: the card gives no minute.",
}
_SIZE, _ROW_GAP, _AXIS_Y = 3.3, 4.4, 20.0


def event_minutes(timeline: list[dict]) -> list[float | None]:
    """The axis position of every event: its minute, or, with only the period, evenly spaced between
    the events with a minute around it in that period (the shoot-out has none)."""
    minutes: list[float | None] = [e.get("minute") for e in timeline]
    i = 0
    while i < len(timeline):
        event = timeline[i]
        if event.get("kind") == "shootout" or minutes[i] is not None:
            i += 1
            continue
        j = i
        while j < len(timeline) and minutes[j] is None and timeline[j].get("period") == event.get("period"):
            j += 1
        start, end = PERIODS[event["period"]]
        before = [m for m in minutes[:i] if m is not None and start <= m <= end]
        after = [m for m in minutes[j:] if m is not None and start <= m <= end]
        low, high = (before[-1] if before else start), (after[0] if after else end)
        for k in range(i, j):
            minutes[k] = low + (high - low) * (k - i + 1) / (j - i + 1)
        i = j
    return minutes


def _mark(kind: str, x: float, y: float, sign: int, colour: str, dashed: bool) -> str:
    """The sign of an event: a goal filled, a chance (save, post) hollow, a red card a card, a change a
    triangle; dashed when the card gives no minute."""
    dash = ' stroke-dasharray="0.8 0.6"' if dashed else ""
    if kind in ("goal", "penalty"):
        if dashed:
            return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="{CARD}" stroke="{colour}" '
                    f'stroke-width="0.6"{dash}/>')
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="{colour}" stroke="{CARD}" stroke-width="0.5"/>'
    if kind == "red":
        return f'<rect x="{x - 0.9:.1f}" y="{y - 1.3:.1f}" width="1.8" height="2.6" fill="{colour}"/>'
    if kind == "sub":
        return (f'<path d="M {x - 1.3:.1f} {y - sign * 0.9:.1f} L {x + 1.3:.1f} {y - sign * 0.9:.1f} '
                f'L {x:.1f} {y + sign * 1.3:.1f} Z" fill="none" stroke="{colour}" stroke-width="0.5"{dash}/>')
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.2" fill="none" stroke="{colour}" stroke-width="0.5"{dash}/>'


def timeline_svg(card: dict, english: bool = False, animate: bool = True) -> str:
    """The timeline of a final: goals with the score, penalties, saves, a post, red cards and changes,
    above the axis for the first team of the title (red), below for the other (ink); extra time and the
    shoot-out only when they were played; a tooltip with the card's own words on every event. Empty
    without a timeline."""
    timeline = card.get("timeline") or []
    teams = TITLE_TEAMS_RE.search(card.get("title", ""))
    if not timeline or not teams:
        return ""
    home, lang = teams["home"], "en" if english else "it"
    minutes = event_minutes(timeline)
    shootout = next((e for e in timeline if e.get("kind") == "shootout"), None)
    extra = shootout is not None or any(m and m > 90 for m in minutes)
    end = 120 if extra else 90
    x0, x1 = 11.0, (84.0 if shootout else 96.0)   # the teams' symbols before the axis

    def x_of(minute: float) -> float:
        return x0 + (x1 - x0) * minute / end

    key = figure_key(card.get("id") or card.get("title"), english, animate)
    rows_right: dict[bool, list[float]] = {True: [], False: []}   # labels on rows: two never overlap
    marks, css = [], []
    for n, (event, minute) in enumerate(zip(timeline, minutes)):
        if event.get("kind") == "shootout" or minute is None:
            continue
        top, x, kind = event["team"] == home, x_of(minute), event["kind"]
        colour = RED if top else INK
        shown = event.get("shown") or (f"{event['minute']}'" if "minute" in event else "")
        suffix = ("(rig.)" if lang == "it" else "(pen.)") if kind == "penalty" else ""
        label = " ".join(filter(None, [shown, event.get("score", ""), event.get("who", ""), suffix]))
        width = len(label) * _SIZE * 0.46
        label_x = min(max(x, width / 2 + 0.5), 99.5 - width / 2)   # kept inside the figure, near the edges too
        rows = rows_right[top]
        row = next((r for r, right in enumerate(rows) if label_x - width / 2 > right + 1.2), len(rows))
        if row < len(rows):
            rows[row] = label_x + width / 2
        else:
            rows.append(label_x + width / 2)
        sign = -1 if top else 1
        mark_y = _AXIS_Y + sign * 3.2
        label_y = _AXIS_Y + sign * (7.2 + row * _ROW_GAP) + (0 if top else _SIZE * 0.75)
        leader = (f'<line x1="{x:.1f}" y1="{mark_y + sign * 1.8:.1f}" x2="{x:.1f}" '
                  f'y2="{label_y + (_SIZE * 0.2 if top else -_SIZE):.1f}" stroke="{colour}" stroke-width="0.2"/>'
                  if row or abs(label_x - x) > width / 3 else "")
        weight = ' font-weight="700"' if kind in ("goal", "penalty") else ""
        when = shown or (f"periodo {event['period']}" if lang == "it" else f"period {event['period']}")
        said = " ".join(filter(None, [event.get("score", ""), _KIND_WORDS[lang][kind], event.get("who", "")]))
        name = f"ma-{key}-t{n}"
        marks.append(f'<g class="{name}"><title>{esc(when)} · {esc(event["team"])} · {esc(said)} — «{esc(event["quote"])}»</title>'
                     f'<rect x="{label_x - width / 2:.1f}" y="{min(mark_y, label_y) - 3.5:.1f}" width="{width:.1f}" '
                     f'height="{abs(label_y - mark_y) + 5:.1f}" fill="transparent"/>'
                     f'{_mark(kind, x, mark_y, sign, colour, "minute" not in event)}{leader}'
                     f'<text x="{label_x:.1f}" y="{label_y:.1f}" {TEXT} font-size="{_SIZE}"{weight} text-anchor="middle" '
                     f'fill="{INK}">{esc(label)}</text></g>')
        if animate:   # the events appear in the order of the match, as the axis is drawn
            delay = 0.3 + 1.4 * (x - x0) / (x1 - x0)
            css.append(f"@keyframes {name} {{ from {{ opacity: 0; transform: translate(0, {sign * -2}px); }} "
                       f"to {{ opacity: 1; transform: translate(0, 0); }} }} "
                       f".{name} {{ animation: {name} 0.5s ease-out {delay:.2f}s both; }}")

    def near(minute: int, top: bool) -> bool:   # an event close to a tick, on that side of the axis
        return any(m is not None and e.get("kind") != "shootout" and abs(m - minute) < 9 and (e["team"] == home) == top
                   for e, m in zip(timeline, minutes))

    ticks = "".join(f'<line x1="{x_of(m):.1f}" y1="{_AXIS_Y - 1}" x2="{x_of(m):.1f}" y2="{_AXIS_Y + 1}" '
                    f'stroke="{INK}" stroke-width="0.3"/>' for m in (0, 45, 90, 105, 120) if m <= end)
    ticks += "".join(f'<text x="{x_of(m) + 0.6:.1f}" y="{_AXIS_Y + (3.4 if near(m, True) and not near(m, False) else -1.4):.1f}" '
                     f'{TEXT} font-size="2.3" fill="{MUTED}">{m}\'</text>'
                     for m in (45, 90, 105) if m < end)
    band = (f'<rect x="{x_of(90):.1f}" y="{_AXIS_Y - 3}" width="{x_of(120) - x_of(90):.1f}" height="6" '
            f'fill="{RED}" opacity="0.08"/>' if extra else "")
    box = ""
    if shootout:
        winner = RED if shootout["team"] == home else INK
        word = "RIGORI" if lang == "it" else "PENALTIES"
        box = (f'<g><title>{esc(shootout["team"])} · {word.lower()} {esc(shootout["score"])} — «{esc(shootout["quote"])}»</title>'
               f'<rect x="87" y="{_AXIS_Y - 4.5}" width="11.5" height="9" fill="none" stroke="{INK}" '
               f'stroke-width="0.4"/><text x="92.75" y="{_AXIS_Y - 0.8}" {TEXT} font-size="2.4" text-anchor="middle" '
               f'fill="{MUTED}">{word}</text><text x="92.75" y="{_AXIS_Y + 3.2}" {TEXT} '
               f'font-size="3.3" font-weight="700" text-anchor="middle" fill="{winner}">{esc(shootout["score"])}</text></g>')
    axis = (f'<line class="ma-{key}-axis" x1="{x0}" y1="{_AXIS_Y}" x2="{x1}" y2="{_AXIS_Y}" pathLength="100" '
            f'stroke="{INK}" stroke-width="0.5"/>')
    if animate:
        css.append(f"@keyframes ma-{key}-axis {{ from {{ stroke-dashoffset: 100; }} to {{ stroke-dashoffset: 0; }} }} "
                   f".ma-{key}-axis {{ stroke-dasharray: 100; animation: ma-{key}-axis 1.4s ease-out 0.2s both; }}")
    top_y = _AXIS_Y - 7.2 - max(len(rows_right[True]) - 1, 0) * _ROW_GAP - _SIZE - 1.5
    bottom_y = _AXIS_Y + 7.2 + max(len(rows_right[False]) - 1, 0) * _ROW_GAP + _SIZE + 1.5
    header_y = top_y - 1.0
    # "Finale Champions League 2026: Paris Saint-Germain 1-1 Arsenal (4-3 d.c.r.)": the competition on
    # the small line, the match on the big one, smaller if it is still too long for the width
    competition, _, match = card.get("title", "").rpartition(": ")
    kicker = ("REAL CASE" if english else "CASO REALE") + (f" · {competition.upper()}" if competition else "")
    title_size = min(3.6, 96 / max(len(match) * 0.5, 1))   # the header starts at x=2
    badges = (team_badge(home, 2, _AXIS_Y - 5.6, 4.4) + team_badge(teams["away"], 2, _AXIS_Y + 1.2, 4.4))
    header = (f'<text x="2" y="{header_y - 4.6:.1f}" {TEXT} font-size="2.6" font-weight="700" letter-spacing="0.4" '
              f'fill="{MUTED}">{esc(kicker)}</text>'
              f'<text x="2" y="{header_y:.1f}" {TEXT} font-size="{title_size:.2f}" font-weight="700" '
              f'fill="{INK}">{esc(match)}</text>')
    caption = (f"{_LEGEND[lang]} From the card {esc(card.get('id', ''))}: minutes and names as the card writes them."
               if english else
               f"{_LEGEND[lang]} Dalla scheda {esc(card.get('id', ''))}: minuti e nomi come li scrive la scheda.")
    top_view = header_y - 8.5
    return (f'<figure class="ma-figure ma-timeline" style="margin:0.5rem 0 0">{motion_style(css, key)}'
            f'<svg viewBox="0 {top_view:.1f} 100 {bottom_y - top_view:.1f}" role="img" '
            f'aria-label="{"Timeline" if english else "Linea del tempo"}: {esc(card.get("title", ""))}" '
            f'style="width:100%;height:auto;display:block">{header}{badges}{band}{axis}{ticks}{"".join(marks)}{box}</svg>'
            f"{figcaption(caption)}</figure>")
