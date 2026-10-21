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
import json
import re
from collections.abc import Iterable
from functools import lru_cache

from src.core.config import PROJECT_ROOT
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


# ---------------------------------------------------------------- the teams' symbols
# No club crest and no competition logo: they are registered trademarks and protected artwork. The
# national teams get their country's flag (a public symbol of the State, drawn here, simplified: no
# coat of arms), the clubs a neutral shield with their initials in the club's colours (colours alone are
# not a logo). Everything is drawn by code: nothing is downloaded.
_FLAGS = {   # viewBox 0 0 30 20
    "Argentina": '<rect width="30" height="20" fill="#74ACDF"/><rect y="6.67" width="30" height="6.67" fill="#FFFFFF"/>'
                 '<circle cx="15" cy="10" r="2.2" fill="#F6B40E"/>',
    "Francia": '<rect width="10" height="20" fill="#0055A4"/><rect x="10" width="10" height="20" fill="#FFFFFF"/>'
               '<rect x="20" width="10" height="20" fill="#EF4135"/>',
    "Spagna": '<rect width="30" height="20" fill="#AA151B"/><rect y="5" width="30" height="10" fill="#F1BF00"/>',
    "Inghilterra": '<rect width="30" height="20" fill="#FFFFFF"/><rect x="12.5" width="5" height="20" fill="#CE1124"/>'
                   '<rect y="7.5" width="30" height="5" fill="#CE1124"/>',
    "Italia": '<rect width="10" height="20" fill="#009246"/><rect x="10" width="10" height="20" fill="#FFFFFF"/>'
              '<rect x="20" width="10" height="20" fill="#CE2B37"/>',
}
_CLUBS = {   # initials, shield colour, initials colour
    "Manchester City": ("MCI", "#6CABDD", "#1C2C5B"), "Inter": ("INT", "#0068A8", "#FFFFFF"),
    "Atalanta": ("ATA", "#1E71B8", "#111111"), "Bayer Leverkusen": ("B04", "#E32221", "#111111"),
    "Paris Saint-Germain": ("PSG", "#004170", "#FFFFFF"), "Arsenal": ("ARS", "#EF0107", "#FFFFFF"),
}
_SHIELD = "M1 1 H19 V12 C19 18.5 10 23 10 23 C10 23 1 18.5 1 12 Z"


def team_badge(team: str, x: float, y: float, height: float) -> str:
    """The team's symbol at (x, y), `height` tall: its flag for a national team, else a neutral shield
    with its initials (any club, the first three letters when it is not listed)."""
    if team in _FLAGS:
        width = height * 1.5
        return (f'<svg x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" viewBox="0 0 30 20">'
                f'<title>{team}</title>{_FLAGS[team]}<rect width="30" height="20" fill="none" '
                f'stroke="var(--ma-ink,#111)" stroke-width="0.8"/></svg>')
    initials, fill, ink = _CLUBS.get(team, (re.sub(r"[^A-Z]", "", team.upper())[:3], "#4A3A3C", "#FFFFFF"))
    y, height = y - height * 0.15, height * 1.3   # a shield is narrower than a flag: a little taller
    width = height * 20 / 24
    return (f'<svg x="{x:.1f}" y="{y:.1f}" width="{width:.1f}" height="{height:.1f}" viewBox="0 0 20 24">'
            f'<title>{team}</title><path d="{_SHIELD}" fill="{fill}" stroke="var(--ma-ink,#111)" stroke-width="0.9"/>'
            f'<text x="10" y="13.6" {_TEXT} font-size="6.4" font-weight="700" text-anchor="middle" '
            f'fill="{ink}">{initials}</text></svg>')


