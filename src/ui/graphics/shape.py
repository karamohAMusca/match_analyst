"""How a coach's team changes shape on the pitch, from the coach's card.

The changes come from the `shape_changes:` of the card's front matter, each with the card's own words
(`quote`): a test checks that the quote, the two formations, the moment, the team and the card's
warning are in its text (tests/test_corpus.py). Two things are not in the cards, and the caption says
so: the places, the indicative ones of formation_places spread over more of the pitch (one team, no
opponent), and who goes where, the assignment with the shortest moves, easier along the flanks.

The team is red and filled, as the coach's team of formations_svg; its starting places ink, hollow and
faint; the kicker and the big line name the coach and the change, so the colour is never alone.
"""

from __future__ import annotations

from src.guardrails.output_guard import cited_ids
from src.ui.graphics.formations import as_formation, formation_places, written_formations
from src.ui.graphics.svg import (CARD, H, INK, MUTED, RED, TEXT, W, esc, figcaption, figure_key, motion_style,
                                 pitch_svg)

Place = tuple[float, float, str]   # x, y and the line, as formation_places gives them
_SPREAD = 2.0   # the outfield lines twice as far apart as in formation_places: from x=18 to x=90
_LOOP = 6       # seconds: the first shape held, to the second, held, back to the first
_LINE_NAMES = {"portiere": "goalkeeper", "difesa": "defence", "centrocampo": "midfield", "attacco": "attack"}
# The header: at least 3 units on the 124 of the view (about 10 px on a phone). A line wider than the
# pitch is drawn smaller, its width reckoned generously: _EM of the size a character, _CAP a capital
# (a timeline label is reckoned at 0.46).
_KICKER, _BIG, _CUE = 3.0, 4.6, 0.72   # font sizes; the cue after the formations at 0.72 of theirs
_EM, _CAP = 0.55, 0.7


def _places(formation: str) -> list[Place]:
    """formation_places on more of the pitch: the outfield lines from the edge of the own box (x=18) to
    x=90, as there is no opponent to leave half of it to; the goalkeeper where he is. Rounded to a
    tenth, as they are drawn."""
    keeper, *outfield = formation_places(formation)
    return [keeper] + [(round(18 + (x - 18) * _SPREAD, 1), round(y, 1), line) for x, y, line in outfield]


def _cost(start: Place, end: Place) -> tuple[int, int]:
    """What a player's move costs, in whole numbers (the places are in tenths: a tie stays a tie). First
    its squared length, so that two players stepping up a line each cost less than one running the
    length of the pitch, which a plain sum of lengths prefers (from 4-4-2 to 3-4-3, a centre-back
    becoming the third forward); the run up or down the pitch counted in proportion to how far from the
    touchline it starts, as the changes of the cards are made along the flanks (the wing-backs dropping
    into a back five, the winger and the full-back stepping up in the pressing, the false full-back),
    not through the middle. Then, of two equal choices, the wider player changes line."""
    (x0, y0, _), (x1, y1, _) = start, end
    dx, dy = round((x1 - x0) * 10), round((y1 - y0) * 10)
    wide = round(min(y0, H - y0) * 10)   # tenths from the nearer touchline, at most H / 2
    return dx * dx * wide // (H * 5) + dy * dy, (wide if dx else 0)


def least_movement(cost: list[list[tuple[int, ...]]]) -> list[int]:
    """The order with the least total cost, `order[i]` the place of player i: exact, by a dynamic
    programme over the sets of places already taken (2^n of them, 1024 for 10 outfield players, instead
    of the n! orders). A cost is a tuple of whole numbers, added term by term and compared in order; of
    equal totals the first found is kept, so the same shapes always give the same moves."""
    n = len(cost)
    # for each set of places (a bit each) given to the first players: the least total, and the place
    # the last of them took
    best: dict[int, tuple[tuple[int, ...], int]] = {0: (tuple(0 for _ in cost[0][0]) if n else (), -1)}
    for taken in range(1 << n):   # increasing: a set comes after every set it grows from
        total, player = best[taken][0], taken.bit_count()
        for place in range(n):
            if taken >> place & 1:
                continue
            grown, candidate = taken | 1 << place, tuple(a + b for a, b in zip(total, cost[player][place]))
            if grown not in best or candidate < best[grown][0]:
                best[grown] = (candidate, place)
    order, taken = [0] * n, (1 << n) - 1
    for player in reversed(range(n)):
        order[player] = best[taken][1]
        taken ^= 1 << order[player]
    return order


def shape_moves(first: str, second: str) -> list[tuple[Place, Place]]:
    """(place in the first shape, place in the second) of each of the 11 players, the goalkeeper first
    and where he is: the 10 outfield players go to the places of the second shape with the least
    movement."""
    starts, ends = _places(first), _places(second)
    order = least_movement([[_cost(a, b) for b in ends[1:]] for a in starts[1:]])
    return [(starts[0], ends[0])] + [(a, ends[1 + j]) for a, j in zip(starts[1:], order)]


