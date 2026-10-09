"""Gold run and LLM judge (offline): metrics, judge contract, cost counting, report format."""

from __future__ import annotations

from types import SimpleNamespace

from datapizza.core.clients import ClientResponse
from datapizza.type import StructuredBlock

from src.evaluation.cost import TokenMeter, estimate_cost
from src.evaluation.gold_run import detail, load_gold, replay, run, score, summary, table, unsupported
from src.evaluation.judge import (JUDGE_MAX_TOKENS, JUDGE_TEMPERATURE, judge_faithfulness,
                                  judge_faithfulness_claims, judge_relevancy)
from tests.fakes import FakeJudge

CARD = SimpleNamespace(text="Possesso 60,2% (FIFA); Wikipedia: 65%.",
                       metadata={"document_id": "case_2026_wc_final_spain_argentina"})
OTHER = SimpleNamespace(text="Altro.", metadata={"document_id": "case_2024_euro_final_spain_england"})


def test_gold_is_the_same_gold_set_without_guardrail_questions():
    gold = load_gold()
    assert len(gold) == 41 and not {"off_topic", "chitchat", "follow_up"} & set(summary(gold))
    by_id = {g["id"]: g for g in gold}
    assert by_id["Q17"]["source"] == "case_2026_wc_final_spain_argentina" and by_id["Q17"]["ref"]
    assert all(by_id[i]["source"] is None for i in ("Q19", "Q20", "Q21"))       # out of corpus: abstention
    assert [g["id"] for g in load_gold(ids=["Q17", "Q35"])] == ["Q17", "Q35"]


def test_judge_scores_are_clamped_and_errors_are_visible():
    assert judge_faithfulness(FakeJudge(faithfulness=1.7), "ctx", "ans")["score"] == 1.0
    assert judge_relevancy(FakeJudge(relevancy=-0.3), "q", "ans")["score"] == 0.0
    failed = judge_faithfulness(FakeJudge(fail=True), "ctx", "ans")
    assert failed["score"] == 0.0 and failed["reason"].startswith("judge error: TimeoutError")


class NoVerdictJudge(FakeJudge):
    """Extracts the statements of the answer, then returns no verdict for them."""

    def _structured_response(self, input, output_cls, *args, **kwargs):
        if output_cls.__name__ == "StatementVerdicts":
            return ClientResponse(content=[StructuredBlock(content=output_cls(verdicts=[]))])
        return super()._structured_response(input, output_cls, *args, **kwargs)


def test_judge_that_returns_nothing_gives_an_error_not_a_pass():
    # Degenerate judge outputs: nothing to score is a judge error (left out of the averages and
    # counted), never a 1.0. An answer of citations only has no statement and is not an abstention.
    empty = judge_faithfulness_claims(FakeJudge(), "[coach_pioli]\nTesi.", "[coach_pioli]", "Chi?")
    assert empty["error"] and empty["reason"] == "judge error: no statement extracted"
    silent = judge_faithfulness_claims(NoVerdictJudge(), "[coach_pioli]\nTesi.", "La tesi parla del Chievo [coach_pioli].", "Chi?")
    assert silent["error"] and silent["reason"] == "judge error: no verdict returned"


def test_judge_temperature_is_really_sent():
    judge = FakeJudge()
    judge_relevancy(judge, "q", "a")
    assert judge.temperatures == [JUDGE_TEMPERATURE] and JUDGE_TEMPERATURE > 0   # 0 would be dropped
    assert judge.max_tokens == [JUDGE_MAX_TOKENS]                 # a runaway answer cannot hang the run