def badge_width(team: str, height: float) -> float:
    return height * (1.5 if team in _FLAGS else 1.3 * 20 / 24)



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
    x0, x1 = 11.0, (84.0 if shootout else 96.0)   # the teams' symbols before the axis

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
    badges = (team_badge(home, 2, _AXIS_Y - 5.6, 4.4) + team_badge(teams["away"], 2, _AXIS_Y + 1.2, 4.4))
    header = (f'<text x="2" y="{header_y - 4.6:.1f}" {_TEXT} font-size="2.6" font-weight="700" letter-spacing="0.4" '
              f'fill="var(--ma-muted,#4A3A3C)">{kicker}</text>'
              f'<text x="2" y="{header_y:.1f}" {_TEXT} font-size="{title_size:.2f}" font-weight="700" '
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
            f'style="width:100%;height:auto;display:block">{header}{badges}{band}{axis}{ticks}{"".join(marks)}{box}</svg>'
            f'<figcaption style="font-family:\'IBM Plex Sans Condensed\',sans-serif;font-size:12px;'
            f'color:var(--ma-muted,#4A3A3C)">{caption}</figcaption></figure>')


# ---------------------------------------------------------------- the action of a goal (StatsBomb)
# The touches before a goal of the finals with StatsBomb event data (scripts/build_goal_actions.py):
# where the ball went and when, at the real tempo of the match. The scoring team attacks left to right.
GOAL_ACTIONS = PROJECT_ROOT / "references" / "derived" / "statsbomb_goal_actions.json"
_STEP_WORDS = {"it": {"pass": "passaggio", "carry": "conduzione", "shot": "tiro"},
               "en": {"pass": "pass", "carry": "carry", "shot": "shot"}}
_MAX_SECONDS = 14.0   # a longer action is played faster, and the caption says so
_HOLD_SECONDS = 1.8   # the ball rests in the net before the action starts again
_MINUTE_RE = re.compile(r"\b(\d{1,3}')")
_PERIOD_NAMES = {"it": {1: "1° tempo", 2: "2° tempo", 3: "1° supplementare", 4: "2° supplementare"},
                 "en": {1: "1st half", 2: "2nd half", 3: "1st extra half", 4: "2nd extra half"}}


@lru_cache(maxsize=1)
def goal_actions() -> dict[str, list[dict]]:
    """{match card id: its goals of play with their actions}; empty if the derived file is missing."""
    if not GOAL_ACTIONS.exists():
        return {}
    data = json.loads(GOAL_ACTIONS.read_text(encoding="utf-8"))
    return {card_id: match["goals"] for card_id, match in data["matches"].items()}


def pick_goal(goals: list[dict], line: str) -> dict | None:
    """The goal a real-case line speaks of: the one at a minute it writes ("al 47'"), else the one whose
    scorer it names ("Palmer pareggia"; the latest, if he scored twice), else the action with the most
    touches."""
    written = set(_MINUTE_RE.findall(line))
    named = [g for g in goals if re.search(rf"(?<!\w){re.escape(g['scorer'])}(?!\w)", line)]
    return (next((g for g in goals if g["minute"] in written), None) or (named[-1] if named else None)
            or max(goals, key=lambda g: len(g["steps"]), default=None))


def goal_label(goal: dict, english: bool = False) -> str:
    """'36' 2-0 Di María', with '(rig.)' for a penalty; the period when the card gives no minute."""
    when = goal["minute"] or _PERIOD_NAMES["en" if english else "it"].get(goal.get("period"), "")
    penalty = (" (rig.)" if not english else " (pen.)") if goal.get("penalty") else ""
    return f"{when} {goal['score']} {goal['scorer']}{penalty}"


