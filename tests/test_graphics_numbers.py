"""The numbers of a final (src/ui/graphics/match_numbers.py), offline: the "## Numeri" table of a match
card read as it is written, the bars drawn from it, and the texts that name one of its metrics."""

from __future__ import annotations

import html
import re

import pytest

from src.ui.graphics.match_numbers import READS_LOWER, final_numbers, names_a_number, numbers_svg
from src.ui.graphics.timeline import timeline_svg
from src.ui.view import load_card_index

CARDS = load_card_index()
WC22, EURO24, WC26 = ("case_2022_wc_final_argentina_france", "case_2024_euro_final_spain_england",
                      "case_2026_wc_final_spain_argentina")
WC26_BODY = CARDS[WC26]["body"]


def _classes(svg: str) -> set[str]:
    return set(re.findall(r'class="(ma-[0-9a-f]{6}-[\w-]+)"', svg))


def _spans(svg: str) -> dict[int, dict[str, tuple[float, float]]]:
    """Where each part of each row's bar starts and ends, in units: "h" the first team, "a" the other
    (drawn inset by half its outline, 0.2), "c" a share that is neither team's."""
    spans: dict[int, dict[str, tuple[float, float]]] = {}
    for row, part, base, end in re.findall(r'class="ma-[0-9a-f]{6}-r(\d+)([ha])" d="M ([\d.]+) [\d.]+ '
                                           r'H [\d.]+ A [\d.]+ [\d.]+ 0 0 \d ([\d.]+)', svg):
        base, end = float(base), float(end)
        spans.setdefault(int(row), {})[part] = (base, end) if part == "h" else (end - 0.2, base + 0.2)
    for row, x, width in re.findall(r'class="ma-[0-9a-f]{6}-r(\d+)c" x="([\d.]+)" y="[\d.]+" width="([\d.]+)"', svg):
        spans.setdefault(int(row), {})["c"] = (float(x), float(x) + float(width))
    return spans


# ---------------------------------------------------------------- the table, as the card writes it
@pytest.mark.parametrize("case_id, teams, source, rows", [
    (WC22, ["Argentina", "Francia"], "intera partita, StatsBomb", [
        ("Tiri (in porta)", ["20 (10)", "10 (5)"], [[20, 10], [10, 5]]),
        ("xG", ["2.76", "2.27"], [[2.76], [2.27]]),
        ("Quota passaggi", ["55%", "45%"], [[55], [45]]),
        ("Field tilt", ["62%", "38%"], [[62], [38]])]),
    (EURO24, ["Spagna", "Inghilterra"], "intera partita, StatsBomb", [
        ("Quota passaggi", ["65%", "35%"], [[65], [35]]),
        ("Tiri (in porta)", ["16 (6)", "9 (3)"], [[16, 6], [9, 3]]),
        ("xG", ["1.79", "0.73"], [[1.79], [0.73]]),
        ("Field tilt", ["68%", "32%"], [[68], [32]]),
        ("PPDA", ["11.3", "22.2"], [[11.3], [22.2]])]),
    (WC26, ["Spagna", "Argentina"], "", [   # "## Numeri": no source in the heading
        ("Possesso", ["60,2%", "32,5% (7,4% contesa)"], [[60.2], [32.5, 7.4]]),
        ("Tiri (in porta)", ["20 (12)", "2 (0)"], [[20, 12], [2, 0]]),
        ("xG", ["2.52", "0.07"], [[2.52], [0.07]])]),
])
def test_the_numeri_table_as_the_card_writes_it(case_id, teams, source, rows):
    card = CARDS[case_id]
    numbers = final_numbers(card)
    assert numbers["teams"] == teams and card["title"].index(teams[0]) < card["title"].index(teams[1])
    assert numbers["source"] == source
    assert [(r["metric"], r["texts"], r["numbers"]) for r in numbers["rows"]] == rows
    assert all(f"| {r['metric']} | {r['texts'][0]} | {r['texts'][1]} |" in card["body"] for r in numbers["rows"])


