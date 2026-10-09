"""Verifier: a second model checks the answer statement by statement against the consulted cards,
before the coach sees it.

The deterministic checks (output_guard.py) see names, numbers and citations, not who did what:
"Inter defended a lead in the 2023 final" passes them, since Inter and the final are in the card,
while the card says City won 1-0 and Inter was chasing the game. The same kind of error was
found in Q37 (Atalanta's man-to-man press given to Leverkusen) and Q18 (Pioli's thesis given to
"his Milan"): the right card was read, the sentence swapped the roles.
The verifier runs the claim-by-claim check of the gold run's judge (src/evaluation/judge.py: the
answer split into statements, then each one checked against the cards, with the supporting
sentence as evidence). Each unsupported statement becomes an Issue, fixed by the single rewrite
of the output guardrail together with the other problems: corrected with what the cards say, not
just deleted.
Model: gpt-4.1-mini, the judge chosen on 2026-09-29 (it caught Q18 and Q12, gpt-4o-mini did
not). Two calls per checked answer. A failed verification never blocks the answer: it is reported.
Measuring it: the gold run's judge uses the same method and model, so a gold run alone would
overrate the verifier; check it also with another judge (gpt-4.1) and on the known errors.
"""

from __future__ import annotations

from typing import Any

from src.evaluation.judge import judge_faithfulness_claims
from src.guardrails.output_guard import Issue

VERIFIER_MODEL = "gpt-4.1-mini"


def verify_answer(llm: Any, answer: str, question: str, context: str,
                  earlier_questions: str = "") -> tuple[list[Issue], str | None]:
    """(one Issue per statement of `answer` that `context` does not support, error or None).

    `context` is the text of the consulted cards; the coach's questions (`earlier_questions` of the
    same conversation, then `question`) are given to the check, since what the coach says about
    their own team is not an invention.
    """
    coach = "\n".join(q for q in (earlier_questions, question) if q)
    verdict = judge_faithfulness_claims(llm, context, answer, coach)
    if verdict.get("error"):
        return [], verdict["reason"]
    return [Issue(
        "unsupported", claim["statement"],
        f"This statement is not supported by the cards: \"{claim['statement']}\" (check: {claim['evidence']}). "
        "Correct it with what the cards say about the same fact (who did what, which team, which match, "
        "the score), or remove it if the cards say nothing about it; keep every other sentence and fact.",
    ) for claim in verdict["claims"] if not claim["supported"]], None
