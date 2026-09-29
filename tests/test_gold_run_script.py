"""scripts/gold_run.py run end to end offline: which judge a command line really uses.

Regression test: re-judging a gpt-4.1-mini run without --judge-model once used a gpt-4.1-mini
judge, not the one expected. No key and no .env: settings, key, OpenAI client and tracing are
replaced by stand-ins; the in-memory index of conftest replaces Qdrant.
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import datapizza.clients.openai as openai_clients
import pytest

import scripts.gold_run as gold_run_script
import src.agent.analyst_agent as analyst_module
import src.core.config as config
import src.observability.tracing as tracing
from src.evaluation.gold_run import load_gold
from tests.fakes import FakeJudge


@pytest.fixture
def offline_script(tmp_path, monkeypatch, retriever):
    """Runs the script with `args`; returns (model asked to OpenAIClient, saved record). The fake
    judges, in creation order, are in `run_script.judges`; their cache is a file in tmp_path."""
    source = tmp_path / "agent_run.json"
    questions = {g["id"]: g["q"] for g in load_gold(ids=["Q17", "Q19"])}
    source.write_text(json.dumps({"model": "gpt-4o-mini", "guardrails": True, "questions": [
        {"question_id": "Q17", "question": questions["Q17"], "answer": "60,2% [case_2026_wc_final_spain_argentina].",
         "consulted": ["case_2026_wc_final_spain_argentina"]},
        {"question_id": "Q19", "question": questions["Q19"], "answer": "Non lo so.", "consulted": []},
    ]}), encoding="utf-8")
    asked: list[str] = []
    judges: list[FakeJudge] = []

    def fake_openai_client(**kwargs):
        asked.append(kwargs["model"])
        assert kwargs["timeout"] == 60 and kwargs["max_retries"] == 1   # a judge call cannot hang the run
        judges.append(FakeJudge())
        judges[-1].cache = kwargs["cache"]          # a datapizza client: it uses the cache it is given
        return judges[-1]

    # datapizza's ClientFactory is the real one: it picks the (fake) OpenAI client.
    monkeypatch.setattr(openai_clients, "OpenAIClient", fake_openai_client)
    monkeypatch.setattr(config, "require_api_key", lambda provider: "test-key")
    monkeypatch.setattr(config, "load_settings", lambda: SimpleNamespace(phoenix_endpoint="x", phoenix_project="y"))
    monkeypatch.setattr(tracing, "setup_tracing", lambda *a, **k: "tracing off (test)")
    monkeypatch.setattr(analyst_module, "build_retriever", lambda: retriever)
    monkeypatch.setattr(gold_run_script, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(gold_run_script, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(gold_run_script, "CACHE_DIR", tmp_path / "cache")   # never the real .cache/

    def run_script(*args: str, capsys=None):
        monkeypatch.setattr(sys, "argv", ["gold_run", "--rejudge", str(source), *args])
        assert gold_run_script.main() == 0
        saved = sorted((tmp_path / "runs").glob("gold_*.json"))[-1]
        record = json.loads(saved.read_text(encoding="utf-8"))
        saved.unlink()
        return asked[-1], record

    run_script.judges = judges
    return run_script


def test_explicit_judge_is_the_one_used(offline_script, capsys):
    for judge in ("gpt-4o-mini", "gpt-4.1-mini"):
        asked, record = offline_script("--tag", f"claims-{judge}", "--judge-model", judge)
        assert asked == judge and record["judge_model"] == judge and record["tag"] == f"claims-{judge}"
        assert f"judge {judge} (claims)" in capsys.readouterr().out


def test_default_judge_is_fixed_not_the_model_of_the_saved_run(offline_script):
    asked, record = offline_script("--tag", "default")
    assert asked == "gpt-4.1-mini" and record["judge_model"] == "gpt-4.1-mini"
    assert record["model"] == "gpt-4o-mini"           # the agent of the saved run is kept apart


def test_rejudge_record_is_complete(offline_script):
    _, record = offline_script("--tag", "check")
    assert record["rejudged_from"].endswith("agent_run.json") and record["faithfulness_method"] == "claims"
    assert [r["id"] for r in record["rows"]] == ["Q17", "Q19"] and record["metrics"]["replayed"] is True
    assert record["rows"][0]["faithfulness_claims"]                  # claim by claim by default


def test_a_rejudge_does_not_pay_again_for_the_verdicts_it_has(offline_script, capsys):
    _, first = offline_script("--tag", "first")
    paid = len(offline_script.judges[-1].inputs)
    assert paid and first["judge_cost_usd"] > 0 and first["judge_cache_hits"] == 0
    _, again = offline_script("--tag", "again")                  # e.g. after a run stopped halfway
    assert offline_script.judges[-1].inputs == []                # the judge was never asked
    assert again["judge_cache_hits"] == paid and again["judge_cost_usd"] == 0
    verdicts = lambda record: [(r.get("faithfulness_reason"), r.get("relevancy_reason")) for r in record["rows"]]
    assert verdicts(again) == verdicts(first)                    # the same verdicts, read back
    assert f"({paid} judge calls answered by the cache, not paid)" in capsys.readouterr().out
    _, fresh = offline_script("--tag", "fresh", "--no-judge-cache")
    assert len(offline_script.judges[-1].inputs) == paid and fresh["judge_cache_hits"] == 0


def test_a_provider_that_is_not_available_stops_with_a_message(offline_script, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["gold_run", "--rejudge", "x.json", "--judge-provider", "nope"])
    monkeypatch.setattr(gold_run_script.Path, "read_text", lambda *a, **k: '{"questions": []}')
    assert gold_run_script.main() == 1
    assert "nope" in capsys.readouterr().out and offline_script.judges == []
