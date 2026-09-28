"""LLM-as-judge: faithfulness and relevancy of an answer, each a score from 0.0 to 1.0.

The judge answers with typed objects through datapizza's `structured_response`, so there is no
text to parse. Scores are clamped to [0, 1]; a judge error scores 0.0 and the reason says why,
so a broken judge is visible in the results.

Faithfulness, two methods:
- "holistic" (`judge_faithfulness`): one score for the whole answer (`Verdict`: score + reason).
  If the context holds conflicting values and the answer presents one as certain without
  reporting the conflict, it is not faithful to the whole context.
  Measured on 2026-09-28 it gave 1.0 to all 38 answers, three known-wrong ones included (an
  invented PPDA threshold, a thesis attributed to a later team, a source conflict left out),
  with gpt-4o-mini and with gpt-4.1-mini: one global score rewards an answer whose facts are
  mostly right, while the error sits in a single sentence.
- "claims" (`judge_faithfulness_claims`, the method of RAGAS Faithfulness): first the answer is
  split into atomic statements, looking at the answer only; then each statement is checked
  against the context, with the supporting sentence as evidence. Score = supported / total, and
  the unsupported statements are reported, so the result says WHICH sentence is not grounded.
  The verification applies the same standard the agent is held to: nothing beyond the context,
  no rule or threshold the context does not state, no attribution to another team or season,
  conflicting sources reported. It also sees the question: the coach's description of their own
  team is given (first claims run -222641 penalised "your team plays 4-3-3" and "your team
  resembles Gasperini"), while a false premise of the question is not evidence (Q18's "his
  Milan"). A verdict must agree with the evidence it quotes (the same run contradicted itself).
  Limit: statements are checked one by one, so an omission (a conflict between sources left
  out, as in Q17) is not seen; the required-facts check of eval_agent covers it.
Relevancy: the answer actually answers the question (completeness and pertinence).
Temperature: datapizza's OpenAI client drops a temperature of 0 (it sends the value only when it
is truthy), so the judge would silently run at the API default; JUDGE_TEMPERATURE is the
smallest value that is really sent.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from src.guardrails.output_guard import is_abstention

JUDGE_TEMPERATURE = 0.01
# One judge for every run, whatever the agent's model: scores are comparable only with the same
# judge. (It once defaulted to the agent's model: re-judging a gpt-4.1-mini run silently used a
# gpt-4.1-mini judge instead of the one asked for.)
DEFAULT_JUDGE_MODEL = "gpt-4o-mini"
# Limits of one judge call. Without them one call hung for minutes on 2026-09-28 (a structured
# output that kept growing; the OpenAI client has no timeout by default): now it fails fast, the
# question gets "judge error" with the reason, and the run goes on.
JUDGE_TIMEOUT_S = 60
JUDGE_MAX_RETRIES = 1
JUDGE_MAX_TOKENS = 3000

FAITHFULNESS_PROMPT = (
    "You are a strict judge of FAITHFULNESS. Check whether EVERY claim of the ANSWER is supported "
    "by the CONTEXT. 1.0 = everything supported; 0.0 = it contains claims that are not in the "
    "context. Judge only from the context, not from outside knowledge. Card ids in square "
    "brackets are citations, not claims. If the answer says it does not know and the context does "
    "not contain that information, that part is faithful. If the CONTEXT contains conflicting "
    "information and the ANSWER presents only one version as certain without reporting the "
    "conflict, the answer is NOT faithful to the whole context: lower the score."
)
RELEVANCY_PROMPT = (
    "You are a judge of RELEVANCY. Rate how well the ANSWER actually answers the QUESTION "
    "(completeness and pertinence). 1.0 = fully relevant; 0.0 = off topic."
)
STATEMENTS_PROMPT = (
    "Split the ANSWER into its atomic statements. Each statement is one fact or one "
    "recommendation, understandable on its own: replace pronouns with the names they refer to, and "
    "keep every name, team, number, season and qualifier exactly as the answer writes it. Card ids "
    "in square brackets are citations, not statements: leave them out. Leave out sentences that "
    "only say that some information is not available (\"Non lo so\", \"I don't know\")."
)
VERIFY_PROMPT = (
    "You are a strict judge of FAITHFULNESS. For each STATEMENT decide whether it can be directly "
    "inferred from the CONTEXT alone, without outside knowledge. The statement may paraphrase the "
    "context or translate it into another language: judge the meaning, not the words. "
    "supported = true only if the context states it or it follows directly from what the context "
    "states; give the supporting sentence of the context as evidence. "
    "supported = false if it is not in the context; if it generalises beyond the context (a rule, a "
    "threshold or a ranking that the context does not state, even when built from a value the "
    "context reports); or if it attributes something to a person, team, season or event other than "
    "the one the context attributes it to. If the context reports conflicting information about "
    "the same fact and the statement gives one version as certain without mentioning the conflict, "
    "it is not supported. "
    "The QUESTION is what the coach asked. What the coach says there about their OWN team or "
    "situation is given: a statement that only repeats it is supported, and a comparison between "
    "that description and the context (which coach the team resembles, what to do in that "
    "situation) is supported when the traits or options it relies on are in the context. Anything "
    "else in the question (claims about other teams, coaches or sources) is not evidence: a false "
    "premise of the question stays unsupported. "
    "Be consistent: if the evidence you quote states the statement, supported must be true. "
    "Return one verdict per statement, in the same order."
)


class Verdict(BaseModel):
    score: float = Field(description="Score from 0.0 to 1.0")
    reason: str = Field(description="Short reason for the score")


class Statements(BaseModel):
    statements: list[str] = Field(description="The atomic statements of the answer, one fact each")


class StatementVerdict(BaseModel):
    statement: str = Field(description="The statement, as given")
    supported: bool = Field(description="True only if the statement can be directly inferred from the context")
    evidence: str = Field(description="The supporting sentence of the context, or why it cannot be inferred")


class StatementVerdicts(BaseModel):
    verdicts: list[StatementVerdict] = Field(description="One verdict per statement, in order")


def _structured(llm: Any, output_cls: type[BaseModel], system: str, user: str) -> Any:
    out = llm.structured_response(input=user, output_cls=output_cls, system_prompt=system,
                                  temperature=JUDGE_TEMPERATURE, max_tokens=JUDGE_MAX_TOKENS)
    return out.structured_data[0]


def _verdict(llm: Any, system: str, user: str) -> dict[str, Any]:
    try:
        verdict = _structured(llm, Verdict, system, user)
        return {"score": max(0.0, min(1.0, float(verdict.score))), "reason": verdict.reason}
    except Exception as e:  # a failed judgement must not stop the run, and must not look like a pass
        return {"score": 0.0, "reason": f"judge error: {type(e).__name__}: {e}"}


def judge_faithfulness(llm: Any, context: str, answer: str) -> dict[str, Any]:
    """Holistic: {"score", "reason"}, 1.0 = every claim of `answer` is supported by `context`."""
    return _verdict(llm, FAITHFULNESS_PROMPT, f"CONTEXT:\n{context}\n\nANSWER:\n{answer}")


def judge_faithfulness_claims(llm: Any, context: str, answer: str, question: str = "") -> dict[str, Any]:
    """Claim by claim: {"score", "reason", "claims"}; score = supported statements / statements.

    `claims` lists every statement with `supported` and `evidence`. An answer that only says
    "Non lo so" has no statement to check and scores 1.0.
    """
    try:
        statements = _structured(llm, Statements, STATEMENTS_PROMPT,
                                 f"QUESTION:\n{question}\n\nANSWER:\n{answer}").statements
        statements = [s.strip() for s in statements if s.strip()]
        if not statements:
            if is_abstention(answer):
                return {"score": 1.0, "reason": "abstention: no statement to check", "claims": []}
            return {"score": 0.0, "reason": "judge error: no statement extracted", "claims": []}
        numbered = "\n".join(f"{i}. {s}" for i, s in enumerate(statements, 1))
        verdicts = _structured(llm, StatementVerdicts, VERIFY_PROMPT,
                               f"QUESTION:\n{question}\n\nCONTEXT:\n{context}\n\nSTATEMENTS:\n{numbered}").verdicts
    except Exception as e:  # a failed judgement must not stop the run, and must not look like a pass
        return {"score": 0.0, "reason": f"judge error: {type(e).__name__}: {e}", "claims": []}
    if not verdicts:
        return {"score": 0.0, "reason": "judge error: no verdict returned", "claims": []}
    claims = [{"statement": v.statement, "supported": bool(v.supported), "evidence": v.evidence} for v in verdicts]
    supported = sum(c["supported"] for c in claims)
    unsupported = [c["statement"] for c in claims if not c["supported"]]
    reason = f"{supported}/{len(claims)} statements supported" + (
        "; not supported: " + " | ".join(unsupported) if unsupported else "")
    return {"score": supported / len(claims), "reason": reason, "claims": claims}


def judge_relevancy(llm: Any, question: str, answer: str) -> dict[str, Any]:
    """{"score", "reason"}: 1.0 = `answer` fully answers `question`."""
    return _verdict(llm, RELEVANCY_PROMPT, f"QUESTION:\n{question}\n\nANSWER:\n{answer}")
