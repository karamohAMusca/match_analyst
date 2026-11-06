"""Secrets and contact data hidden from what the project sends out and keeps: the question before the model,
the chats saved in `chats/`, the traces sent to Phoenix and the log.

A coach may paste a key by mistake ("non funziona, la mia chiave è sk-...") or write a player's phone number;
without this it would reach OpenAI, stay in clear in the chat's file and in the traces, which keep what they
capture. The question is masked before anything else reads it, so the model, the traces and the memory of the
chat never see it; the files and the log are masked again when written (defence in depth: an answer, a tool
result or a log line holds what the question held).

Hidden: API keys and tokens (OpenAI `sk-...`, GitHub, AWS, Google, a JWT, a "Bearer" token, `password=...` and
the like), email addresses, phone numbers (with an international prefix, or an Italian mobile), IBANs, Italian
tax codes. Not hidden: names, which nothing tells apart from a coach's or a footballer's (the app asks not to
write the players' personal data). Deterministic, no model: the cards, the gold set and the saved answers have
nothing it masks (tests/test_redact.py).
"""

from __future__ import annotations

import re
from typing import Any

# (what it is, pattern, replacement): in this order, the keys first (a key may hold an "@" or digits)
_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("key", re.compile(r"\b(?P<name>api[_-]?key|access[_-]?token|token|secret|password|passwd|pwd)"
                       r"(?P<sep>\s*[:=]\s*)(?!\[chiave)(?P<value>[\"']?[^\s\"',;]{6,}[\"']?)", re.IGNORECASE), r"\g<name>\g<sep>[chiave nascosta]"),
    ("key", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/\-]{16,}=*"), "Bearer [chiave nascosta]"),
    ("key", re.compile(r"\bsk-(?:[A-Za-z0-9]+-)*[A-Za-z0-9_\-]{16,}"), "[chiave nascosta]"),
    ("key", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "[chiave nascosta]"),
    ("key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[chiave nascosta]"),
    ("key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), "[chiave nascosta]"),
    ("key", re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"), "[chiave nascosta]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}\b"), "[email nascosta]"),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b"), "[IBAN nascosto]"),
    ("tax_code", re.compile(r"\b[A-Z]{6}\d{2}[A-EHLMPR-T]\d{2}[A-Z]\d{3}[A-Z]\b", re.IGNORECASE), "[codice fiscale nascosto]"),
    # a phone: an international prefix and at least 8 digits, or an Italian mobile (3xx); dates, seasons
    # (2023-2024), scores and the long revision numbers of the cards' sources have neither
    ("phone", re.compile(r"(?<![\w+])\+\d{1,3}(?:[ .]?\d){8,12}\b|(?<![\w.\-])3\d{2}[ .]?\d{3}[ .]?\d{3,4}\b"), "[telefono nascosto]"),
]


def redact(text: str) -> tuple[str, list[str]]:
    """`text` with its secrets and contact data hidden, and what was hidden (the kinds, once each, in order:
    "key", "email", "iban", "tax_code", "phone"); the text unchanged and [] when there is nothing."""
    found: list[str] = []
    for kind, pattern, replacement in _RULES:
        text, count = pattern.subn(replacement, text)
        if count and kind not in found:
            found.append(kind)
    return text, found


def redact_all(value: Any) -> Any:
    """Every string inside `value` (dicts, lists, tuples, as JSON holds them) redacted; the rest as it is."""
    if isinstance(value, str):
        return redact(value)[0]
    if isinstance(value, dict):
        return {key: redact_all(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_all(item) for item in value]
    return value
