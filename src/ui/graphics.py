"""Graphics under a chat answer, drawn as SVG by code in the colours of the design system (the
`--ma-*` variables of the CSS block in view.py, light and dark): no chart library, no JavaScript;
the movement is CSS only, and it stops when the system asks for reduced motion.
The app renders them with `st.markdown(..., unsafe_allow_html=True)`: `st.html` sanitizes the
`<svg>` element away.

Nothing here comes from the model. The formations are read from the coach's own questions
("noi giochiamo 4-3-3", "affrontiamo un 4-4-2 basso", "352"): the pitch shows where a formation puts
its players, indicatively, and says so; it is not a fact of the cards.

The two teams: the coach's in red, filled; the opponent in ink, hollow. Checked with a palette
validator on the app's surfaces: red and ink stay apart for colour-blind readers too (ΔE 21 light,
24 dark) with enough contrast; ink reads as a neutral, so the shape and the direct labels
("VOI", "AVVERSARIO") carry the identity as well, never the colour alone.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable

from src.guardrails.language import detect_language
from src.guardrails.real_case import CASE_LINE_RE, case_ids
from src.guardrails.text import normalize

W, H = 120, 80   # pitch units (StatsBomb's), the coach's team attacking left to right

# A formation: 3 to 5 lines of outfield players, 1 to 5 each, adding up to 10; with dashes (any
# typographic dash) or written as one number ("433", "4231"). Not a score ("1-0") nor a year.
_FORMATION_RE = re.compile(r"(?<![\w-])([1-5](?:\s?[-‐-―−]\s?[1-5]){2,4}|[1-5]{3,5})(?![\w-])")
# Who plays it: the cue nearest before the formation, in the same sentence. "gioca" alone is
# neither ("la mia squadra gioca 4-2-3-1": the cue is "mia squadra").
_OURS_RE = re.compile(
    r"\b(?:noi|giochiamo|giocavamo|gioco|giocando|schieriamo|schieravamo|schiero|usiamo|utilizziamo|adottiamo|partiamo|"
    r"(?:la\s+)?mia\s+squadra|nostr[oaie]|we|our|my\s+team|i\s+play)\b")
_THEIRS_RE = re.compile(
    r"\b(?:affrontiamo|affronto|affrontare|affrontando|avversari[oae]?|loro|contro|giocano|schierano|"
    r"si\s+chiude|si\s+schiera|attacca(?:re)?|battere|superare|scardinare|opponents?|they|their|"
    r"against|face|facing|beat)\b")
_SENTENCE_RE = re.compile(r"[^.!?;\n]+")


def _formation(written: str) -> str | None:
    """'4–3–3', '433', '4 - 2 - 3 - 1' as '4-3-3'; None if it is not a formation of 10 players."""
    digits = [int(d) for d in re.findall(r"[1-5]", written)]
    return "-".join(map(str, digits)) if 3 <= len(digits) <= 5 and sum(digits) == 10 else None


def formations_in(text: str) -> dict[str, str]:
    """{"ours": ..., "theirs": ...} for the formations of `text` whose side a cue word gives; a
    formation with no cue before it in its sentence is left out (a wrong side is worse than none)."""
    found: dict[str, str] = {}
    for sentence in _SENTENCE_RE.findall(normalize(text)):
        start = 0
        for match in _FORMATION_RE.finditer(sentence):
            formation = _formation(match.group(1))
            before, start = sentence[start:match.start()], match.end()
            if not formation:
                continue
            cues = [(m.end(), "ours") for m in _OURS_RE.finditer(before)]
            cues += [(m.end(), "theirs") for m in _THEIRS_RE.finditer(before)]
            if cues:
                found[max(cues)[1]] = formation
    return found


def coach_formations(questions: Iterable[str]) -> dict[str, str]:
    """The formations of a conversation, side by side: a later question overrides an earlier one."""
    found: dict[str, str] = {}
    for question in questions:
        found.update(formations_in(question))
    return found


def formation_places(formation: str) -> list[tuple[float, float, str]]:
    """(x, y, line) of the 11 players, goalkeeper first, for a team attacking left to right in its own
    half: the lines evenly spaced from defence to attack, the players of a line evenly across."""
    lines = [int(d) for d in formation.split("-")]
    names = (["difesa"] + ["centrocampo"] * (len(lines) - 2) + ["attacco"]) if len(lines) > 2 else ["difesa", "attacco"]
    xs = [18 + j * (54 - 18) / (len(lines) - 1) for j in range(len(lines))]
    places = [(5.0, H / 2, "portiere")]
    for x, n, name in zip(xs, lines, names):
        places += [(x, H * (i + 1) / (n + 1), name) for i in range(n)]
    return places


def pitch_svg() -> str:
    """The lines of the pitch, in ink on the card colour."""
    line = 'fill="none" stroke="var(--ma-ink,#111)" stroke-width="0.35"'
    return (f'<rect x="0" y="0" width="{W}" height="{H}" fill="var(--ma-card,#FBE9EA)" stroke="var(--ma-ink,#111)" '
            f'stroke-width="0.5"/>'
            f'<line x1="60" y1="0" x2="60" y2="{H}" {line}/><circle cx="60" cy="40" r="10" {line}/>'
            f'<rect x="0" y="18" width="18" height="44" {line}/><rect x="102" y="18" width="18" height="44" {line}/>'
            f'<rect x="0" y="30" width="6" height="20" {line}/><rect x="114" y="30" width="6" height="20" {line}/>'
            '<rect x="-1.2" y="36" width="1.2" height="8" fill="var(--ma-ink,#111)"/>'
            '<rect x="120" y="36" width="1.2" height="8" fill="var(--ma-ink,#111)"/>')


_LABEL = 'font-family="IBM Plex Sans Condensed, sans-serif" font-size="5" font-weight="700" letter-spacing="0.3"'


def formations_svg(formations: dict[str, str], english: bool = False, animate: bool = True) -> str:
    """The pitch with the coach's formation on the left (red, filled) and the opponent's on the right
    (ink, hollow); each player has a tooltip with the team and the line. Animated: the players run
    from the halfway line to their place. Empty string if there is no formation."""
    if not formations:
        return ""
    ours, theirs = formations.get("ours"), formations.get("theirs")
    key = hashlib.sha1(f"{ours}|{theirs}".encode()).hexdigest()[:6]   # keyframe names unique per figure
    team_names = ("You", "Opponent") if english else ("Voi", "Avversario")
    css, marks = [], []
    for side, formation, team in (("ours", ours, team_names[0]), ("theirs", theirs, team_names[1])):
        if not formation:
            continue
        left = side == "ours"
        for i, (x, y, line) in enumerate(formation_places(formation)):
            x, y = (x, y) if left else (W - x, H - y)
            dot = (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.3" fill="var(--ma-red,#B3122B)" '
                   f'stroke="var(--ma-card,#FBE9EA)" stroke-width="0.6"/>' if left else
                   f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2" fill="var(--ma-card,#FBE9EA)" '
                   f'stroke="var(--ma-ink,#111)" stroke-width="0.9"/>')
            name = f"ma-{key}-{side}-{i}"
            marks.append(f'<g class="{name}"><title>{team} · {formation} · {line}</title>'
                         f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="transparent"/>{dot}</g>')
            if animate:
                start_x = 56 if left else 64
                css.append(f"@keyframes {name} {{ from {{ transform: translate({start_x - x:.1f}px, {40 - y:.1f}px); "
                           f"opacity: 0; }} to {{ transform: translate(0, 0); opacity: 1; }} }} "
                           f".{name} {{ animation: {name} 0.9s cubic-bezier(.2,.8,.2,1) "
                           f"{0.05 * i + (0 if left else 0.3):.2f}s both; }}")
    labels = ""
    if ours:
        labels += f'<text x="2" y="-2" {_LABEL} fill="var(--ma-red,#B3122B)">{team_names[0].upper()} · {ours}</text>'
    if theirs:
        labels += (f'<text x="118" y="-2" {_LABEL} fill="var(--ma-ink,#111)" text-anchor="end">'
                   f'{team_names[1].upper()} · {theirs}</text>')
    described = " · ".join(f"{t} {f}" for t, f in zip(team_names, (ours, theirs)) if f)
    caption = ("Indicative positions of the formations you wrote: they do not come from the cards." if english else
               "Disposizione indicativa dei moduli che hai scritto: le posizioni non vengono dalle schede.")
    style = (f"<style>{' '.join(css)} @media (prefers-reduced-motion: reduce) {{ [class^=\"ma-{key}-\"] "
             f"{{ animation: none !important; }} }}</style>" if css else "")
    return (f'<figure class="ma-figure" style="margin:0.5rem 0 0">{style}'
            f'<svg viewBox="-2 -7 124 89" role="img" aria-label="{described}" style="width:100%;height:auto;display:block">'
            f"{pitch_svg()}{labels}{''.join(marks)}</svg>"
            f'<figcaption style="font-family:\'IBM Plex Sans Condensed\',sans-serif;font-size:12px;'
            f'color:var(--ma-muted,#4A3A3C)">{caption}</figcaption></figure>')


# ---------------------------------------------------------------- the timeline of a real case
# The events of a final come from the `timeline:` of its card's front matter, each with the card's own
# words (`quote`): a test checks that the quote, the names and the minutes are in the card's text and
# that the goals add up to the title (tests/test_corpus.py). An event with no minute in the card has
# its period instead, and is drawn dashed, spaced between the events around it.
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
_TITLE_TEAMS_RE = re.compile(r":\s*(?P<home>.+?)\s+\d+-\d+\s+(?P<away>[^(]+?)\s*(?:\(|$)")
_TEXT = 'font-family="IBM Plex Sans Condensed, sans-serif"'
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
            return (f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.6" fill="var(--ma-card,#FBE9EA)" stroke="{colour}" '
                    f'stroke-width="0.6"{dash}/>')
        return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.7" fill="{colour}" stroke="var(--ma-card,#FBE9EA)" stroke-width="0.5"/>'
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
    teams = _TITLE_TEAMS_RE.search(card.get("title", ""))
    if not timeline or not teams:
        return ""
    home, lang = teams["home"], "en" if english else "it"
    minutes = event_minutes(timeline)
    shootout = next((e for e in timeline if e.get("kind") == "shootout"), None)
    extra = shootout is not None or any(m and m > 90 for m in minutes)
    end = 120 if extra else 90
    x0, x1 = 4.0, (84.0 if shootout else 96.0)

    def x_of(minute: float) -> float:
        return x0 + (x1 - x0) * minute / end

    key = hashlib.sha1(str(card.get("id") or card.get("title")).encode()).hexdigest()[:6]
    rows_right: dict[bool, list[float]] = {True: [], False: []}   # labels on rows: two never overlap
    marks, css = [], []
    for n, (event, minute) in enumerate(zip(timeline, minutes)):
        if event.get("kind") == "shootout" or minute is None:
            continue
        top, x, kind = event["team"] == home, x_of(minute), event["kind"]
        colour = "var(--ma-red,#B3122B)" if top else "var(--ma-ink,#111)"
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
        marks.append(f'<g class="{name}"><title>{when} · {event["team"]} · {said} — «{event["quote"]}»</title>'
                     f'<rect x="{label_x - width / 2:.1f}" y="{min(mark_y, label_y) - 3.5:.1f}" width="{width:.1f}" '
                     f'height="{abs(label_y - mark_y) + 5:.1f}" fill="transparent"/>'
                     f'{_mark(kind, x, mark_y, sign, colour, "minute" not in event)}{leader}'
                     f'<text x="{label_x:.1f}" y="{label_y:.1f}" {_TEXT} font-size="{_SIZE}"{weight} text-anchor="middle" '
                     f'fill="var(--ma-ink,#111)">{label}</text></g>')
        if animate:   # the events appear in the order of the match, as the axis is drawn
            delay = 0.3 + 1.4 * (x - x0) / (x1 - x0)
            css.append(f"@keyframes {name} {{ from {{ opacity: 0; transform: translate(0, {sign * -2}px); }} "
                       f"to {{ opacity: 1; transform: translate(0, 0); }} }} "
                       f".{name} {{ animation: {name} 0.5s ease-out {delay:.2f}s both; }}")

    def near(minute: int, top: bool) -> bool:   # an event close to a tick, on that side of the axis
        return any(m is not None and e.get("kind") != "shootout" and abs(m - minute) < 9 and (e["team"] == home) == top
                   for e, m in zip(timeline, minutes))

    ticks = "".join(f'<line x1="{x_of(m):.1f}" y1="{_AXIS_Y - 1}" x2="{x_of(m):.1f}" y2="{_AXIS_Y + 1}" '
                    f'stroke="var(--ma-ink,#111)" stroke-width="0.3"/>' for m in (0, 45, 90, 105, 120) if m <= end)
    ticks += "".join(f'<text x="{x_of(m) + 0.6:.1f}" y="{_AXIS_Y + (3.4 if near(m, True) and not near(m, False) else -1.4):.1f}" '
                     f'{_TEXT} font-size="2.3" fill="var(--ma-muted,#4A3A3C)">{m}\'</text>'
                     for m in (45, 90, 105) if m < end)
    band = (f'<rect x="{x_of(90):.1f}" y="{_AXIS_Y - 3}" width="{x_of(120) - x_of(90):.1f}" height="6" '
            f'fill="var(--ma-red,#B3122B)" opacity="0.08"/>' if extra else "")
    box = ""
    if shootout:
        winner = "var(--ma-red,#B3122B)" if shootout["team"] == home else "var(--ma-ink,#111)"
        word = "RIGORI" if lang == "it" else "PENALTIES"
        box = (f'<g><title>{shootout["team"]} · {word.lower()} {shootout["score"]} — «{shootout["quote"]}»</title>'
               f'<rect x="87" y="{_AXIS_Y - 4.5}" width="11.5" height="9" fill="none" stroke="var(--ma-ink,#111)" '
               f'stroke-width="0.4"/><text x="92.75" y="{_AXIS_Y - 0.8}" {_TEXT} font-size="2.4" text-anchor="middle" '
               f'fill="var(--ma-muted,#4A3A3C)">{word}</text><text x="92.75" y="{_AXIS_Y + 3.2}" {_TEXT} '
               f'font-size="3.3" font-weight="700" text-anchor="middle" fill="{winner}">{shootout["score"]}</text></g>')
    axis = (f'<line class="ma-{key}-axis" x1="{x0}" y1="{_AXIS_Y}" x2="{x1}" y2="{_AXIS_Y}" pathLength="100" '
            f'stroke="var(--ma-ink,#111)" stroke-width="0.5"/>')
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
    title_size = min(3.6, (100 - 2 * x0) / max(len(match) * 0.5, 1))
    header = (f'<text x="{x0}" y="{header_y - 4.6:.1f}" {_TEXT} font-size="2.6" font-weight="700" letter-spacing="0.4" '
              f'fill="var(--ma-muted,#4A3A3C)">{kicker}</text>'
              f'<text x="{x0}" y="{header_y:.1f}" {_TEXT} font-size="{title_size:.2f}" font-weight="700" '
              f'fill="var(--ma-ink,#111)">{match}</text>')
    caption = (f"{_LEGEND[lang]} From the card {card.get('id', '')}: minutes and names as the card writes them."
               if english else
               f"{_LEGEND[lang]} Dalla scheda {card.get('id', '')}: minuti e nomi come li scrive la scheda.")
    style = (f"<style>{' '.join(css)} @media (prefers-reduced-motion: reduce) {{ [class^=\"ma-{key}-\"] "
             f"{{ animation: none !important; }} }}</style>" if css else "")
    top_view = header_y - 8.5
    return (f'<figure class="ma-figure ma-timeline" style="margin:0.5rem 0 0">{style}'
            f'<svg viewBox="0 {top_view:.1f} 100 {bottom_y - top_view:.1f}" role="img" '
            f'aria-label="{"Timeline" if english else "Linea del tempo"}: {card.get("title", "")}" '
            f'style="width:100%;height:auto;display:block">{header}{band}{axis}{ticks}{"".join(marks)}{box}</svg>'
            f'<figcaption style="font-family:\'IBM Plex Sans Condensed\',sans-serif;font-size:12px;'
            f'color:var(--ma-muted,#4A3A3C)">{caption}</figcaption></figure>')


# ---------------------------------------------------------------- under which answer
ANSWERED = ("football", "follow_up")   # the input guard's verdicts of a question the agent answered


def real_cases(answer: str) -> list[str]:
    """The finals the real-case lines of an answer cite (the line written by code from the card)."""
    return list(dict.fromkeys(i for m in CASE_LINE_RE.finditer(answer) for i in case_ids(m.group("rest"))))


def answer_figures(messages: list[dict], index: int, cards: dict[str, dict], animate: bool = True) -> list[str]:
    """The graphics under the answer `messages[index]`, for a question the agent answered (not one
    stopped by the input guard): the pitch, when its own question names a formation of the coach or
    of the opponent (the other side may come from an earlier question of the chat); the timeline of
    every final its real-case line cites."""
    message = messages[index]
    if message.get("role") != "assistant" or (message.get("guard") or {}).get("input") not in ANSWERED:
        return []
    questions = [m["content"] for m in messages[:index] if m.get("role") == "user"]
    english = bool(questions) and detect_language(questions[-1]) == "en"
    figures = []
    if questions and formations_in(questions[-1]):
        figures.append(formations_svg(coach_formations(questions), english=english, animate=animate))
    for case_id in real_cases(message.get("content", "")):
        if case_id in cards:
            figures.append(timeline_svg(cards[case_id], english=english, animate=animate))
    return [f for f in figures if f]
