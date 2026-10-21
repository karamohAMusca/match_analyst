"""Facts written or checked by code instead of by the model.

The errors that survived every other check (eval/error_log.md) were names that are all in the
cards, put together wrongly, and additions the cards do not make. One module per family:
- `real_case.py`: the real case of an advice answer, written with the card's own sentence (E1, E2);
- `coaches.py`: coach-team pairs and thresholds the cards do not state (E3, E4, E5), `fact_issues`;
- `sides.py`: the coach's side of a game situation and the man down (E17), a score never given (E6);
- `additions.py`: a closing summary, an effect after a comma, an unknown without "Non lo so" (E19,
  E20), all three after the review (`tidy`);
- `text.py`: the sentences of an answer, shared by all of them.
This module keeps the names the agent, the evaluation and the tests import, and the kinds of issue
whose sentence is removed if it is still there after the rewrite (`FACT_KINDS`).
"""

from src.guardrails.additions import closing_summary, effect_tails, tidy, unmarked_unknown
from src.guardrails.coaches import TEAMS, coach_knowledge, fact_issues
from src.guardrails.real_case import CASE_LINE_RE, case_sentence, collapse_real_cases, expand_real_cases
from src.guardrails.sides import (MAN_DOWN_CARD, SIDES, coach_side, man_down_answer, perspective_issues,
                                  premise_issues, writes_man_down)
from src.guardrails.text import remove_sentences, sentences

FACT_KINDS = ("coach_team", "threshold", "premise")

__all__ = [
    "CASE_LINE_RE", "FACT_KINDS", "MAN_DOWN_CARD", "SIDES", "TEAMS", "case_sentence", "closing_summary",
    "coach_knowledge", "coach_side", "collapse_real_cases", "effect_tails", "expand_real_cases",
    "fact_issues", "man_down_answer", "perspective_issues", "premise_issues", "remove_sentences",
    "sentences", "tidy", "unmarked_unknown", "writes_man_down",
]
