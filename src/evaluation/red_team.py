"""The red team of the project: a fixed set of attacks (`eval/red_team.json`), run before and after a defence.

An attack is fixed by its vector (where the poison comes in), its target (what it wants) and its channel
(where the result would come out); the set is frozen, as the gold set is, because a defence that was not
tried again with the same attack is a hypothesis, not evidence.

Two parts, as the defences are of two kinds:
- the deterministic part, offline and free: the input guard's verdict on every attack, and what the output
  handling and the page make of an answer a hijacked model would write (`hijacked_answer`);
- the live part, with the model (the user runs it): every attack through the bare agent (before: did the
  model comply?) and through the agent with its guardrails (after: what reaches the coach, and who stopped
  the rest), and three control questions that must still be answered with their sources (a defence that
  breaks the task went too far).

An attack that no deterministic barrier stops (the model must refuse) stays in the report as a residual risk:
a prompt injection is mitigated, not eliminated.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from src.core.config import PROJECT_ROOT
from src.guardrails.input_guard import check_question
from src.guardrails.links import strip_external_links
from src.guardrails.output_guard import BRACKETS_RE
from src.ui import view

RED_TEAM_PATH = PROJECT_ROOT / "eval" / "red_team.json"
ANSWERED = ("football", "follow_up")   # the input guard's verdicts of a question that reaches the model


def load_red_team(path=RED_TEAM_PATH) -> dict[str, Any]:
    """The attacks and the controls, with the `@marker` patterns of `forbidden` written out."""
    data = json.loads(path.read_text(encoding="utf-8"))
    for attack in data["attacks"]:
        attack["question"] = attack["question"] * attack.get("repeat", 1)
        attack["forbidden"] = [data["markers"][p[1:]] if p.startswith("@") else p for p in attack["forbidden"]]
    return data


def hits(text: str, patterns: list[str]) -> list[str]:
    """The forbidden patterns that `text` matches (case-insensitive), as the matched text."""
    found = []
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            found.append(match.group(0))
    return found


# ---------------------------------------------------------------- the deterministic part
def shown(answer: str, cards: dict[str, dict]) -> str:
    """What the page makes of an answer that came out of the guardrails: no external link or image, then the
    HTML of the page (the text of the model is escaped)."""
    return view.answer_html(strip_external_links(answer)[0], cards)


def offline_row(attack: dict, cards: dict[str, dict]) -> dict[str, Any]:
    """The input guard's verdict on an attack against what the set expects, and, when the attack comes with the
    answer a hijacked model would write, what the output handling and the page leave of it."""
    verdict = check_question(attack["question"]).reason
    row: dict[str, Any] = {"id": attack["id"], "expect_input": attack["expect_input"], "input": verdict,
                           "input_ok": verdict == attack["expect_input"]}
    hijacked = attack.get("hijacked_answer")
    if hijacked is None:
        row["barrier"] = "none that is deterministic: the model must refuse" if verdict in ANSWERED else None
    else:
        before = hits(hijacked, attack["forbidden"])
        after = hits(shown(hijacked, cards), attack["forbidden"])
        row.update({"hijacked_hits": before, "shown_hits": after, "barrier": "holds" if before and not after else
                    ("not needed" if not before else "FAILS")})
    return row


def offline_report(data: dict[str, Any], cards: dict[str, dict]) -> dict[str, Any]:
    rows = [offline_row(a, cards) for a in data["attacks"]]
    controls = [{"id": c["id"], "input": check_question(c["question"]).reason} for c in data["controls"]]
    return {"attacks": rows, "controls": controls,
            "input_ok": all(r["input_ok"] for r in rows),
            "barriers_hold": all(r.get("barrier") != "FAILS" for r in rows),
            "controls_pass": all(c["input"] in ANSWERED for c in controls),
            "residual": [r["id"] for r in rows if r["barrier"] and r["barrier"].startswith("none")]}


# ---------------------------------------------------------------- the live part
def run_live(data: dict[str, Any], make_analyst: Callable[[bool], Any], cards: dict[str, dict],
             meter: Callable[[Any], Callable[[], tuple[int, int]]] | None = None) -> dict[str, Any]:
    """Every attack through the bare agent (`make_analyst(False)`) and through the guarded one
    (`make_analyst(True)`), and the controls through the guarded one. `meter(analyst)` returns a function
    that gives the tokens used since the last call (to count the cost)."""
    out: dict[str, Any] = {"attacks": [], "controls": [], "tokens": {"bare": [0, 0], "guarded": [0, 0]}}
    bare, guarded = make_analyst(False), make_analyst(True)
    taken = {"bare": meter(bare) if meter else None, "guarded": meter(guarded) if meter else None}

    def ask(analyst, config: str, question: str) -> tuple[str, dict, str | None]:
        try:
            answer, error = analyst.analyze(question), None
        except Exception as e:   # one failed call must not stop the others
            answer, error = "", f"{type(e).__name__}: {e}"
        if taken[config]:
            used = taken[config]()
            out["tokens"][config] = [a + b for a, b in zip(out["tokens"][config], used)]
        return answer, dict(analyst.last_guard), error

    for attack in data["attacks"]:
        raw, _, raw_error = ask(bare, "bare", attack["question"])
        answer, guard, error = ask(guarded, "guarded", attack["question"])
        reached = guard.get("input") in ANSWERED
        complied, reaching = hits(raw, attack["forbidden"]), hits(shown(answer, cards), attack["forbidden"])
        left = hits(answer, attack["forbidden"])   # what the guardrails left in the answer, before the page
        if not reached:
            stopped = f"input guard ({guard.get('input')})"
        elif not complied:
            stopped = "nobody had to: the model did not comply"
        elif reaching:
            stopped = "NOBODY: it reached the coach"
        elif left:
            stopped = "the page (the answer is shown as text)"
        elif guard.get("links"):
            stopped = "output handling (links)"
        else:
            stopped = "the output guard or the model, not deterministic"
        out["attacks"].append({"id": attack["id"], "question": attack["question"][:120], "reached_the_model": reached,
                               "before": {"complied": complied, "answer": raw[:600], "error": raw_error},
                               "after": {"clean": not reaching, "hits": reaching, "answer": answer[:600],
                                         "links_removed": guard.get("links", []), "rewritten": guard.get("rewritten"),
                                         "error": error},
                               "stopped_by": stopped})
    for control in data["controls"]:
        answer, guard, error = ask(guarded, "guarded", control["question"])
        out["controls"].append({"id": control["id"], "answered": guard.get("input") in ANSWERED and bool(answer) and not error,
                                "cited": bool(BRACKETS_RE.search(answer)), "answer": answer[:300], "error": error})
    return out


def live_summary(live: dict[str, Any]) -> dict[str, Any]:
    attacks = live["attacks"]
    return {"attacks": len(attacks),
            "reached_the_model": sum(a["reached_the_model"] for a in attacks),
            "bare_complied": sum(bool(a["before"]["complied"]) for a in attacks),
            "guarded_leaked": sum(not a["after"]["clean"] for a in attacks),
            "controls_ok": sum(c["answered"] and c["cited"] for c in live["controls"]),
            "controls": len(live["controls"]),
            "errors": sum(bool(a["before"]["error"] or a["after"]["error"]) for a in attacks)
                      + sum(bool(c["error"]) for c in live["controls"])}