def test_the_note_after_the_table_of_the_2026_final():
    assert final_numbers(CARDS[WC26])["notes"] == ["Le fonti divergono sul possesso: la Wikipedia inglese riporta 65%-35%."]
    assert final_numbers(CARDS[WC22])["notes"] == final_numbers(CARDS[EURO24])["notes"] == []


@pytest.mark.parametrize("case_id", ["case_2023_ucl_final_city_inter", "case_2025_ucl_final_psg_inter", "glossary_metriche"])
def test_a_card_without_a_table(case_id):
    assert final_numbers(CARDS[case_id]) is None and numbers_svg(CARDS[case_id]) == ""
    assert not names_a_number("possesso, tiri, xG, passaggi, field tilt e PPDA", CARDS[case_id])
    no_table = dict(CARDS[WC26], body="## Numeri\n\nNessun dato.\n")      # the heading alone is not a table
    assert final_numbers(no_table) is None and numbers_svg(no_table) == ""


@pytest.mark.parametrize("written", ["n.d.", "circa 20", "20-25", "1.234", "20 (12", "-3", "20 (12) tiri", ""])
def test_a_value_that_cannot_be_read_leaves_its_row_out(written):
    card = dict(CARDS[WC26], body=WC26_BODY.replace("| 20 (12) |", f"| {written} |"))
    assert [row["metric"] for row in final_numbers(card)["rows"]] == ["Possesso", "xG"]   # no guessed bar
    svg = numbers_svg(card)
    assert "Tiri (in porta)" not in svg and "<title>Spagna · Possesso · 60,2%</title>" in svg


def test_the_teams_of_the_header_are_checked_against_the_title():
    swapped = dict(CARDS[WC26], body=WC26_BODY.replace("| | Spagna | Argentina |", "| | Argentina | Spagna |"))
    numbers = final_numbers(swapped)
    assert numbers["teams"] == ["Spagna", "Argentina"]                          # the title's order
    assert numbers["rows"][0]["texts"] == ["32,5% (7,4% contesa)", "60,2%"]     # each column with its team
    other = dict(CARDS[WC26], body=WC26_BODY.replace("| | Spagna | Argentina |", "| | Spagna | Francia |"))
    assert final_numbers(other) is None and numbers_svg(other) == ""             # whose column is it? Nothing


# ---------------------------------------------------------------- the bars
@pytest.mark.parametrize("case_id", [WC22, EURO24, WC26])
def test_a_bar_part_per_team_per_row_with_its_tooltip_and_the_card_s_values(case_id):
    numbers = final_numbers(CARDS[case_id])
    svg = numbers_svg(CARDS[case_id])
    rows, spans = numbers["rows"], _spans(svg)
    for i, row in enumerate(rows):
        for team, text in zip(numbers["teams"], row["texts"]):
            assert f"<title>{team} · {row['metric']} · {text}</title>" in svg      # every part, the card's own text
            assert f">{text}</text>" in svg
        values = {"h": row["numbers"][0][0], "a": row["numbers"][1][0]}
        if "c" in spans[i]:
            values["c"] = next(n[1] for n in row["numbers"] if len(n) > 1)
        widths = {part: stop - start for part, (start, stop) in spans[i].items()}
        assert widths.keys() == values.keys()
        for part, width in widths.items():   # each row on its own scale, split in proportion to its values
            assert width / sum(widths.values()) == pytest.approx(values[part] / sum(values.values()), abs=0.002)
        ordered = [spans[i][part] for part in ("h", "c", "a") if part in spans[i]]
        assert ordered[0][0] == 2.0 and ordered[-1][1] == pytest.approx(98.0)       # the same ends on every row
        assert all(left[1] < right[0] for left, right in zip(ordered, ordered[1:]))  # a gap between the parts
    # the first team of the title red and filled, the other ink and hollow, as in the timeline
    assert len(re.findall(r'-r\d+h" d="[^"]+" fill="var\(--ma-red,#B3122B\)"', svg)) == len(rows)
    assert len(re.findall(r'-r\d+a" d="[^"]+" fill="var\(--ma-card,#FBE9EA\)" stroke="var\(--ma-ink,#111\)"', svg)) == len(rows)
    assert "<script" not in svg


