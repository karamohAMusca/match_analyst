"""Analyst agent built on datapizza-ai v0.1.0."""

from __future__ import annotations

from typing import Any

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient

from src.agent.prompts import MATCH_ANALYST_SYSTEM_PROMPT
from src.core.config import load_settings, require_openai_key


class MatchAnalyst:
    """Assistant coach agent: answers match-preparation and in-game questions."""

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.1,
        tools: list[Any] | None = None,
        max_steps: int = 5,
    ) -> None:
        """Create the agent.

        Args:
            model_name: chat model; defaults to OPENAI_CHAT_MODEL (or gpt-4o-mini).
            temperature: sampling temperature (low for consistent, grounded answers).
            tools: datapizza tools available to the agent (e.g. corpus retrieval).
            max_steps: maximum reasoning/tool steps per question.

        Raises:
            ValueError: if OPENAI_API_KEY is not configured.
        """
        settings = load_settings()
        self.client = OpenAIClient(
            api_key=require_openai_key(),
            model=model_name or settings.chat_model,
            temperature=temperature,
        )
        self.tools = tools or []
        self.agent = Agent(
            name="MatchAnalystAgent",
            client=self.client,
            system_prompt=MATCH_ANALYST_SYSTEM_PROMPT,
            tools=self.tools,
            max_steps=max_steps,
            terminate_on_text=True,
        )

    def analyze(self, query: str) -> str:
        """Answer a coaching question and return the text of the final step."""
        response = self.agent.run(query)
        return response.text if hasattr(response, "text") else str(response)
