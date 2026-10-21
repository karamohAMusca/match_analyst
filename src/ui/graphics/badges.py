"""The teams' symbols, drawn by code: nothing is downloaded.

No club crest and no competition logo: they are registered trademarks and protected artwork. The
national teams get their country's flag (a public symbol of the State, drawn here, simplified: no
coat of arms), the clubs a neutral shield with their initials in the club's colours (colours alone are
not a logo).
"""

from __future__ import annotations

import re

from src.ui.graphics.svg import INK, TEXT, esc

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


def _badge_box(team: str, height: float) -> tuple[float, float, float]:
    """(width, height, shift up) of a team's symbol drawn `height` tall: a flag is 3:2; a shield is
    narrower, so it is drawn a little taller, centred on the same line."""
    if team in _FLAGS:
        return height * 1.5, height, 0.0
    return height * 1.3 * 20 / 24, height * 1.3, height * 0.15


def team_badge(team: str, x: float, y: float, height: float) -> str:
    """The team's symbol at (x, y), `height` tall: its flag for a national team, else a neutral shield
    with its initials (any club, the first three letters when it is not listed)."""
    width, tall, up = _badge_box(team, height)
    box = f'x="{x:.1f}" y="{y - up:.1f}" width="{width:.1f}" height="{tall:.1f}"'
    if team in _FLAGS:
        return (f'<svg {box} viewBox="0 0 30 20"><title>{esc(team)}</title>{_FLAGS[team]}'
                f'<rect width="30" height="20" fill="none" stroke="{INK}" stroke-width="0.8"/></svg>')
    initials, fill, ink = _CLUBS.get(team, (re.sub(r"[^A-Z]", "", team.upper())[:3], "#4A3A3C", "#FFFFFF"))
    return (f'<svg {box} viewBox="0 0 20 24"><title>{esc(team)}</title>'
            f'<path d="{_SHIELD}" fill="{fill}" stroke="{INK}" stroke-width="0.9"/>'
            f'<text x="10" y="13.6" {TEXT} font-size="6.4" font-weight="700" text-anchor="middle" '
            f'fill="{ink}">{esc(initials)}</text></svg>')


def badge_width(team: str, height: float) -> float:
    return _badge_box(team, height)[0]