def test_the_contested_possession_of_the_2026_final():
    svg = numbers_svg(CARDS[WC26])
    spans = _spans(svg)[0]
    assert spans["h"][1] < spans["c"][0] < spans["c"][1] < spans["a"][0]           # between the two teams
    assert "<title>Possesso · 7,4% contesa</title>" in svg and ">7,4% contesa</text>" in svg   # its own label
    assert 'fill="var(--ma-muted,#4A3A3C)" fill-opacity="0.35"/>' in svg              # a light neutral
    assert ">32,5% (7,4% contesa)</text>" in svg                                     # the card's text, whole
    assert "c" not in _spans(svg)[1]   # the shots on target are part of the shots: in the text only ("20 (12)")


def test_the_note_is_in_the_caption_and_marks_its_row():
    svg = numbers_svg(CARDS[WC26])
    caption = svg.split("<figcaption")[1]
    assert "* Le fonti divergono sul possesso: la Wikipedia inglese riporta 65%-35%." in caption
    assert ">Possesso*</text>" in svg and ">Tiri (in porta)</text>" in svg
    assert "*" not in numbers_svg(CARDS[EURO24]).split("<figcaption")[1]


def test_ppda_reads_the_other_way_in_the_glossary_s_words():
    glossary, said, said_en = READS_LOWER["ppda"]
    assert said in CARDS[glossary]["body"] and "PPDA" in CARDS[glossary]["body"]     # the glossary's own words
    svg = numbers_svg(CARDS[EURO24])
    assert f">«{said}» ({glossary})</text>" in svg                                   # on the figure, under the bar
    assert f"PPDA: «{said}» ({glossary})." in svg.split("<figcaption")[1]
    english = numbers_svg(CARDS[EURO24], english=True)
    assert f">{said_en} ({glossary})</text>" in english and f"PPDA: {said_en} («{said}», {glossary})." in english
    assert said not in numbers_svg(CARDS[WC22]) + numbers_svg(CARDS[WC26])            # only with a PPDA row


def test_the_header_and_the_caption():
    svg = numbers_svg(CARDS[WC22])
    assert ">I NUMERI DELLA FINALE · FINALE MONDIALE 2022</text>" in svg and ">Argentina 3-3 Francia (4-2 d.c.r.)</text>" in svg
    assert "<title>Argentina</title>" in svg and "<title>Francia</title>" in svg      # the teams' symbols
    assert ">Argentina</text>" in svg and ">Francia</text>" in svg                    # and their names
    assert "Dalla tabella Numeri della scheda case_2022_wc_final_argentina_france (intera partita, StatsBomb):" in svg
    assert "Dalla tabella Numeri della scheda case_2026_wc_final_spain_argentina: " in numbers_svg(CARDS[WC26])
    assert ('aria-label="I numeri della finale: Finale Mondiale 2022: Argentina 3-3 Francia (4-2 d.c.r.). '
            'Tiri (in porta): Argentina 20 (10), Francia 10 (5); xG: Argentina 2.76, Francia 2.27;') in svg   # read aloud
    english = numbers_svg(CARDS[WC22], english=True)
    assert ">THE NUMBERS OF THE FINAL · FINALE MONDIALE 2022</text>" in english
    assert "From the Numeri table of the card case_2022_wc_final_argentina_france (intera partita, StatsBomb):" in english
    assert ">Tiri (in porta)</text>" in english and ">20 (10)</text>" in english   # the card's words stay as they are


