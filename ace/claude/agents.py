"""Programmatic Claude sub-agent definitions used by ACE."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from ..prompts import CURATOR_PROMPT, GENERATOR_PROMPT, REFLECTOR_PROMPT

try:  # pragma: no cover - exercised when the SDK is installed.
    from claude_agent_sdk.agents import AgentDefinition  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without SDK.

    @dataclass
    class AgentDefinition:  # type: ignore[override]
        """Lightweight stand-in mirroring the Claude SDK dataclass."""

        description: str
        prompt: str
        tools: Optional[Iterable[str]] = None
        model: Optional[str] = None
        name: Optional[str] = None

        def as_dict(self) -> Dict[str, object]:
            payload: Dict[str, object] = {
                "description": self.description,
                "prompt": self.prompt,
            }
            if self.tools is not None:
                payload["tools"] = list(self.tools)
            if self.model is not None:
                payload["model"] = self.model
            if self.name is not None:
                payload["name"] = self.name
            return payload


def _normalize_tools(tools: Optional[Iterable[str]]) -> List[str]:
    if tools is None:
        return []
    return [str(tool) for tool in tools]


def create_default_agent_definitions(
    *,
    model: str = "claude-3-5-sonnet-20241022",
    generator_tools: Optional[Iterable[str]] = None,
    reflector_tools: Optional[Iterable[str]] = None,
    curator_tools: Optional[Iterable[str]] = None,
) -> Dict[str, AgentDefinition]:
    """Return Claude sub-agent definitions for ACE roles.

    The payload mirrors the documented ``AgentDefinition`` signature from the
    Claude Agent SDK Python examples. The prompts reuse ACE's battle-tested
    templates so behaviour remains consistent whether the run uses the Claude
    SDK transport or the legacy LiteLLM path.
    """

    agents: Dict[str, AgentDefinition] = {
        "ace-generator": AgentDefinition(
            description=(
                "Generate task completions using the ACE playbook and return"
                " structured JSON with reasoning and a final answer."
            ),
            prompt=GENERATOR_PROMPT,
            tools=_normalize_tools(generator_tools) or [
                "mcp://filesystem.read",
                "mcp://filesystem.write",
            ],
            model=model,
        ),
        "ace-reflector": AgentDefinition(
            description=(
                "Analyze generator trajectories, environment feedback, and"
                " update helpful/harmful signals for the ACE playbook."
            ),
            prompt=REFLECTOR_PROMPT,
            tools=_normalize_tools(reflector_tools) or [
                "mcp://filesystem.read",
            ],
            model=model,
        ),
        "ace-curator": AgentDefinition(
            description=(
                "Transform reflections into playbook delta operations,"
                " classifying bullets and exporting JSON patches."
            ),
            prompt=CURATOR_PROMPT,
            tools=_normalize_tools(curator_tools) or [
                "mcp://filesystem.read",
                "mcp://filesystem.write",
            ],
            model=model,
        ),
    }
    return agents


__all__ = ["AgentDefinition", "create_default_agent_definitions"]
