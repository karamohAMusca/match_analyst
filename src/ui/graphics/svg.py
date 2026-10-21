"""What the graphics share: the pitch, the colours and the text, the escaping, the names and the style
of an animation, the caption.

The colours are the design system's CSS variables (the CSS block of view.py, light and dark), each
with its light value as the fallback.
"""

from __future__ import annotations

import hashlib
import html
import re

W, H = 120, 80   # pitch units (StatsBomb's), the coach's team attacking left to right
RED, INK = "var(--ma-red,#B3122B)", "var(--ma-ink,#111)"
CARD, MUTED = "var(--ma-card,#FBE9EA)", "var(--ma-muted,#4A3A3C)"
TEXT = 'font-family="IBM Plex Sans Condensed, sans-serif"'
# The two teams of a final's title: "Finale Mondiale 2026: Spagna 1-0 Argentina (d.t.s.)"
TITLE_TEAMS_RE = re.compile(r":\s*(?P<home>.+?)\s+\d+-\d+\s+(?P<away>[^(]+?)\s*(?:\(|$)")


def esc(text: object) -> str:
    """Text of a card or of the data for SVG text and double-quoted attributes: "&", "<", ">" and '"'
    escaped; the apostrophe is safe in both and stays ("47' 1-0 Williams")."""
    return html.escape(str(text), quote=False).replace('"', "&quot;")


def figure_key(*parts: object) -> str:
    """The prefix of a figure's class and keyframe names: unique per content and per animate, so that
    a still figure never takes the animation of an animated one with the same content (the CSS of a
    page is shared by every figure on it)."""
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:6]


def motion_style(css: list[str], key: str) -> str:
    """The <style> of a figure's animation (its `ma-<key>-` classes), stopped when the system asks for
    reduced motion; nothing for a still figure."""
    return (f"<style>{' '.join(css)} @media (prefers-reduced-motion: reduce) {{ [class^=\"ma-{key}-\"] "
            f"{{ animation: none !important; }} }}</style>" if css else "")


def figcaption(text: str) -> str:
    """The caption under a figure: where its data comes from and what it is not."""
    return (f'<figcaption style="font-family:\'IBM Plex Sans Condensed\',sans-serif;font-size:12px;'
            f'color:{MUTED}">{text}</figcaption>')


def pitch_svg() -> str:
    """The lines of the pitch, in ink on the card colour."""
    line = f'fill="none" stroke="{INK}" stroke-width="0.35"'
    return (f'<rect x="0" y="0" width="{W}" height="{H}" fill="{CARD}" stroke="{INK}" '
            f'stroke-width="0.5"/>'
            f'<line x1="60" y1="0" x2="60" y2="{H}" {line}/><circle cx="60" cy="40" r="10" {line}/>'
            f'<rect x="0" y="18" width="18" height="44" {line}/><rect x="102" y="18" width="18" height="44" {line}/>'
            f'<rect x="0" y="30" width="6" height="20" {line}/><rect x="114" y="30" width="6" height="20" {line}/>'
            f'<rect x="-1.2" y="36" width="1.2" height="8" fill="{INK}"/>'
            f'<rect x="120" y="36" width="1.2" height="8" fill="{INK}"/>')
