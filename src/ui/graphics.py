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


# ---------------------------------------------------------------- under which answer
ANSWERED = ("football", "follow_up")   # the input guard's verdicts of a question the agent answered


def answer_figure(messages: list[dict], index: int, animate: bool = True) -> str:
    """The pitch under the answer `messages[index]`, when its own question names a formation of the
    coach or of the opponent; the other side may come from an earlier question of the chat. Only for
    a question the agent answered (not one stopped by the input guard)."""
    message = messages[index]
    if message.get("role") != "assistant" or (message.get("guard") or {}).get("input") not in ANSWERED:
        return ""
    questions = [m["content"] for m in messages[:index] if m.get("role") == "user"]
    if not questions or not formations_in(questions[-1]):
        return ""
    english = detect_language(questions[-1]) == "en"
    return formations_svg(coach_formations(questions), english=english, animate=animate)
