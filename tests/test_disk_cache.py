"""The disk cache behind datapizza's client `cache` (offline): a verdict is paid once, even across restarts."""

from __future__ import annotations

import json

from src.core.disk_cache import DiskCache
from src.evaluation.cost import TokenMeter
from src.evaluation.judge import JUDGE_OUTPUTS, judge_faithfulness_claims, judge_relevancy
from tests.fakes import FakeJudge

QUESTION = "Come pressano le catene laterali nella tesi di Pioli?"
CONTEXT = "[coach_pioli]\nTesi sul 4-4-2 a zona della Primavera del Chievo."
ANSWER = "La tesi parla della Primavera del Chievo [coach_pioli]. Il 4-4-2 è a zona [coach_pioli]."


def judge_with_cache(path, **options) -> FakeJudge:
    judge = FakeJudge(**options)
    judge.cache = DiskCache(path, JUDGE_OUTPUTS)
    return judge


def test_values_survive_a_restart(tmp_path):
    path = tmp_path / "cache.json"
    DiskCache(path).set("k", [0.1, 0.2])
    again = DiskCache(path)                                        # a new process: only the file is left
    assert again.get("k") == [0.1, 0.2] and again.get("other") is None and again.hits == 1
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": [0.1, 0.2]}   # plain JSON, readable


def test_a_judge_verdict_is_paid_once(tmp_path):
    path = tmp_path / "judge.json"
    judge = judge_with_cache(path)
    first = judge_faithfulness_claims(judge, CONTEXT, ANSWER, QUESTION)
    assert len(judge.inputs) == 2 and first["score"] == 1.0         # statements, then their verdicts
    # After a restart: this judge would reject the Chievo statement, but it is never asked.
    restarted = judge_with_cache(path, unsupported=("Chievo",))
    meter = TokenMeter(restarted)
    assert judge_faithfulness_claims(restarted, CONTEXT, ANSWER, QUESTION) == first
    assert restarted.inputs == [] and restarted.cache.hits == 2 and meter.take() == (0, 0)   # not paid
    judge_relevancy(restarted, QUESTION, "Un'altra risposta [coach_pioli].")   # a new answer: a new call
    assert len(restarted.inputs) == 1 and meter.take() == (100, 20)


def test_a_verdict_that_cannot_be_rebuilt_is_asked_again(tmp_path):
    path = tmp_path / "judge.json"
    judge_relevancy(judge_with_cache(path), QUESTION, ANSWER)
    blind = FakeJudge()
    blind.cache = DiskCache(path)                                  # it does not know the judge's classes
    assert judge_relevancy(blind, QUESTION, ANSWER)["score"] == 0.8 and len(blind.inputs) == 1
