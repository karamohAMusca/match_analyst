"""Test doubles: a deterministic embedder, so tests need no API key and no network."""

from __future__ import annotations

import hashlib
import math
import re

from datapizza.core.embedder import BaseEmbedder

DIM = 64
MODEL = "fake-embedding"
COLLECTION = "test_cards"


class FakeEmbedder(BaseEmbedder):
    """Bag-of-words vectors: texts sharing words are close, which is enough to test search."""

    def __init__(self) -> None:
        self.model_name = MODEL
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, text, model_name=None):
        self.calls += 1
        return self._vector(text) if isinstance(text, str) else [self._vector(t) for t in text]
