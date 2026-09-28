"""Guardrails: code that prevents, not a prompt that asks.

- input_guard: decides, before any model call, whether a question reaches the agent;
- output_guard: checks the answer against the consulted cards and asks for one rewrite;
- grounding, language: the deterministic checks both guards (and the evaluation) rely on.
"""
