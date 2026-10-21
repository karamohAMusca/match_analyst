"""The numbers of a final, the two teams side by side, from the "## Numeri" table of its card.

The table is read as the card writes it (`final_numbers`): the teams of its header row, checked
against the card's title and put in its order; every value with its own text ("20 (10)", "60,2%",
"32,5% (7,4% contesa)") and the numbers in it; the source in the heading and the notes after the
table, which go into the caption. A value that cannot be read for sure leaves its row out: a wrong
bar is worse than none.

One row per metric, each with its own scale (the units differ): a bar split between the two teams in
proportion to their values, the first team of the title red and filled, the other ink and hollow
(the timeline's convention), the team names and symbols as direct labels. A share the card gives to
neither team (the contested possession) is a light neutral between the two, with its own label:
MUTED at 35%, checked with a palette validator on the app's surfaces next to red and ink (ΔE 23
light, 18 dark for colour-blind readers); below 3:1 against the page, it is never drawn without its
label. PPDA reads the other way (lower means more pressing): the figure says so in the glossary's words.
"""

from __future__ import annotations

import re

from src.guardrails.text import LEAD_RE, normalize
from src.ui.graphics.badges import badge_width, team_badge
from src.ui.graphics.svg import CARD, INK, MUTED, RED, TEXT, TITLE_TEAMS_RE, esc, figcaption, figure_key, motion_style

# "## Numeri (intera partita, StatsBomb)" or "## Numeri": the source, when there is one, in brackets
_HEADING_RE = re.compile(r"^##[ \t]+Numeri(?:[ \t]*\((?P<source>[^()\n]+)\))?[ \t]*$", re.MULTILINE)
_SEPARATOR_RE = re.compile(r":?-{3,}:?")
_NUMBER = r"\d+(?:[.,]\d+)?"
# A value: a number, a percentage or not, maybe a part in brackets with a number and words
# ("20 (10)", "2.76", "60,2%", "32,5% (7,4% contesa)"); nothing else
_VALUE_RE = re.compile(rf"({_NUMBER})\s*%?(?:\s*\(({_NUMBER})\s*%?(?:\s+[^\W\d_]+(?:['’][^\W\d_]+)*)*\))?")
_THOUSANDS_RE = re.compile(r"[1-9]\d{0,2}[.,]\d{3}")   # "1.234": a thousand or a decimal? Not read
_SHARE_RE = re.compile(rf"\(({_NUMBER}\s*%\s+[^()]+)\)")   # "(7,4% contesa)": a share, with its words
# The words that name a metric of the table, compared without case or accents ("Tiri (in porta)" is
# "tiri"); a metric not listed is named by its own words. Not "passaggio" (also a change of shape:
# "il passaggio alla difesa a tre"), nor "pressing": PPDA measures it, but it is not its name.
_METRIC_WORDS = {
    "possesso": ("possesso", "possession"),
    "tiri": ("tiri", "tiro", "shots"),
    "xg": ("xg", "expected goals", "gol attesi", "gol previsti"),
    "quota passaggi": ("passaggi", "passes", "pass share"),
    "field tilt": ("field tilt",),
    "ppda": ("ppda",),
}
# A metric where lower means more: the card that says so, its words, the same in English
READS_LOWER = {"ppda": ("glossary_metriche", "più è basso, più il pressing è aggressivo",
                        "the lower, the more aggressive the pressing")}
_MARKS = "*†‡§"   # a note after the table that names a row: the same mark on the row and in the caption
_X0, _X1 = 2.0, 98.0   # the ends of every bar, the first team of the title on the left
_BAR, _GAP, _RADIUS, _STROKE = 2.6, 0.6, 0.8, 0.4
_VALUE, _LABEL = 3.4, 3.0   # font sizes: the card's values; the metrics and the lines under a bar


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _numbers(text: str) -> list[float] | None:
    """The numbers a value writes ("32,5% (7,4% contesa)": [32.5, 7.4]); None when it cannot be read
    for sure: anything else in it, or a point or a comma that may group thousands ("1.234")."""
    match = _VALUE_RE.fullmatch(text)
    if not match or any(_THOUSANDS_RE.fullmatch(n) for n in match.groups() if n):
        return None
    return [float(n.replace(",", ".")) for n in match.groups() if n]