def test_a_zero_has_no_bar_but_keeps_its_value_and_tooltip():
    card = {"id": "case_x", "title": "Finale Mondiale 2026: Spagna 1-0 Argentina",
            "body": "## Numeri\n| | Spagna | Argentina |\n|---|---|---|\n| Tiri | 5 | 0 |\n| Rigori | 0 | 0 |\n"}
    svg = numbers_svg(card)
    assert _spans(svg) == {0: {"h": (2.0, 98.0)}}                                    # nothing to split in the second row
    assert "<title>Argentina · Tiri · 0</title>" in svg and "<title>Spagna · Rigori · 0</title>" in svg


def test_the_text_of_a_card_is_escaped():
    card = {"id": "case_x", "title": 'Finale Coppa 2026: Brighton & Hove 1-0 Inter "B"',
            "body": ('## Numeri (fonte <A & B>)\n| | Brighton & Hove | Inter "B" |\n|---|---|---|\n'
                     '| Tiri <in area> | 5 (2) | 3 (1) |\n\nNota: "tiri" & <dati>.\n')}
    svg = numbers_svg(card)
    assert "Brighton &amp; Hove" in svg and "Inter &quot;B&quot;" in svg and "Tiri &lt;in area&gt;" in svg
    assert "(fonte &lt;A &amp; B&gt;)" in svg and "Nota: &quot;tiri&quot; &amp; &lt;dati&gt;." in svg
    assert "<in area>" not in svg and "& Hove" not in svg and "<dati>" not in svg and "<script" not in svg


_TEXT_RE = re.compile(r'<text x="([\d.]+)" y="([\d.]+)" [^>]*?font-size="([\d.]+)"([^>]*)>([^<]*)</text>')


@pytest.mark.parametrize("case_id", [WC22, EURO24, WC26])
@pytest.mark.parametrize("english", [False, True])
def test_the_labels_fit_and_never_overlap(case_id, english):
    # widths as a wide sans-serif draws them (Arial, measured: at most 0.58 of the size per character in
    # bold, 0.5 in regular), wider than the app's condensed font; the longest value is "32,5% (7,4% contesa)"
    svg = re.sub(r"<svg x=.*?</svg>", "", numbers_svg(CARDS[case_id], english=english))   # not the symbols
    height = float(re.search(r'viewBox="0 0 100 ([\d.]+)"', svg).group(1))
    boxes = []
    for x, y, size, attributes, text in _TEXT_RE.findall(svg):
        x, y, size, text = float(x), float(y), float(size), html.unescape(text)
        width = len(text) * (size * (0.58 if 'font-weight="700"' in attributes else 0.5)
                             + (0.3 if "letter-spacing" in attributes else 0))
        left = x - width / 2 if 'anchor="middle"' in attributes else x - width if 'anchor="end"' in attributes else x
        boxes.append((text, left, left + width, y - 0.75 * size, y + 0.25 * size))
        assert size >= 3.0, text                                                   # about 10 px on a phone
    assert len(boxes) >= 4 + 3 * len(final_numbers(CARDS[case_id])["rows"])
    for text, left, right, top, bottom in boxes:
        assert 0 <= left and right <= 100 and 0 <= top and bottom <= height, text   # inside the figure
    for n, a in enumerate(boxes):
        for b in boxes[n + 1:]:
            assert not (a[1] < b[2] and b[1] < a[2] and a[3] < b[4] and b[3] < a[4]), (a[0], b[0])