def goal_svg(goal: dict, card: dict, english: bool = False, animate: bool = True) -> str:
    """The action of a goal on the pitch: the passes (solid), the carries (dashed) and the shot (thick)
    drawn as the ball travels, at the real tempo; every player who touches the ball appears when he
    does, named; the ball rests in the net, then the action plays again. Still: the whole action."""
    steps = goal.get("steps") or []
    teams = _TITLE_TEAMS_RE.search(card.get("title", ""))
    if not steps or not teams:
        return ""
    lang = "en" if english else "it"
    colour = "var(--ma-red,#B3122B)" if goal["team"] == teams["home"] else "var(--ma-ink,#111)"
    length = steps[-1]["t1"]
    speed = max(length / _MAX_SECONDS, 1.0)
    total = length / speed + _HOLD_SECONDS
    key = hashlib.sha1(f"{card.get('id')}|{goal_label(goal)}".encode()).hexdigest()[:6]

    def pct(t: float) -> float:
        return min(100 * (t / speed) / total, 99.9)

    css, lines, dots = [], [], []
    seen: set[str] = set()
    previous = None
    for n, step in enumerate(steps):
        kind, p0, p1 = step["kind"], pct(step["t0"]), max(pct(step["t1"]), pct(step["t0"]) + 0.1)
        style = {"pass": 'stroke-width="0.45"', "carry": 'stroke-width="0.35" stroke-dasharray="1 0.8"',
                 "shot": 'stroke-width="0.9"'}[kind]
        line_class = f"ma-{key}-l{n}"
        tip = f"{step['player']}: {_STEP_WORDS[lang][kind]} ({step['t0']:.1f} s)"
        # a carry keeps its dashes: it is drawn by fading in, a pass or a shot by growing along its line
        path_length = "" if kind == "carry" else ' pathLength="100"'
        lines.append(f'<line class="{line_class}" x1="{step["x"]}" y1="{step["y"]}" x2="{step["x2"]}" y2="{step["y2"]}" '
                     f'stroke="{colour}" {style} stroke-linecap="round"{path_length}><title>{tip}</title></line>')
        if animate:
            if kind == "carry":
                css.append(f"@keyframes {line_class} {{ 0%, {p0:.2f}% {{ opacity: 0; }} {p1:.2f}%, 100% {{ opacity: 1; }} }}")
            else:
                css.append(f"@keyframes {line_class} {{ 0%, {p0:.2f}% {{ stroke-dashoffset: 100; }} "
                           f"{p1:.2f}%, 100% {{ stroke-dashoffset: 0; }} }} .{line_class} {{ stroke-dasharray: 100; }}")
            css.append(f".{line_class} {{ animation: {line_class} {total:.2f}s linear infinite; }}")
        if step["player"] != previous or kind == "shot":   # a new touch: the player, where he got the ball
            dot_class = f"ma-{key}-d{n}"
            label = ""
            if step["player"] not in seen or kind == "shot":   # named once, and again where the goal is scored
                weight = ' font-weight="700"' if step["player"] == goal["scorer"] else ""
                label = (f'<text x="{step["x"]}" y="{step["y"] - 2.6:.1f}" {_TEXT} font-size="3"{weight} '
                         f'text-anchor="middle" fill="var(--ma-ink,#111)">{step["player"]}</text>')
                seen.add(step["player"])
            dots.append(f'<g class="{dot_class}"><title>{tip}</title><circle cx="{step["x"]}" cy="{step["y"]}" r="1.5" '
                        f'fill="{colour}" stroke="var(--ma-card,#FBE9EA)" stroke-width="0.5"/>{label}</g>')
            if animate:
                css.append(f"@keyframes {dot_class} {{ 0%, {p0:.2f}% {{ opacity: 0; }} {min(p0 + 1.5, 99.95):.2f}%, 100% "
                           f"{{ opacity: 1; }} }} .{dot_class} {{ animation: {dot_class} {total:.2f}s linear infinite; }}")
        previous = step["player"]

    end_x, end_y = steps[-1]["x2"], steps[-1]["y2"]
    if animate:   # the ball: at the start and at the end of every touch, at its real second
        frames = []
        for step in steps:
            frames += [(pct(step["t0"]), step["x"], step["y"]), (pct(step["t1"]), step["x2"], step["y2"])]
        frames.append((100.0, end_x, end_y))
        keyframes, last = [], -1.0
        for p, x, y in frames:
            p = max(p, last + 0.01)
            keyframes.append(f"{p:.2f}% {{ transform: translate({x}px, {y}px); }}")
            last = p
        css.append(f"@keyframes ma-{key}-ball {{ {' '.join(keyframes)} }} "
                   f".ma-{key}-ball {{ animation: ma-{key}-ball {total:.2f}s linear infinite; }}")
    ball = (f'<g class="ma-{key}-ball" style="transform: translate({end_x}px, {end_y}px)"><circle cx="0" cy="0" r="1.1" '
            f'fill="var(--ma-card,#FBE9EA)" stroke="var(--ma-ink,#111)" stroke-width="0.45"/></g>')

    competition = card.get("title", "").rpartition(": ")[0]
    kicker = ("THE GOAL" if english else "L'AZIONE DEL GOL") + (f" · {competition.upper()}" if competition else "")
    passes = sum(s["kind"] == "pass" for s in steps)
    count = (f"{passes} passes, {length:.0f} seconds" if english else
             f"{passes} passaggi in {length:.0f} secondi") if passes else ""
    header = (f'<text x="0" y="-9" {_TEXT} font-size="2.8" font-weight="700" letter-spacing="0.4" '
              f'fill="var(--ma-muted,#4A3A3C)">{kicker}</text>'
              f'{team_badge(goal["team"], 0, -7.4, 4.8)}'
              f'<text x="{badge_width(goal["team"], 4.8) + 1.4:.1f}" y="-3.5" {_TEXT} font-size="4.2" font-weight="700" '
              f'fill="{colour}">{goal_label(goal, english)}'
              f'<tspan fill="var(--ma-muted,#4A3A3C)" font-weight="500" font-size="3.2">{"  ·  " + count if count else ""}</tspan>'
              f'</text>')
    faster = (f" Played {speed:.1f} times faster." if english else f" Accelerata {speed:.1f} volte.") if speed > 1 else ""
    caption = ((f"Real positions and tempo of the ball: StatsBomb Open Data.{faster} Solid: pass · dashed: carry · "
                "thick: shot.") if english else
               (f"Posizioni e tempi reali del pallone: StatsBomb Open Data.{faster} Linea piena: passaggio · "
                "tratteggio: conduzione · spessa: tiro."))
    style = (f"<style>{' '.join(css)} @media (prefers-reduced-motion: reduce) {{ [class^=\"ma-{key}-\"] "
             f"{{ animation: none !important; }} }}</style>" if css else "")
    return (f'<figure class="ma-figure ma-goal" style="margin:0.5rem 0 0">{style}'
            f'<svg viewBox="-2 -14 124 96" role="img" aria-label="{"The goal" if english else "L&#39;azione del gol"}: '
            f'{goal_label(goal, english)}" style="width:100%;height:auto;display:block">'
            f'{header}{pitch_svg()}{"".join(lines)}{"".join(dots)}{ball}</svg>'
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
    every final its real-case line cites and, for a final with StatsBomb data, the action of a goal
    (the one at a minute the line writes, else the longest)."""
    message = messages[index]
    if message.get("role") != "assistant" or (message.get("guard") or {}).get("input") not in ANSWERED:
        return []
    questions = [m["content"] for m in messages[:index] if m.get("role") == "user"]
    english = bool(questions) and detect_language(questions[-1]) == "en"
    figures = []
    if questions and formations_in(questions[-1]):
        figures.append(formations_svg(coach_formations(questions), english=english, animate=animate))
    content = message.get("content", "")
    for case_id in real_cases(content):
        if case_id in cards:
            figures.append(timeline_svg(cards[case_id], english=english, animate=animate))
            line = next((m.group(0) for m in CASE_LINE_RE.finditer(content) if case_id in m.group(0)), "")
            if goal := pick_goal(goal_actions().get(case_id, []), line):
                figures.append(goal_svg(goal, cards[case_id], english=english, animate=animate))
    return [f for f in figures if f]
