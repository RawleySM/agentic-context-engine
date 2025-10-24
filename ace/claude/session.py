"""Claude Agent SDK session orchestration for ACE adaptation loops."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, TYPE_CHECKING

from ..playbook import Playbook
from ..roles import (
    Curator,
    CuratorOutput,
    Generator,
    GeneratorOutput,
    Reflector,
    ReflectorOutput,
)
from .agents import AgentDefinition, create_default_agent_definitions
from .hooks import HookMatcher

if TYPE_CHECKING:  # pragma: no cover - runtime optional imports
    from ..adaptation import EnvironmentResult, Sample

try:  # pragma: no cover - only executed when the SDK is available.
    from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without SDK.
    ClaudeSDKClient = None  # type: ignore
    ClaudeAgentOptions = None  # type: ignore


LOGGER = logging.getLogger("ace.claude.session")


class ClaudeAgentRuntimeUnavailable(RuntimeError):
    """Raised when attempting to use the Claude Agent SDK without an environment."""


@dataclass
class ACEClaudeSession:
    """Bridge ACE orchestration with Claude Agent SDK primitives."""

    client: Optional[Any] = None
    agents: Optional[Dict[str, AgentDefinition]] = None
    hooks: Optional[Iterable[HookMatcher]] = None
    setting_sources: Sequence[str] = ("project", "user")
    session_options: Optional[Any] = None
    generator: Optional[Generator] = None
    reflector: Optional[Reflector] = None
    curator: Optional[Curator] = None

    def __post_init__(self) -> None:
        self.agents = self.agents or create_default_agent_definitions()
        self._hooks: List[HookMatcher] = list(self.hooks or [])
        self._client = self.client
        self._session = None
        self._fallback_generator = self.generator
        self._fallback_reflector = self.reflector
        self._fallback_curator = self.curator

    # ------------------------------------------------------------------ #
    # Public helpers
    # ------------------------------------------------------------------ #
    @property
    def sdk_available(self) -> bool:
        return ClaudeSDKClient is not None

    def ensure_session(self) -> Any:
        if not self.sdk_available:
            raise ClaudeAgentRuntimeUnavailable(
                "Claude Agent SDK is not installed. Install 'claude-agent-sdk' to "
                "enable first-party orchestration."
            )
        if self._session is None:
            client = self._client or ClaudeSDKClient()  # type: ignore[operator]
            options = self.session_options or ClaudeAgentOptions(  # type: ignore[call-arg]
                agents=self.agents,
                setting_sources=list(self.setting_sources),
                hooks=self._hooks,
            )
            try:
                self._session = client.start_session(options)
            except AttributeError:
                # SDK API changed; log and fall back.
                LOGGER.warning(
                    "Claude SDK client does not expose start_session; falling back to local roles."
                )
                self._session = None
            except Exception:
                LOGGER.exception("Failed to start Claude agent session; falling back to local roles.")
                self._session = None
            else:
                self._client = client
        return self._session

    def register_hooks(self, hooks: Iterable[HookMatcher]) -> None:
        for hook in hooks:
            if hook not in self._hooks:
                self._hooks.append(hook)

    def register_local_roles(
        self,
        *,
        generator: Optional[Generator] = None,
        reflector: Optional[Reflector] = None,
        curator: Optional[Curator] = None,
    ) -> None:
        if generator is not None:
            self._fallback_generator = generator
        if reflector is not None:
            self._fallback_reflector = reflector
        if curator is not None:
            self._fallback_curator = curator

    # ------------------------------------------------------------------ #
    # Hook emission helpers
    # ------------------------------------------------------------------ #
    def _emit_hook(self, event: str, payload: Dict[str, Any]) -> None:
        for hook in self._hooks:
            try:
                hook(event, payload)
            except Exception:  # pragma: no cover - hooks are best-effort logging.
                LOGGER.exception("Hook %s failed while handling %s", hook, event)

    # ------------------------------------------------------------------ #
    # Claude role runners (with local fallbacks)
    # ------------------------------------------------------------------ #
    def run_generator(
        self,
        *,
        question: str,
        context: Optional[str],
        playbook: Playbook,
        reflection: Optional[str] = None,
        sample: Optional["Sample"] = None,
        epoch: Optional[int] = None,
        step: Optional[int] = None,
        **llm_kwargs: Any,
    ) -> GeneratorOutput:
        payload: Dict[str, Any] = {
            "agent": "ace-generator",
            "question": question,
            "context": context,
            "reflection": reflection,
            "sample": sample,
            "epoch": epoch,
            "step": step,
        }
        self._emit_hook("pre_tool_use", payload)

        output = self._run_generator_locally(
            question=question,
            context=context,
            playbook=playbook,
            reflection=reflection,
            **llm_kwargs,
        )

        payload.update(
            {
                "result": output.raw,
                "generator_output": output,
                "playbook": playbook,
            }
        )
        self._emit_hook("post_tool_use", payload)
        return output

    def _run_generator_locally(
        self,
        *,
        question: str,
        context: Optional[str],
        playbook: Playbook,
        reflection: Optional[str],
        **llm_kwargs: Any,
    ) -> GeneratorOutput:
        if self._fallback_generator is None:
            raise ClaudeAgentRuntimeUnavailable(
                "Generator fallback not configured; cannot run without Claude SDK session."
            )
        return self._fallback_generator.generate(
            question=question,
            context=context,
            playbook=playbook,
            reflection=reflection,
            **llm_kwargs,
        )

    def run_reflector(
        self,
        *,
        question: str,
        generator_output: GeneratorOutput,
        playbook: Playbook,
        ground_truth: Optional[str],
        feedback: Optional[str],
        sample: Optional["Sample"] = None,
        epoch: Optional[int] = None,
        step: Optional[int] = None,
        **llm_kwargs: Any,
    ) -> ReflectorOutput:
        payload: Dict[str, Any] = {
            "agent": "ace-reflector",
            "question": question,
            "sample": sample,
            "epoch": epoch,
            "step": step,
            "feedback": feedback,
            "ground_truth": ground_truth,
        }
        self._emit_hook("pre_tool_use", payload)

        output = self._run_reflector_locally(
            question=question,
            generator_output=generator_output,
            playbook=playbook,
            ground_truth=ground_truth,
            feedback=feedback,
            **llm_kwargs,
        )
        payload.update({"result": output.raw, "reflection_output": output})
        self._emit_hook("post_tool_use", payload)
        return output

    def _run_reflector_locally(
        self,
        *,
        question: str,
        generator_output: GeneratorOutput,
        playbook: Playbook,
        ground_truth: Optional[str],
        feedback: Optional[str],
        **llm_kwargs: Any,
    ) -> ReflectorOutput:
        if self._fallback_reflector is None:
            raise ClaudeAgentRuntimeUnavailable(
                "Reflector fallback not configured; cannot run without Claude SDK session."
            )
        return self._fallback_reflector.reflect(
            question=question,
            generator_output=generator_output,
            playbook=playbook,
            ground_truth=ground_truth,
            feedback=feedback,
            **llm_kwargs,
        )

    def run_curator(
        self,
        *,
        reflection: ReflectorOutput,
        playbook: Playbook,
        question_context: str,
        progress: str,
        sample: Optional["Sample"] = None,
        epoch: Optional[int] = None,
        step: Optional[int] = None,
        **llm_kwargs: Any,
    ) -> CuratorOutput:
        payload: Dict[str, Any] = {
            "agent": "ace-curator",
            "sample": sample,
            "epoch": epoch,
            "step": step,
        }
        self._emit_hook("pre_tool_use", payload)

        output = self._run_curator_locally(
            reflection=reflection,
            playbook=playbook,
            question_context=question_context,
            progress=progress,
            **llm_kwargs,
        )
        payload.update(
            {
                "result": output.raw,
                "delta": output.delta,
                "curator_output": output,
            }
        )
        self._emit_hook("post_tool_use", payload)
        return output

    def _run_curator_locally(
        self,
        *,
        reflection: ReflectorOutput,
        playbook: Playbook,
        question_context: str,
        progress: str,
        **llm_kwargs: Any,
    ) -> CuratorOutput:
        if self._fallback_curator is None:
            raise ClaudeAgentRuntimeUnavailable(
                "Curator fallback not configured; cannot run without Claude SDK session."
            )
        return self._fallback_curator.curate(
            reflection=reflection,
            playbook=playbook,
            question_context=question_context,
            progress=progress,
            **llm_kwargs,
        )

    # ------------------------------------------------------------------ #
    # Environment feedback bridging
    # ------------------------------------------------------------------ #
    def emit_environment_feedback(
        self,
        *,
        sample: "Sample",
        generator_output: GeneratorOutput,
        environment_result: "EnvironmentResult",
        epoch: int,
        step: int,
        bullet_metadata: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> None:
        payload = {
            "agent": "ace-generator",
            "sample": sample,
            "generator_output": generator_output,
            "environment_feedback": environment_result.feedback,
            "environment_metrics": environment_result.metrics,
            "environment_ground_truth": environment_result.ground_truth,
            "epoch": epoch,
            "step": step,
            "bullet_metadata": bullet_metadata,
        }
        self._last_environment_payload = payload
        self._emit_hook("environment_feedback", payload)

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #
    def close(self) -> None:
        if self._session is None:
            return
        try:
            close = getattr(self._session, "close", None)
            if callable(close):
                close()
        finally:
            self._session = None


__all__ = ["ACEClaudeSession", "ClaudeAgentRuntimeUnavailable"]
