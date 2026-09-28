"""Formatting for the Streamlit app: style, citation badges, cards, answer details, saved runs.

Pure functions (no Streamlit calls), so they are tested offline. The texts shown to the user are
in Italian; every piece of model output or card text is HTML-escaped before it is marked up.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from src.corpus.cards import load_cards
from src.guardrails.output_guard import BRACKETS_RE, ID_WITH_PAGE_RE, citation_ids

CATEGORIES = {
    "match_case": ("🏆", "Finali"),
    "game_situation": ("🧭", "Situazioni di gioco"),
    "coach_profile": ("🧑‍🏫", "Allenatori"),
    "thesis_note": ("📘", "Note dalle tesi"),
    "glossary": ("📖", "Glossario"),
}
EXAMPLES = [
    ("🧱 Contro un 4-4-2 basso", "Domenica affrontiamo una squadra che si chiude in un 4-4-2 basso. "
                                "Noi giochiamo 4-3-3. Come la prepariamo?"),
    ("➕ In superiorità numerica", "Siamo in superiorità numerica negli ultimi 20 minuti e l'avversario "
                                  "si è abbassato. Cosa facciamo?"),
    ("🪞 A chi somiglio?", "La mia squadra difende a uomo a tutto campo, costruisce sulle fasce e porta "
                          "anche i difensori centrali in area. A quale allenatore somiglia?"),
    ("🇬🇧 In English", "How did Spain beat Argentina in the 2026 World Cup final?"),
    ("🛡️ Fuori tema (guardrail)", "Mi scrivi la ricetta della carbonara?"),
]
WELCOME = [
    ("🗓️", "Prepara la partita", "Descrivi la tua squadra e l'avversario: ricevi un piano con le "
                                 "situazioni di gioco e un caso reale dalle finali recenti."),
    ("⏱️", "Decidi durante la gara", "Superiorità numerica, vantaggio da difendere, rimonta: opzioni "
                                    "concrete, ognuna con la sua fonte."),
    ("🔎", "Solo fonti citate", "Ogni affermazione cita la sua scheda. Se le schede non bastano, "
                               "l'assistente risponde «Non lo so»."),
]
GUARD_INPUT = {
    "football": "domanda di calcio, passata all'agente",
    "follow_up": "domanda di seguito, passata all'agente",
    "greeting": "saluto: risposta fissa, nessuna chiamata al modello",
    "thanks": "ringraziamento: risposta fissa, nessuna chiamata al modello",
    "off_topic": "fuori tema: fermata prima del modello",
    "injection": "tentativo di cambiare le istruzioni: fermato prima del modello",
    "too_long": "domanda troppo lunga: fermata prima del modello",
    "empty": "domanda vuota",
}
RETRIEVAL_NAMES = {"dense": "densa", "bm25": "BM25 (parole chiave)", "hybrid rrf (course)": "ibrida RRF",
                   "hybrid interleave": "ibrida interleave (scelta)"}

CSS = """
<style>
.block-container {padding-top: 3.6rem;}
.ma-hero {background: linear-gradient(120deg, #0b5d1e 0%, #1f8a3b 55%, #2fa84f 100%); color: #fff;
  border-radius: 16px; padding: 1.1rem 1.4rem; margin-bottom: .9rem; position: relative; overflow: hidden;}
.ma-hero:before {content: ""; position: absolute; right: 70px; top: 0; bottom: 0; border-left: 2px solid rgba(255,255,255,.22);}
.ma-hero:after {content: ""; position: absolute; right: 10px; top: 50%; width: 120px; height: 120px;
  transform: translateY(-50%); border: 2px solid rgba(255,255,255,.22); border-radius: 50%;}
.ma-hero h1 {color: #fff; font-size: 1.75rem; margin: 0; padding: 0;}
.ma-hero p {margin: .25rem 0 .6rem 0; opacity: .93;}
.ma-chip {display: inline-block; padding: .12rem .6rem; margin: .12rem .3rem .12rem 0; border-radius: 999px;
  font-size: .78rem; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.35);}
.ma-cite {display: inline-block; padding: .03rem .45rem; margin: 0 .12rem; border-radius: 6px; font-size: .78rem;
  background: rgba(46,160,67,.14); border: 1px solid rgba(46,160,67,.45); white-space: nowrap; cursor: help;}
.ma-card-head {border-left: 5px solid #2fa84f; padding: .35rem .8rem; margin-bottom: .5rem;
  background: rgba(46,160,67,.06); border-radius: 0 10px 10px 0;}
.ma-card-head .t {font-weight: 700; font-size: 1.05rem;}
.ma-tag {display: inline-block; padding: .06rem .5rem; margin: .25rem .3rem 0 0; border-radius: 999px;
  font-size: .74rem; background: rgba(46,160,67,.12); border: 1px solid rgba(46,160,67,.35);}
.ma-feature {border: 1px solid rgba(128,128,128,.28); border-radius: 14px; padding: .9rem 1rem; min-height: 150px;}
.ma-feature .i {font-size: 1.7rem;}
.ma-feature .t {font-weight: 700; margin: .2rem 0 .3rem 0;}
.ma-feature .d {font-size: .88rem; opacity: .85;}
</style>
"""


# ============================ CARDS =========================================
def load_card_index() -> dict[str, dict[str, Any]]:
    """Every card of the corpus as a plain dict (cacheable), by document_id."""
    index = {}
    for card in load_cards():
        md = card.metadata
        index[md["document_id"]] = {
            "id": md["document_id"], "title": md.get("title", md["document_id"]), "category": md.get("category", ""),
            "body": card.body, "sources": md.get("sources") or [], "date": str(md.get("date") or ""),
            "coaches": md.get("coaches") or {}, "formations": md.get("formations") or {}, "winner": md.get("winner"),
        }
    return index


def category_name(category: str) -> str:
    icon, name = CATEGORIES.get(category, ("📄", category))
    return f"{icon} {name}"


def short_title(card: dict[str, Any], limit: int = 40) -> str:
    """Finals by their name ("Finale Mondiale 2026"), the others by what follows the colon."""
    head, sep, tail = card["title"].partition(":")
    text = head if card["category"] == "match_case" or not sep else tail.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rsplit(" ", 1)[0] + "…"      # cut between words, not inside one


def card_label(card: dict[str, Any]) -> str:
    return f"{CATEGORIES.get(card['category'], ('📄',))[0]} {short_title(card, 60)}"


def card_body(card: dict[str, Any]) -> str:
    """The card's Markdown without its first heading (the title is shown in the header), with the
    section headings two levels smaller so they do not look like page titles in the side panel."""
    body = re.sub(r"\A\s*# [^\n]*\n+", "", card["body"])
    return re.sub(r"^(#{2,4}) ", lambda m: "#" * (len(m.group(1)) + 2) + " ", body, flags=re.M)


def card_header_html(card: dict[str, Any]) -> str:
    tags = [category_name(card["category"])]
    if card["date"]:
        tags.append(f"📅 {card['date']}")
    if card["winner"]:
        tags.append(f"🏅 {card['winner']}")
    tags += [f"📋 {team}: {formation}" for team, formation in card["formations"].items()]
    tags += [f"🧑‍🏫 {team}: {coach}" for team, coach in card["coaches"].items()]
    chips = "".join(f'<span class="ma-tag">{html.escape(str(t))}</span>' for t in tags)
    return f'<div class="ma-card-head"><div class="t">{html.escape(card["title"])}</div>{chips}</div>'


def header_html(cards: dict[str, dict[str, Any]]) -> str:
    counts = {c: sum(1 for card in cards.values() if card["category"] == c) for c in CATEGORIES}
    chips = "".join(f'<span class="ma-chip">{CATEGORIES[c][0]} {n} {CATEGORIES[c][1].lower()}</span>'
                    for c, n in counts.items() if n)
    return ('<div class="ma-hero"><h1>⚽ Match Analyst</h1>'
            "<p>L'assistente allenatore che prepara la partita e le situazioni di gara "
            "citando le fonti: tesi di Coverciano e finali 2022–2026.</p>"
            f"{chips}</div>")


# ============================ ANSWERS =======================================
def cite_badges(answer: str, cards: dict[str, dict[str, Any]]) -> str:
    """The answer with every [card_id] citation shown as a badge (title in the tooltip)."""
    text = html.escape(answer, quote=False)

    def badge(match: re.Match) -> str:
        inner = match.group(1).strip()
        ids = citation_ids(inner)
        if not ids:
            return match.group(0)
        page = inner.split(",", 1)[1].strip() if ID_WITH_PAGE_RE.fullmatch(inner) else ""
        badges = []
        for card_id in ids:
            card = cards.get(card_id)
            icon = CATEGORIES.get(card["category"], ("📄",))[0] if card else "📄"
            label = short_title(card) if card else card_id
            tooltip = card["title"] if card else card_id
            badges.append(f'<span class="ma-cite" title="{html.escape(tooltip)}">{icon} {html.escape(label)}'
                          f'{" · " + html.escape(page) if page else ""}</span>')
        return " ".join(badges)

    return BRACKETS_RE.sub(badge, text)


def ordered_cards(message: dict[str, Any], cards: dict[str, dict[str, Any]]) -> list[str]:
    """The cards of an answer: the cited ones first, in citation order, then the other consulted ones."""
    cited = [i for b in BRACKETS_RE.findall(message.get("content", "")) for i in citation_ids(b.strip())]
    ordered = list(dict.fromkeys(cited + list(message.get("consulted") or [])))
    return [i for i in ordered if i in cards]


def _n(value: int) -> str:
    """1234 -> "1.234" (Italian thousands separator)."""
    return f"{value:,}".replace(",", ".")


def details_markdown(message: dict[str, Any]) -> str:
    """Latency, tokens, cost, searches and what the guardrails did, as a Markdown list."""
    meta, guard = message.get("meta") or {}, message.get("guard") or {}
    searches = sum(1 for c in message.get("calls") or [] if c.get("tool") == "search_cards")
    tokens = meta.get("prompt_tokens", 0) + meta.get("completion_tokens", 0)
    if guard.get("input") is None:
        output = "guardrail spenti"
    elif guard.get("rewritten"):
        output = "risposta riscritta (" + ", ".join(i.split(":")[0] for i in guard.get("issues", [])) + ")"
    elif guard.get("issues"):
        output = "problemi trovati, riscrittura non tenuta"
    elif guard.get("input") in ("football", "follow_up"):
        output = "nessun problema"
    else:
        output = "—"
    lines = [
        f"- ⏱️ **Tempo:** {meta.get('latency_s', 0):.1f} s",
        f"- 🔤 **Token:** {_n(tokens)} (letti {_n(meta.get('prompt_tokens', 0))}, "
        f"scritti {_n(meta.get('completion_tokens', 0))})",
        f"- 💰 **Costo:** {meta.get('cost_usd', 0):.4f} $ ({meta.get('model', '—')})",
        f"- 🔎 **Ricerche:** {searches} · **schede consultate:** {len(message.get('consulted') or [])}",
        f"- 🛡️ **Guardrail di ingresso:** {GUARD_INPUT.get(guard.get('input'), 'spenti')}",
        f"- 🛡️ **Guardrail di uscita:** {output}",
    ]
    return "\n".join(lines)


def searches_markdown(calls: list[dict[str, Any]], cards: dict[str, dict[str, Any]]) -> str:
    """What the agent searched and read, one line per tool call."""
    lines = []
    for call in calls:
        if call.get("tool") == "search_cards":
            where = f" _(preferendo: {', '.join(call['categories'])})_" if call.get("categories") else ""
            found = ", ".join(card_label(cards[c]) for c in call.get("cards", []) if c in cards) or "nessun risultato"
            lines.append(f"- 🔎 «{call.get('query', '')}»{where}  \n  → {found}")
        elif call.get("tool") == "read_card":
            card = cards.get(call.get("document_id", ""))
            lines.append(f"- 📖 letta per intero: {card_label(card) if card else call.get('document_id')}")
    return "\n".join(lines) or "Nessuna ricerca."


# ============================ SAVED RUNS ====================================
def run_summaries(runs_dir: Path) -> dict[str, Any]:
    """The saved runs, for the evaluation tab: full agent runs, gold runs, latest retrieval comparison."""
    agent, gold, retrieval = [], [], None
    for path in sorted(runs_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        time_of_day = f"{path.stem[-6:-4]}:{path.stem[-4:-2]}"
        if path.name.startswith("agent_") and len(data.get("questions", [])) >= 40:
            questions = data["questions"]
            label = f"{data.get('model') or 'gpt-4o-mini'}{' + guardrail' if data.get('guardrails') else ''} ({time_of_day})"
            agent.append({"run": label, "passano": sum(not q["problems"] for q in questions),
                          "domande": len(questions)})
        elif path.name.startswith("gold_"):
            metrics = data["metrics"]
            gold.append({"file": path.name, "tag": data.get("tag"), "metrics": metrics,
                         "live": not data.get("rejudged_from") and not metrics.get("replayed"),
                         "judge": data.get("judge_model"), "method": data.get("faithfulness_method") or "holistic"})
        elif path.name.startswith("retrieval_"):
            retrieval = data
    retrieval_rows = []
    for name, summary in ((retrieval or {}).get("summaries") or {}).items():
        overall = summary.get("overall", summary)
        retrieval_rows.append({"metodo": RETRIEVAL_NAMES.get(name, name),
                               "recall@5": overall.get("recall@5"), "MRR": overall.get("MRR@10")})
    live = [g for g in gold if g["live"]]
    return {"agent": agent, "gold": gold, "gold_live": live[-1] if live else None, "retrieval": retrieval_rows}
