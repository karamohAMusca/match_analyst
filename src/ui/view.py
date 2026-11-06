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
from src.guardrails.links import strip_external_links
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
    ("🔄 Come cambia il modulo", "Come difende l'Inter di Inzaghi senza palla?"),
    ("📊 Numeri e tiri di una finale", "Quanti tiri e che xG ha avuto la Spagna nella finale dell'Europeo 2024?"),
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
    ("📊", "Guarda la partita", "Il campo con i moduli, la linea del tempo, i numeri e i tiri della finale, "
                               "e l'azione di ogni gol animata."),
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
/* Classes of the page (.ma-*), from the redesign made with Claude Design (design-system/):
   titles and the chat input in Inter, text in Newsreader, labels in IBM Plex Sans Condensed. */
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;700;800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;0,6..72,700;1,6..72,400&family=IBM+Plex+Sans+Condensed:wght@500;600;700&display=swap");

.block-container {padding-top: 5rem;}   /* the masthead top line clears the Streamlit toolbar */
[data-testid="stChatInput"] textarea { font-family:"Inter",sans-serif; }
:root {
  --ma-ink:#111111; --ma-red:#B3122B; --ma-on-red:#FFFFFF;
  --ma-paper:#F6D3D6; --ma-card:#FBE9EA; --ma-muted:#4A3A3C;
  --ma-head:"Inter",sans-serif;
  --ma-head-weight:800; --ma-head-case:uppercase;
  --ma-label:"IBM Plex Sans Condensed",sans-serif;
}
@media (prefers-color-scheme: dark) { :root {
  --ma-ink:#F6E3E4; --ma-red:#FF5A6E; --ma-on-red:#1B1315;
  --ma-paper:#1B1315; --ma-card:#241A1C; --ma-muted:#C9AFB2;
} }
.ma-hero { text-align:center; }
.ma-hero .top { display:flex; justify-content:space-between; flex-wrap:wrap; gap:8px;
  font:600 12px var(--ma-label); text-transform:uppercase; letter-spacing:.08em;
  border-bottom:1px solid var(--ma-ink); padding-bottom:6px; }
.ma-hero .top em { font-style:normal; color:var(--ma-red); }
.ma-hero h1 { font-family:var(--ma-head); font-weight:var(--ma-head-weight);
  text-transform:var(--ma-head-case); font-size:clamp(40px,11vw,88px); line-height:.98;
  color:var(--ma-ink); margin:12px 0 8px; padding-bottom:6px; border-bottom:4px solid var(--ma-ink); }
.ma-hero p { font-style:italic; font-size:18px; max-width:680px; margin:10px auto 12px; }
.ma-chips { display:flex; flex-wrap:wrap; justify-content:center; align-items:center;
  gap:6px 22px; padding:8px 12px;
  border-top:1px solid var(--ma-ink); border-bottom:1px solid var(--ma-ink); }
.ma-chips .label { font:700 12px var(--ma-label); text-transform:uppercase;
  letter-spacing:.1em; color:var(--ma-red); }
.ma-chip { font:500 15px var(--ma-label); white-space:nowrap; }
.ma-cite { display:inline-flex; align-items:center; gap:5px; margin:0 2px;
  font:600 12px var(--ma-label); text-transform:uppercase; letter-spacing:.03em;
  color:var(--ma-red); border-bottom:1px solid var(--ma-red); white-space:nowrap; cursor:help; }
.ma-cite .n { background:var(--ma-ink); color:var(--ma-paper);
  font-family:var(--ma-head); font-weight:var(--ma-head-weight); font-size:12px;
  min-width:16px; height:16px; line-height:16px; text-align:center; }
.ma-card-head { background:var(--ma-card); border-top:6px solid var(--ma-ink);
  border-bottom:1px solid var(--ma-ink); padding:12px 16px;
  display:grid; grid-template-columns:minmax(0,1fr) auto; gap:12px; align-items:start; }
.ma-card-head .t { font-family:var(--ma-head); font-weight:var(--ma-head-weight);
  text-transform:var(--ma-head-case); font-size:28px; line-height:1.05; margin-top:8px; }
.ma-card-head .n { width:44px; height:44px; border-radius:50%; background:var(--ma-ink);
  color:var(--ma-paper); font-family:var(--ma-head); font-weight:var(--ma-head-weight);
  font-size:24px; line-height:44px; text-align:center; }
.ma-tag { display:inline-block; padding:1px 8px; background:var(--ma-red); color:var(--ma-on-red);
  font:700 12px var(--ma-label); letter-spacing:.1em; text-transform:uppercase; }
.ma-welcome { display:grid; grid-template-columns:repeat(2, 1fr); gap:16px;
  align-items:stretch; margin-bottom:0.5rem; }   /* one grid: the tiles of a row share their height */
@media (max-width: 640px) { .ma-welcome { grid-template-columns:1fr; } }
.ma-feature { background:var(--ma-card); border-top:6px solid var(--ma-ink);
  border-bottom:1px solid var(--ma-ink); padding:14px 16px; min-height:150px; height:100%; box-sizing:border-box; }