def final_numbers(card: dict) -> dict | None:
    """The "## Numeri" table of a match card: {"teams": [first, second] in the order of the title,
    "source": the words in brackets in the heading ("" without), "rows": [{"metric", "texts": each
    team's value as written, "numbers": the numbers in each}], "notes": the lines after the table}.
    None without a table or when its teams are not the title's; a row with a value that cannot be
    read is left out."""
    teams = TITLE_TEAMS_RE.search(card.get("title", ""))
    heading = _HEADING_RE.search(card.get("body", ""))
    if not teams or not heading:
        return None
    lines = card["body"][heading.end():].splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip()), len(lines))
    end = next((i for i in range(start, len(lines)) if not lines[i].lstrip().startswith("|")), len(lines))
    table = [_cells(line) for line in lines[start:end]]
    home, away = teams["home"], teams["away"]
    if not table or table[0][1:] not in ([home, away], [away, home]):
        return None
    columns = (1, 2) if table[0][1:] == [home, away] else (2, 1)   # the header's order checked, not assumed
    rows = []
    for cells in table[1:]:
        if len(cells) != 3 or not cells[0] or all(_SEPARATOR_RE.fullmatch(c) for c in cells):
            continue
        texts = [cells[c] for c in columns]
        numbers = [_numbers(text) for text in texts]
        if None not in numbers:
            rows.append({"metric": cells[0], "texts": texts, "numbers": numbers})
    notes = []
    for line in lines[end:]:
        if line.lstrip().startswith("#"):
            break
        if line.strip():
            notes.append(LEAD_RE.sub("", line).replace("**", "").strip())
    return {"teams": [home, away], "source": (heading["source"] or "").strip(), "rows": rows, "notes": notes}


def _metric_name(metric: str) -> str:
    """A metric as the word lists know it: no brackets, case or accents ("Tiri (in porta)": "tiri")."""
    return normalize(re.sub(r"\([^)]*\)", " ", metric)).strip()


def _named(plain: str, metric: str) -> bool:
    """Whether a normalized text names a metric, in whole words ("possession-based" does)."""
    name = _metric_name(metric)
    for words in _METRIC_WORDS.get(name, (name,) if name else ()):
        pattern = r"[\s-]+".join(map(re.escape, words.split()))
        if re.search(rf"(?<!\w){pattern}(?!\w)", plain):
            return True
    return False


def names_a_number(text: str, card: dict) -> bool:
    """Whether a text (the coach's question or the answer) names a metric of the card's "Numeri"
    table: "possesso"/"possession", "tiri"/"tiro"/"shots", "xG", "passaggi"/"passes", "field tilt",
    "PPDA", in whole words, without case or accents. A metric the table does not have does not count:
    "possesso" is not the "Quota passaggi" of a table without "Possesso"."""
    numbers = final_numbers(card)
    plain = normalize(text or "")
    return bool(numbers) and any(_named(plain, row["metric"]) for row in numbers["rows"])


def _shared(row: dict) -> tuple[float, str] | None:
    """A share of the whole that the card gives to neither team, in brackets after a team's value
    ("32,5% (7,4% contesa)"), and its words: only when it and the two teams' percentages add up to
    100 (a part of a team's own value, as the shots on target, is not one)."""
    (first, *_), (second, *_) = row["numbers"]
    for text, numbers in zip(row["texts"], row["numbers"]):
        share = _SHARE_RE.search(text)
        if (share and all("%" in t.split("(")[0] for t in row["texts"])
                and abs(first + second + numbers[-1] - 100) <= 1):
            return numbers[-1], share[1]
    return None


def _width(text: str, size: float, bold: bool = False) -> float:
    """The room a label takes, a little more than the font's (measured on a wider sans-serif)."""
    return len(text) * size * (0.55 if bold else 0.5)


def _bar(base: float, end: float, y: float, height: float) -> str:
    """The path of a bar from its baseline `base` (square) to its data end `end` (rounded), either way."""
    sign, sweep = (1, 1) if end >= base else (-1, 0)
    r = min(_RADIUS, abs(end - base), height / 2)
    return (f"M {base:.2f} {y:.2f} H {end - sign * r:.2f} A {r:.2f} {r:.2f} 0 0 {sweep} {end:.2f} {y + r:.2f} "
            f"V {y + height - r:.2f} A {r:.2f} {r:.2f} 0 0 {sweep} {end - sign * r:.2f} {y + height:.2f} H {base:.2f} Z")


def _hit(x0: float, y0: float, x1: float, y1: float) -> str:
    """A transparent area that takes the pointer for a part's tooltip, larger than the part."""
    return f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{x1 - x0:.1f}" height="{y1 - y0:.1f}" fill="transparent"/>'


