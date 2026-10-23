"""Which graphics go under a chat answer."""

from __future__ import annotations

from src.guardrails.language import detect_language
from src.guardrails.output_guard import cited_ids
from src.guardrails.real_case import CASE_LINE_RE, case_ids
from src.ui.graphics.formations import coach_formations, formations_in, formations_svg
from src.ui.graphics.goal import goal_actions, goal_svg, pick_goal
from src.ui.graphics.match_numbers import names_a_number, numbers_svg
from src.ui.graphics.shape import cited_shape_changes, shape_svg
from src.ui.graphics.shot_map import match_shots, names_a_shot, shots_svg
from src.ui.graphics.timeline import timeline_svg

ANSWERED = ("football", "follow_up")   # the input guard's verdicts of a question the agent answered


def real_cases(answer: str) -> list[str]:
    """The finals the real-case lines of an answer cite (the line written by code from the card)."""
    return list(dict.fromkeys(i for m in CASE_LINE_RE.finditer(answer) for i in case_ids(m.group("rest"))))


def answer_figures(messages: list[dict], index: int, cards: dict[str, dict], animate: bool = True) -> list[str]:
    """The graphics under the answer `messages[index]`, for a question the agent answered (not one
    stopped by the input guard): the pitch, when its own question names a formation of the coach or
    of the opponent (the other side may come from an earlier question of the chat); a coach's change
    of shape, when a line citing the coach's card writes the shape it becomes; the timeline of every
    final its real-case line cites and the action of a goal, for a final with StatsBomb data (the one
    at a minute the line writes, else the longest); the numbers of every final the answer cites, when
    the question or the answer names one of them, and, for a final with StatsBomb data, its shots when
    they speak of the shots (a question on the shots of a final has no real-case line)."""
    def answered(i: int) -> bool:
        return (i < len(messages) and messages[i].get("role") == "assistant"
                and (messages[i].get("guard") or {}).get("input") in ANSWERED)

    message = messages[index]
    if not answered(index):
        return []
    # the coach's questions the agent answered: one stopped by the input guard never gives a formation
    questions = [m["content"] for i, m in enumerate(messages[:index]) if m.get("role") == "user" and answered(i + 1)]
    english = bool(questions) and detect_language(questions[-1]) == "en"
    figures = []
    if questions and formations_in(questions[-1]):
        figures.append(formations_svg(coach_formations(questions), english=english, animate=animate))
    content = message.get("content", "")
    if changes := cited_shape_changes(content, cards):   # the first change of shape the answer speaks of
        card_id, change = changes[0]
        figures.append(shape_svg(cards[card_id], change, english=english, animate=animate))
    texts = (questions[-1] if questions else "", content)
    real = real_cases(content)
    for case_id in dict.fromkeys(real + [i for i in cited_ids(content) if i.startswith("case_")]):
        if case_id not in cards:
            continue
        if case_id in real:
            figures.append(timeline_svg(cards[case_id], english=english, animate=animate))
        if any(names_a_number(text, cards[case_id]) for text in texts):
            figures.append(numbers_svg(cards[case_id], english=english, animate=animate))
        if (shots := match_shots().get(case_id)) and any(names_a_shot(text) for text in texts):
            figures.append(shots_svg(shots, cards[case_id], english=english, animate=animate))
        line = next((m.group(0) for m in CASE_LINE_RE.finditer(content) if case_id in m.group(0)), "")
        if case_id in real and (goal := pick_goal(goal_actions().get(case_id, []), line)):
            figures.append(goal_svg(goal, cards[case_id], english=english, animate=animate))
    return [f for f in figures if f]