.ma-feature .t { font-family:var(--ma-head); font-weight:var(--ma-head-weight);
  text-transform:var(--ma-head-case); font-size:clamp(16px, 1.6vw, 24px); line-height:1.05;
  overflow-wrap:normal; hyphens:manual; }   /* smaller in a narrow tile, never broken inside a word */
.ma-feature .d { font-size:15px; color:var(--ma-muted); }

/* Graphics under an answer: a pitch is 4:3, so on a wide column it grew taller than the screen */
.ma-figure { max-width:680px; }
.ma-figure.ma-numbers { max-width:560px; }
.ma-figure:not(.ma-timeline):not(.ma-numbers) { max-width:460px; }
/* The cards panel next to the chat stays in view while the chat scrolls, and says which answer it is of */
@media (min-width: 900px) {
  [data-testid="stColumn"]:has(.ma-panel) { position:sticky; top:4rem; align-self:flex-start;
    max-height:calc(100vh - 5rem); overflow-y:auto; }
}
.ma-panel-note { font-size:14px; color:var(--ma-muted); border-left:3px solid var(--ma-red);
  padding-left:8px; margin:-0.25rem 0 0.75rem; }

/* "Non lo so": the part of an answer with no source */
.ma-unknown { display:grid; grid-template-columns:auto 1fr; gap:10px;
  align-items:baseline; padding:8px 0;
  border-top:1px solid var(--ma-ink); border-bottom:1px solid var(--ma-ink); }
.ma-unknown .k { font:700 11px var(--ma-label); text-transform:uppercase;
  letter-spacing:.1em; border:1px solid var(--ma-ink); padding:0 6px; }
.ma-unknown p { margin:0; font-style:italic; }

/* What the guardrails did (instead of a caption); .blocked when the question never reached the model */
.ma-guard { display:flex; align-items:center; gap:8px; padding:5px 10px;
  font:700 12px var(--ma-label); text-transform:uppercase; letter-spacing:.08em;
  border:1px solid var(--ma-ink); }
.ma-guard .k { background:var(--ma-ink); color:var(--ma-paper); padding:0 6px; }
.ma-guard.blocked { background:var(--ma-ink); color:var(--ma-paper); }
.ma-guard.blocked .k { background:var(--ma-red); color:var(--ma-on-red); }

/* Waiting: st.spinner takes primaryColor from the theme, no CSS needed */
@media (max-width: 640px) {
  .ma-hero .top { justify-content:center; text-align:center; }
  .ma-hero h1 { font-size:clamp(40px,11vw,64px); }
  .ma-hero p { font-size:17px; }
  .ma-chips { gap:4px 16px; padding:8px 4px; }
  .ma-chip { font-size:14px; }
  .ma-card-head { padding:10px 12px; }
  .ma-card-head .t { font-size:23px; }
  .ma-card-head .n { width:36px; height:36px; line-height:36px; font-size:20px; }
  .ma-cite { white-space:normal; }
}
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
            "timeline": md.get("timeline") or [], "shape_changes": md.get("shape_changes") or [],
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


def card_header_html(card: dict[str, Any], number: int | None = None) -> str:
    """Tags and title of a card; `number` is the one of its citations in the answer (see citation_numbers)."""
    tags = [category_name(card["category"])]
    if card["date"]:
        tags.append(f"📅 {card['date']}")
    if card["winner"]:
        tags.append(f"🏅 {card['winner']}")
    tags += [f"📋 {team}: {formation}" for team, formation in card["formations"].items()]
    tags += [f"🧑‍🏫 {team}: {coach}" for team, coach in card["coaches"].items()]
    chips = " ".join(f'<span class="ma-tag">{html.escape(str(t))}</span>' for t in tags)
    badge = f'<span class="n">{number}</span>' if number else ""
    return f'<div class="ma-card-head"><div>{chips}<div class="t">{html.escape(card["title"])}</div></div>{badge}</div>'


def header_html(cards: dict[str, dict[str, Any]]) -> str:
    """The masthead of the page: the paper's top line, the title, the corpus in numbers."""
    counts = {c: sum(1 for card in cards.values() if card["category"] == c) for c in CATEGORIES}
    chips = "".join(f'<span class="ma-chip">{CATEGORIES[c][0]} {n} {CATEGORIES[c][1].lower()}</span>'
                    for c, n in counts.items() if n)
    return ('<header class="ma-hero"><div class="top"><span>Coverciano · Finali 2022–2026</span>'
            "<em>L'assistente allenatore</em></div><h1>⚽ Match Analyst</h1>"
            "<p>L'assistente allenatore che prepara la partita e le situazioni di gara "
            "citando le fonti: tesi di Coverciano e finali 2022–2026.</p>"
            f'<div class="ma-chips"><span class="label">Nell\'archivio</span>{chips}</div></header>')


# Who the coach is talking to and where the question goes, always on screen (AI Act, art. 50(1): a person who
# interacts with an AI system is told so, at the latest at the first interaction). See "Data and privacy" in the README.
AI_NOTICE = ("🤖 Le risposte sono scritte da un modello di intelligenza artificiale (OpenAI) a partire dalle schede "
             "citate: controllale prima di usarle. Le domande vanno a OpenAI e restano salvate su questo computer "
             "(`chats/`); non scrivere dati personali dei giocatori.")