def cited_shape_changes(answer: str, cards: dict[str, dict]) -> list[tuple[str, dict]]:
    """The (card id, change) pairs to draw under an answer: of each card it cites, in the order of the
    answer and once, the shape changes whose second formation a line citing the card, or a line citing
    no card (the opening line, often), writes ("il 3-5-2 diventa 5-3-2 senza palla [coach_inzaghi]"), so
    that a figure comes only with an answer that speaks of the change: not with a 4-4-2 (the first shape
    of Pioli's change) nor with a formation of a line citing another card."""
    pairs = []
    for card_id in cited_ids(answer):
        written = set().union(*(written_formations(line) for line in answer.splitlines()
                                if card_id in cited_ids(line) or not cited_ids(line)))
        pairs += [(card_id, change) for change in (cards.get(card_id) or {}).get("shape_changes") or []
                  if as_formation(str(change.get("to", ""))) in written]
    return pairs


def shape_svg(card: dict, change: dict, english: bool = False, animate: bool = True) -> str:
    """A coach's team changing shape: the players (red, filled) move from the places of the first
    formation (ink, hollow and faint, drawn throughout) to the second, hold, go back and hold, in a
    loop; a tooltip on each says his line in the one and in the other. Still: the second shape, with a
    thin line from each player's first place. Empty without two different formations and a quote."""
    first, second = as_formation(str(change.get("from", ""))), as_formation(str(change.get("to", "")))
    if not first or not second or first == second or not change.get("quote"):
        return ""
    key = figure_key(card.get("id"), change, english, animate)
    within = " in the " if english else " nel "
    trail_class = f' class="ma-{key}-trail"' if animate else ""
    css, trails, starts, players = [], [], [], []
    for i, ((x0, y0, line0), (x1, y1, line1)) in enumerate(shape_moves(first, second)):
        name = f"ma-{key}-p{i}"
        starts.append(f'<circle cx="{x0:.1f}" cy="{y0:.1f}" r="2" fill="none" stroke="{INK}" stroke-width="0.5" '
                      f'opacity="0.45"/>')
        if (x0, y0) != (x1, y1):
            trails.append(f'<line{trail_class} x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" stroke="{RED}" '
                          f'stroke-width="0.5" stroke-linecap="round" opacity="0.6"/>')
            if animate:   # from the first place, eased to the second, held there, back and held again
                at_first = f"transform: translate({x0 - x1:.1f}px, {y0 - y1:.1f}px);"
                css.append(f"@keyframes {name} {{ 0%, 15%, 90%, 100% {{ {at_first} }} 40%, 65% {{ transform: "
                           f"translate(0, 0); }} }} .{name} {{ animation: {name} {_LOOP}s ease-in-out infinite; }}")
        before, after = (_LINE_NAMES.get(line, line) if english else line for line in (line0, line1))
        players.append(f'<g class="{name}"><title>{before}{within}{first} → {after}{within}{second}</title>'
                       f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="4" fill="transparent"/>'
                       f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="2.3" fill="{RED}" stroke="{CARD}" stroke-width="0.6"/></g>')
    if animate and trails:   # moving, the players show the way; with reduced motion the trails show it
        css.append(f"@keyframes ma-{key}-trail {{ from, to {{ opacity: 0; }} }} "
                   f".ma-{key}-trail {{ animation: ma-{key}-trail 1s both; }}")

    coach = str(card.get("title", "")).split(": ", 1)[-1]   # "Profilo allenatore: Simone Inzaghi"
    kicker = " · ".join(filter(None, ["HOW THE SHAPE CHANGES" if english else "COME CAMBIA IL MODULO", coach.upper()]))
    cue = " · ".join(str(change[k]) for k in ("when", "how", "team") if change.get(k))   # the card's words
    head, tail = f"{first} → {second}", (f" · {cue}" if cue else "")
    kicker_size = min(_KICKER, (W / len(kicker) - 0.4) / _CAP)   # 0.4: its letter spacing
    big = min(_BIG, W / (_EM * (len(head) + _CUE * len(tail))))
    cue_span = (f'<tspan fill="{MUTED}" font-weight="500" font-size="{_CUE * big:.2f}">{esc(tail)}</tspan>'
                if tail else "")
    header = (f'<g><title>«{esc(change["quote"])}»</title>'
              f'<text x="0" y="-9.2" {TEXT} font-size="{kicker_size:.2f}" font-weight="700" letter-spacing="0.4" '
              f'fill="{MUTED}">{esc(kicker)}</text>'
              f'<text x="0" y="-3" {TEXT} font-size="{big:.2f}" font-weight="700" fill="{RED}">{head}{cue_span}</text></g>')
    described = f"{'How the shape changes' if english else 'Come cambia il modulo'}: {esc(coach)}, {head}{esc(tail)}"
    legend = (f"○ where they start ({first}) · ● where they go ({second})." if english else
              f"○ dove partono ({first}) · ● dove arrivano ({second}).")
    said = f"«{esc(change['quote'])}»." + (f" «{esc(change['note'])}»." if change.get("note") else "")
    caption = (f"{legend} From the card {esc(card.get('id', ''))}: {said} Indicative positions; who goes where does "
               "not come from the card: the shortest movement, easier along the flanks." if english else
               f"{legend} Dalla scheda {esc(card.get('id', ''))}: {said} Posizioni indicative; chi va dove non viene "
               "dalla scheda: è lo spostamento più corto, più facile lungo le fasce.")
    return (f'<figure class="ma-figure ma-shape" style="margin:0.5rem 0 0">{motion_style(css, key)}'
            f'<svg viewBox="-2 -14 124 96" role="img" aria-label="{described}" style="width:100%;height:auto;display:block">'
            f'{header}{pitch_svg()}{"".join(trails)}{"".join(starts)}{"".join(players)}</svg>'
            f"{figcaption(caption)}</figure>")