def _answer(text, context=None, prompt=1000, completion=100):
    return lambda q, k=5: SimpleNamespace(text=text, context=context,
                                          usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


def test_run_metrics_on_in_corpus_and_out_of_corpus_questions():
    gold = load_gold(ids=["Q17", "Q19"])
    answers = {"Q17": "La Spagna ha il 60,2% [case_2026_wc_final_spain_argentina].", "Q19": "Non lo so."}
    answer_fn = lambda q, k=5: _answer(answers["Q17" if "Spagna" in q else "Q19"])(q)   # noqa: E731
    metrics, rows = run(answer_fn, lambda q, k=10: [OTHER, CARD], gold, FakeJudge(0.5, 1.0), faithfulness="holistic")
    assert (metrics["recall@1"], metrics["recall@5"], metrics["MRR"]) == (0.0, 1.0, 0.5)   # found 2nd
    assert (metrics["faithfulness"], metrics["relevancy"]) == (0.5, 1.0) and score(metrics) == 0.75
    assert metrics["abstention_out_of_corpus"] == 1.0
    assert metrics["cost_per_query_usd"] == estimate_cost(1000, 100) and metrics["cost_run_usd"] == 2 * estimate_cost(1000, 100)
    assert rows[0]["rank"] == 2 and rows[0]["faithfulness_reason"] == "scripted" and rows[1]["abstained"]


def test_an_answer_that_used_two_models_gives_its_own_cost():
    # With the verifier, an answer costs the agent's tokens at its price plus the verifier's at its own.
    gold = load_gold(ids=["Q17"])
    resp = _answer("60,2% [case_2026_wc_final_spain_argentina].")
    answer_fn = lambda q, k=5: SimpleNamespace(**vars(resp(q)), cost_usd=0.0042)   # noqa: E731
    metrics, rows = run(answer_fn, lambda q, k=10: [CARD], gold, FakeJudge())
    assert rows[0]["cost_usd"] == 0.0042 and metrics["cost_per_query_usd"] == 0.0042


def test_faithfulness_is_judged_on_what_the_agent_read():
    gold = load_gold(ids=["Q17"])
    judge = FakeJudge()
    run(_answer("60,2%", context="[case_2026_wc_final_spain_argentina]\nscheda letta"), lambda q, k=10: [OTHER], gold, judge)
    split, verify = judge.inputs[0], judge.inputs[1]                 # statements first, then verification
    assert "CONTEXT" not in split and "scheda letta" in verify and "Altro." not in verify
    judge = FakeJudge()
    run(_answer("60,2%"), lambda q, k=10: [OTHER, CARD], gold, judge)                 # no context: top-k hits
    assert "[case_2024_euro_final_spain_england]\nAltro." in judge.inputs[1]


def test_judge_errors_are_left_out_of_the_averages(monkeypatch):
    # Run -095710: Q27's verdict was cut at the token limit and counted as 0.0 against the agent.
    import src.evaluation.gold_run as gold_run_module
    error = {"score": 0.0, "reason": "judge error: ValidationError: EOF", "error": True}
    monkeypatch.setattr(gold_run_module, "judge_relevancy",
                        lambda llm, q, a: error if "Spagna" in q else {"score": 1.0, "reason": "ok"})
    gold = load_gold(ids=["Q17", "Q18"])
    metrics, rows = run(_answer("La tesi parla della Primavera [coach_pioli]."), lambda q, k=10: [CARD], gold,
                        FakeJudge())
    assert metrics["relevancy"] == 1.0 and metrics["judge_errors"] == 1          # Q17 left out, not 0
    assert rows[0]["relevancy"] is None and rows[0]["relevancy_reason"].startswith("judge error")
    assert " err" in detail(rows).splitlines()[2]
    assert table(metrics).splitlines()[-1].replace(" ", "") == "judgeerrors(leftout):1"


def test_judge_errors_are_flagged():
    assert judge_relevancy(FakeJudge(fail=True), "q", "a")["error"] is True
    assert judge_faithfulness_claims(FakeJudge(fail=True), "ctx", MILAN)["error"] is True
    assert "error" not in judge_relevancy(FakeJudge(), "q", "a")


def test_relevancy_judge_does_not_judge_the_facts():
    # Run -095710: Q17 got relevancy 0.0 because "the 2026 World Cup has not happened yet".
    from src.evaluation.judge import RELEVANCY_PROMPT
    assert "Do not judge whether the facts are true" in RELEVANCY_PROMPT


def test_english_abstention_counts():
    metrics, _ = run(_answer("I don't know."), None, load_gold(ids=["Q20"]), FakeJudge())
    assert metrics["abstention_out_of_corpus"] == 1.0


def test_token_meter_counts_every_call_and_cost():
    judge = FakeJudge()
    meter = TokenMeter(judge)
    judge_faithfulness(judge, "c", "a")
    judge_relevancy(judge, "q", "a")
    assert meter.take() == (200, 40) and meter.take() == (0, 0)
    assert estimate_cost(1_000_000, 1_000_000, "gpt-4o-mini") == 0.75 and estimate_cost(10, 10, "unknown") == 0.0


def test_report_marks_rows_below_threshold():
    gold = load_gold(ids=["Q17", "Q19"])
    metrics, rows = run(_answer("Non lo so."), lambda q, k=10: [CARD], gold, FakeJudge(0.6, 0.9), faithfulness="holistic")
    lines = detail(rows).splitlines()
    assert lines[2].startswith("Q17") and "< " in lines[2]           # faithfulness 0.6 < 0.7
    assert "abst." in lines[3] and "< " not in lines[3]
    assert table(metrics).splitlines()[-1].split(":") == ["SCORE (faith+rel)/2      ", " 0.750"]


def test_replay_judges_saved_answers_on_the_cards_they_consulted():
    # eval_agent runs save question, answer and consulted cards: the same answers, another judge.
    saved = [{"question_id": "Q17", "question": load_gold(ids=["Q17"])[0]["q"],
              "answer": "60,2% [case_2026_wc_final_spain_argentina].", "consulted": ["case_2026_wc_final_spain_argentina"]}]
    answer_fn = replay(saved, lambda consulted: "\n".join(f"[{c}]\nscheda" for c in consulted))
    gold = [g for g in load_gold() if g["q"] in answer_fn.questions]
    judge = FakeJudge(0.4, 0.9)
    metrics, rows = run(answer_fn, lambda q, k=10: [CARD], gold, judge, faithfulness="holistic")
    assert [r["id"] for r in rows] == ["Q17"] and rows[0]["consulted"] == ["case_2026_wc_final_spain_argentina"]
    assert "[case_2026_wc_final_spain_argentina]\nscheda" in judge.inputs[0]
    metrics["replayed"] = True
    assert "n/a (re-judged)" in table(metrics) and metrics["faithfulness"] == 0.4


# Claim by claim: the known-wrong answers of run agent_20260928-180737 hide the error in one sentence.
MILAN = ("La tesi di Pioli descrive il 4-4-2 a zona della Primavera del Chievo [coach_pioli]. "
         "Il Milan campione d'Italia giocava con questo 4-4-2 [coach_pioli].")


def test_claims_judge_finds_the_one_unsupported_sentence():
    judge = FakeJudge(unsupported=("Milan",))
    result = judge_faithfulness_claims(judge, "[coach_pioli]\nTesi: Primavera del Chievo.", MILAN, "Q18")
    assert result["score"] == 0.5 and [c["supported"] for c in result["claims"]] == [True, False]
    assert "not supported: Il Milan campione d'Italia giocava con questo 4-4-2" in result["reason"]
    assert "[coach_pioli]" not in judge.inputs[1].split("STATEMENTS:")[1]   # citations are not statements
    assert judge.inputs[1].startswith("QUESTION:\nQ18\n\nCONTEXT:")        # the verifier sees the question


def test_claims_judge_abstention_and_errors():
    assert judge_faithfulness_claims(FakeJudge(), "ctx", "Non lo so.")["score"] == 1.0
    failed = judge_faithfulness_claims(FakeJudge(fail=True), "ctx", MILAN)
    assert failed["score"] == 0.0 and failed["reason"].startswith("judge error") and failed["claims"] == []


def test_gold_run_reports_unsupported_statements():
    gold = load_gold(ids=["Q18"])
    metrics, rows = run(_answer(MILAN), lambda q, k=10: [CARD], gold, FakeJudge(unsupported=("Milan",)))
    assert metrics["faithfulness"] == 0.5 and len(rows[0]["faithfulness_claims"]) == 2
    report = unsupported(rows)
    assert report.startswith("Statements not supported") and "Q18  Il Milan campione" in report
    assert unsupported([]) == "Every statement is supported by the consulted cards."