# ---------------------------------------------------------------- the motion
def test_animated_and_still():
    card = CARDS[WC26]
    moving, still = numbers_svg(card), numbers_svg(card, animate=False)
    assert "@keyframes" in moving and "prefers-reduced-motion: reduce" in moving and "animation: none !important" in moving
    assert "@keyframes" not in still and "<style>" not in still
    assert not _classes(moving) & _classes(still)              # the CSS of a page is shared by all its figures
    assert _classes(moving) == {c for c in re.findall(r"\.(ma-[0-9a-f]{6}-r\d+[hac]) \{", moving)}   # each one moves
    def drawing(svg: str) -> str:
        return re.sub(r"ma-[0-9a-f]{6}-", "ma-", svg[svg.index("<svg"):])
    assert drawing(moving) == drawing(still)                   # still, the whole chart: the same drawing
    assert not _classes(moving) & _classes(numbers_svg(card, english=True))


def test_the_timeline_of_the_same_final_keeps_its_own_names():
    # under an answer the two figures of a final share the page: each has its own key, so not a name
    card = CARDS[WC26]
    timeline, numbers = timeline_svg(card), numbers_svg(card)
    assert re.search(r'class="ma-([0-9a-f]{6})-axis"', timeline)[1] != re.search(r'class="ma-([0-9a-f]{6})-r0h"', numbers)[1]
    assert not _classes(timeline) & _classes(numbers)
    assert not set(re.findall(r"@keyframes (\S+)", timeline)) & set(re.findall(r"@keyframes (\S+)", numbers))


def test_the_bars_grow_from_their_ends_row_after_row():
    moving = numbers_svg(CARDS[EURO24])
    rules = re.findall(r"\.ma-[0-9a-f]{6}-r(\d+)([ha]) \{ transform-box: fill-box; transform-origin: (\w+) center; "
                       r"animation: ma-[0-9a-f]{6}-grow [\d.]+s \S+ ([\d.]+)s both; \}", moving)
    assert {(part, origin) for _, part, origin, _ in rules} == {("h", "left"), ("a", "right")}
    delays = [float(delay) for _, part, _, delay in rules if part == "h"]
    assert len(delays) == 5 and delays == sorted(set(delays))
    assert re.search(r"@keyframes ma-[0-9a-f]{6}-grow \{ from \{ transform: scaleX\(0\); \} "
                     r"to \{ transform: scaleX\(1\); \} \}", moving)


# ---------------------------------------------------------------- does a text name one of the numbers?
@pytest.mark.parametrize("text, case_id, expected", [
    ("Quanto possesso aveva la Spagna?", WC26, True),
    ("How much possession did Spain have?", WC26, True),
    ("Una squadra possession-based", WC26, True),              # a hyphen ends a word
    ("Quanti tiri in porta ha fatto la Spagna?", WC26, True),
    ("Un tiro solo in novanta minuti", WC26, True),
    ("How many shots on target?", WC26, True),
    ("Gli XG delle due squadre", WC26, True),                  # without case
    ("Gli expected goals", WC22, True),
    ("La quota passaggi", WC22, True),
    ("I passaggi corti", EURO24, True),
    ("Spain's passes", EURO24, True),
    ("Il Field Tilt della Spagna", EURO24, True),
    ("Il field-tilt", WC22, True),
    ("il ppda inglese", EURO24, True),
    # the near misses
    ("Il passaggio alla difesa a tre", WC22, False),           # "passaggio": also a change of shape
    ("Spain's passing game", EURO24, False),
    ("Come faccio pressing alto?", EURO24, False),             # PPDA measures it, but it is not its name
    ("Quanti xGA ha concesso?", WC22, False),                  # another metric
    ("Il possessore palla", WC26, False),
    ("Tiriamo da fuori?", WC26, False),
    ("Un tirocinio", WC26, False),
    ("A great shot-stopper", WC26, False),
    ("I numeri e le statistiche della finale", WC26, False),   # numbers, but no metric named
    ("Il possesso della Francia", WC22, False),                # the 2022 table has "Quota passaggi", not "Possesso"
    ("E il PPDA?", WC26, False),                               # the 2026 table has no PPDA
    ("", WC26, False),
])
def test_names_a_number(text, case_id, expected):
    assert names_a_number(text, CARDS[case_id]) is expected