def numbers_svg(card: dict, english: bool = False, animate: bool = True) -> str:
    """The numbers of a final, one row per metric of its table in the card's order: the metric over a
    bar split between the two teams in proportion to their values, each team's value at its end as
    the card writes it, a tooltip on every part; under the bar, the label of a share that is neither
    team's and the reading of a metric where lower means more. Animated: the bars grow from their ends
    to the split, row after row. Empty without a table."""
    numbers = final_numbers(card)
    if not numbers or not numbers["rows"]:
        return ""
    home, away = numbers["teams"]
    key = figure_key(card.get("id") or card.get("title"), "numbers", english, animate)   # not the timeline's key
    marks: dict[str, str] = {}
    notes, used = [], 0
    for note in numbers["notes"]:
        named = [row["metric"] for row in numbers["rows"] if _named(normalize(note), row["metric"])]
        mark = _MARKS[used % len(_MARKS)] if named else ""
        used += bool(named)
        for metric in named:
            marks[metric] = marks.get(metric, "") + mark
        notes.append(f"{mark} {note}".strip())

    body, css = [], []
    y = 17.0   # the top of a row: the metric, the values, the bar, the lines under it
    for i, row in enumerate(numbers["rows"]):
        metric, texts = row["metric"], row["texts"]
        label = metric + marks.get(metric, "")
        size = min(_VALUE, _VALUE * (_X1 - _X0 - 2) / (_width(texts[0], _VALUE, True) + _width(texts[1], _VALUE, True)))
        widths = (_width(texts[0], size, True), _width(texts[1], size, True))
        room = _width(label, _LABEL) / 2 + 1.5
        inline = _X0 + widths[0] <= 50 - room and 50 + room <= _X1 - widths[1]
        values_y = y + (2.8 if inline else 6.6)   # the metric on a line of its own when the values leave no room
        bar_y = values_y + 1.4
        low = bar_y + _BAR
        body.append(f'<text x="50" y="{y + 2.8:.1f}" {TEXT} font-size="{_LABEL}" text-anchor="middle" '
                    f'fill="{MUTED}">{esc(label)}</text>')
        shared = _shared(row)
        parts = [(value, part) for value, part in ((row["numbers"][0][0], "h"), (shared[0] if shared else 0, "c"),
                                                   (row["numbers"][1][0], "a")) if value > 0]
        total, length = sum(v for v, _ in parts), _X1 - _X0 - _GAP * (len(parts) - 1)
        spans, x = {}, _X0
        for value, part in parts:
            spans[part] = (x, x + length * value / total)
            x = spans[part][1] + _GAP
        for part, team, text, width in (("h", home, texts[0], widths[0]), ("a", away, texts[1], widths[1])):
            first = part == "h"
            name = f"ma-{key}-r{i}{part}"
            hit = _hit(_X0 if first else _X1 - width, values_y - size, _X0 + width if first else _X1, bar_y - 0.7)
            bar = ""
            if part in spans:
                start, stop = spans[part]
                hit += _hit(start, bar_y - 0.7, stop, low + 0.7)
                bar = (f'<path class="{name}" d="{_bar(start, stop, bar_y, _BAR)}" fill="{RED}"/>' if first else
                       f'<path class="{name}" d="{_bar(stop - _STROKE / 2, start + _STROKE / 2, bar_y + _STROKE / 2, _BAR - _STROKE)}" '
                       f'fill="{CARD}" stroke="{INK}" stroke-width="{_STROKE}"/>')
                if animate:   # from the team's end of the bar to the split, row after row
                    css.append(f".{name} {{ transform-box: fill-box; transform-origin: {'left' if first else 'right'} center; "
                               f"animation: ma-{key}-grow 0.7s cubic-bezier(.2,.8,.2,1) {0.2 + 0.18 * i:.2f}s both; }}")
            body.append(f'<g><title>{esc(team)} · {esc(metric)} · {esc(text)}</title>{hit}{bar}'
                        f'<text x="{_X0 if first else _X1}" y="{values_y:.1f}" {TEXT} font-size="{size:.2f}" font-weight="700" '
                        f'text-anchor="{"start" if first else "end"}" fill="{INK}">{esc(text)}</text></g>')

        under = 0   # the lines under the bar, 3.8 apart
        if "c" in spans:
            start, stop = spans["c"]
            width = _width(shared[1], _LABEL)
            centre = min(max((start + stop) / 2, _X0 + width / 2), _X1 - width / 2)
            name = f"ma-{key}-r{i}c"
            body.append(f'<g><title>{esc(metric)} · {esc(shared[1])}</title>{_hit(start, bar_y - 0.7, stop, low + 0.7)}'
                        f'{_hit(centre - width / 2, low + 0.7, centre + width / 2, low + 4.3)}'
                        f'<rect class="{name}" x="{start:.2f}" y="{bar_y:.2f}" width="{stop - start:.2f}" height="{_BAR}" '
                        f'rx="{min(_RADIUS, (stop - start) / 2):.2f}" fill="{MUTED}" fill-opacity="0.35"/>'
                        f'<text x="{centre:.1f}" y="{low + 3.3:.1f}" {TEXT} font-size="{_LABEL}" text-anchor="middle" '
                        f'fill="{MUTED}">{esc(shared[1])}</text></g>')
            if animate:   # after the two teams' parts, from its middle
                css.append(f".{name} {{ transform-box: fill-box; transform-origin: center; "
                           f"animation: ma-{key}-grow 0.5s ease-out {0.5 + 0.18 * i:.2f}s both; }}")
            under += 1
        if reading := READS_LOWER.get(_metric_name(metric)):
            glossary, said, said_en = reading
            line = f"{said_en} ({glossary})" if english else f"«{said}» ({glossary})"
            body.append(f'<text x="50" y="{low + 3.3 + 3.8 * under:.1f}" {TEXT} '
                        f'font-size="{min(_LABEL, (_X1 - _X0) / (len(line) * 0.5)):.2f}" text-anchor="middle" '
                        f'fill="{MUTED}">{esc(line)}</text>')
            under += 1
        y = low + 3.4 + 3.8 * under
    if animate:
        css.insert(0, f"@keyframes ma-{key}-grow {{ from {{ transform: scaleX(0); }} to {{ transform: scaleX(1); }} }}")

    # "Finale Mondiale 2026: Spagna 1-0 Argentina (d.t.s.)": the competition on the small line, the match
    # on the big one, each smaller if it is still too long for the width
    competition, _, match = card.get("title", "").rpartition(": ")
    kicker = ("THE NUMBERS OF THE FINAL" if english else "I NUMERI DELLA FINALE") + (
        f" · {competition.upper()}" if competition else "")
    kicker_size = min(3.0, (96 - 0.3 * len(kicker)) / (0.58 * len(kicker)))
    title_size = min(3.6, 96 / max(len(match) * 0.5, 1))
    header = (f'<text x="2" y="3.2" {TEXT} font-size="{kicker_size:.2f}" font-weight="700" letter-spacing="0.3" '
              f'fill="{MUTED}">{esc(kicker)}</text>'
              f'<text x="2" y="8.0" {TEXT} font-size="{title_size:.2f}" font-weight="700" fill="{INK}">{esc(match)}</text>')
    # the legend: each team's bar, symbol and name on its own side of the bars
    badge, legend_y = 3.4, 10.6
    swatch_y = legend_y + (badge - _BAR) / 2
    legend = (f'<path d="{_bar(_X0, _X0 + 4, swatch_y, _BAR)}" fill="{RED}"/>{team_badge(home, _X0 + 5, legend_y, badge)}'
              f'<text x="{_X0 + 6 + badge_width(home, badge):.1f}" y="{legend_y + 2.85:.1f}" {TEXT} font-size="3.2" '
              f'font-weight="700" fill="{INK}">{esc(home)}</text>'
              f'<path d="{_bar(_X1 - _STROKE / 2, _X1 - 4 + _STROKE / 2, swatch_y + _STROKE / 2, _BAR - _STROKE)}" '
              f'fill="{CARD}" stroke="{INK}" stroke-width="{_STROKE}"/>'
              f'{team_badge(away, _X1 - 5 - badge_width(away, badge), legend_y, badge)}'
              f'<text x="{_X1 - 6 - badge_width(away, badge):.1f}" y="{legend_y + 2.85:.1f}" {TEXT} font-size="3.2" '
              f'font-weight="700" text-anchor="end" fill="{INK}">{esc(away)}</text>')

    source = f" ({esc(numbers['source'])})" if numbers["source"] else ""
    caption = (f"From the Numeri table of the card {esc(card.get('id', ''))}{source}: the values as the card writes "
               f"them; each bar is split in proportion to the values of its row." if english else
               f"Dalla tabella Numeri della scheda {esc(card.get('id', ''))}{source}: i valori come li scrive la "
               f"scheda; ogni barra è divisa in proporzione ai valori della sua riga.")
    caption += "".join(f" {esc(note)}" for note in notes)
    for row in numbers["rows"]:
        if reading := READS_LOWER.get(_metric_name(row["metric"])):
            glossary, said, said_en = reading
            caption += (f" {esc(row['metric'])}: {said_en} («{said}», {glossary})." if english else
                        f" {esc(row['metric'])}: «{said}» ({glossary}).")
    # read aloud instead of the drawing: every value, as the card writes it
    described = "; ".join(f"{row['metric']}: {home} {row['texts'][0]}, {away} {row['texts'][1]}" for row in numbers["rows"])
    return (f'<figure class="ma-figure ma-numbers" style="margin:0.5rem 0 0">{motion_style(css, key)}'
            f'<svg viewBox="0 0 100 {y - 2.4:.1f}" role="img" '
            f'aria-label="{"The numbers of the final" if english else "I numeri della finale"}: '
            f'{esc(card.get("title", ""))}. {esc(described)}" '
            f'style="width:100%;height:auto;display:block">{header}{legend}{"".join(body)}</svg>'
            f"{figcaption(caption)}</figure>")