def welcome_html() -> str:
    """The welcome tiles of the empty chat in one grid, two by two, so that they end at the same height
    (Streamlit columns grew each to its own text); on a narrow screen they wrap to one column."""
    return '<div class="ma-welcome">' + "".join(feature_html(*tile) for tile in WELCOME) + "</div>"


def feature_html(icon: str, title: str, text: str) -> str:
    """A welcome tile of the empty chat (the icon leads the title: the tiles have no icon row)."""
    return (f'<div class="ma-feature"><div class="t">{icon} {html.escape(title)}</div>'
            f'<div class="d">{html.escape(text)}</div></div>')


# ============================ ANSWERS =======================================
def citation_numbers(answer: str, cards: dict[str, dict[str, Any]]) -> dict[str, int]:
    """card_id -> the number of its citations in `answer` (1 = first card cited), for the known cards.
    The same number is on the badges of the answer and on the header of the card next to it."""
    cited = [i for b in BRACKETS_RE.findall(answer) for i in citation_ids(b.strip()) if i in cards]
    return {card_id: n for n, card_id in enumerate(dict.fromkeys(cited), start=1)}


def cite_badges(answer: str, cards: dict[str, dict[str, Any]]) -> str:
    """The answer with every [card_id] citation shown as a numbered badge (title in the tooltip)."""
    text = html.escape(answer, quote=False)
    numbers = citation_numbers(answer, cards)

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
            number = f'<span class="n">{numbers[card_id]}</span>' if card_id in numbers else ""
            badges.append(f'<span class="ma-cite" title="{html.escape(tooltip)}">{number}{icon} {html.escape(label)}'
                          f'{" · " + html.escape(page) if page else ""}</span>')
        return " ".join(badges)

    return BRACKETS_RE.sub(badge, text)


UNKNOWN_START = ("non lo so", "i don't know", "i do not know")


def answer_html(answer: str, cards: dict[str, dict[str, Any]]) -> str:
    """The answer for st.markdown: numbered citation badges, and every paragraph that says
    "Non lo so" (the part of the answer with no source) in its own box."""
    # what the model wrote is shown as text: no external image (the browser would fetch it) and no link, with
    # the guardrails off too (src/guardrails/links.py)
    paragraphs = cite_badges(strip_external_links(answer)[0], cards).split("\n\n")
    marked = [f'<div class="ma-unknown"><span class="k">Senza fonte</span><p>{p.strip()}</p></div>'
              if p.strip().lower().startswith(UNKNOWN_START) else p for p in paragraphs]
    return "\n\n".join(marked)


GUARD_STOPPED = {"off_topic", "injection", "too_long"}   # the question never reached the model


def guard_html(message: dict[str, Any]) -> str:
    """What the guardrails did for an answer, as a box ('' when they did nothing to report)."""
    note = message.get("guard_note")
    if not note:
        return ""
    text = note.removeprefix("Guardrail:").strip().rstrip(".")
    stopped = (message.get("guard") or {}).get("input") in GUARD_STOPPED
    return (f'<div class="ma-guard{" blocked" if stopped else ""}"><span class="k">Guardrail</span>'
            f"{html.escape(text)}</div>")


def panel_note_html(question: str, limit: int = 70) -> str:
    """The line under the title of the cards panel: the question whose answer the cards belong to, cut
    between words, so that with many answers in the chat it is clear which one the panel is of."""
    text = " ".join(question.split())
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0] + "…"
    return f'<div class="ma-panel-note">alla domanda «{html.escape(text)}»</div>'


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
        f"- 💰 **Costo:** {meta.get('cost_usd', 0):.4f} $ ({meta.get('model', '—')}"
        + (f" + verifica {meta['verifier_model']}, {_n(meta.get('verifier_tokens', 0))} token"
           if meta.get("verifier_model") else "") + ")",
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
                         "verifier": data.get("verifier"),
                         "judge": data.get("judge_model"), "method": data.get("faithfulness_method") or "holistic"})
        elif path.name.startswith("retrieval_"):
            retrieval = data
    retrieval_rows = []
    for name, summary in ((retrieval or {}).get("summaries") or {}).items():
        overall = summary.get("overall", summary)
        retrieval_rows.append({"metodo": RETRIEVAL_NAMES.get(name, name),
                               "recall@5": overall.get("recall@5"), "MRR": overall.get("MRR@10")})
    live = [g for g in gold if g["live"] and not g["verifier"]]   # the configuration the app runs
    final = {}   # the latest "final-*" judgement of each agent model: the numbers quoted in the README
    for path in sorted(runs_dir.glob("gold_*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if str(data.get("tag", "")).startswith("final-"):
            final[data["model"]] = {"agente": data["model"], "fedeltà": data["metrics"]["faithfulness"],
                                    "pertinenza": data["metrics"]["relevancy"], "score": data["score"],
                                    "giudice": data["judge_model"]}
    return {"agent": agent, "gold": gold, "gold_live": live[-1] if live else None, "retrieval": retrieval_rows,
            "final": list(final.values())}
