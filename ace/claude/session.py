"""Claude Agent SDK session orchestration for ACE adaptation loops."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, TYPE_CHECKING

from ..delta import DeltaBatch
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
    from claude_agent_sdk import (
        AssistantMessage,
        ClaudeAgentOptions,
        ClaudeSDKClient,
        ResultMessage,
        ToolResultBlock,
        query,
    )  # type: ignore
except Exception:  # pragma: no cover - fallback for environments without SDK.
    ClaudeSDKClient = None  # type: ignore
    ClaudeAgentOptions = None  # type: ignore
    AssistantMessage = None  # type: ignore
    ToolResultBlock = None  # type: ignore
    ResultMessage = None  # type: ignore
    query = None  # type: ignore


LOGGER = logging.getLogger("ace.claude.session")


class ClaudeAgentRuntimeUnavailable(RuntimeError):
    """Raised when attempting to use the Claude Agent SDK without an environment."""


@dataclass
class ACEClaudeSession:
    """Bridge ACE orchestration with Claude Agent SDK primitives."""

    client: Optional[Any] = None
    agents: Optional[Dict[str, AgentDefinition]] = None
    hooks: Optional[Iterable[HookMatcher]] = None
    agent_invoker: Optional[Callable[[str, Dict[str, Any]], Optional[Dict[str, Any]]]] = None
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
        self._agent_invoker = self.agent_invoker

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
            options = self.session_options
            if ClaudeAgentOptions is not None:
                default_options = ClaudeAgentOptions(  # type: ignore[call-arg]
                    agents=self.agents,
                    setting_sources=list(self.setting_sources),
                )
            else:
                default_options = None
            if options is None:
                options = default_options
            elif (
                ClaudeAgentOptions is not None
                and isinstance(options, ClaudeAgentOptions)
                and options.agents is None
            ):
                options = replace(options, agents=self.agents)
            elif (
                ClaudeAgentOptions is not None
                and isinstance(options, ClaudeAgentOptions)
                and options.setting_sources is None
            ):
                options = replace(options, setting_sources=list(self.setting_sources))
            self.session_options = options
            # The Python SDK currently exposes a streaming client without an explicit
            # session factory. Store the client instance so invocations can reuse the
            # configured transport while higher-level helpers fall back to stateless
            # invocations when necessary.
            if hasattr(client, "start_session"):
                try:
                    self._session = client.start_session(options)
                except AttributeError:
                    LOGGER.debug(
                        "Claude SDK client does not support start_session; using client directly."
                    )
                    self._session = client
                except Exception:
                    LOGGER.exception(
                        "Failed to start Claude agent session; falling back to local roles."
                    )
                    self._session = None
                else:
                    self._client = client
            else:
                self._client = client
                self._session = client
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

        output = None
        if self.sdk_available:
            try:
                output = self._run_generator_via_sdk(
                    question=question,
                    context=context,
                    playbook=playbook,
                    reflection=reflection,
                    **llm_kwargs,
                )
            except ClaudeAgentRuntimeUnavailable:
                raise
            except Exception:
                LOGGER.exception("Claude generator invocation failed; using local fallback.")

        if output is None:
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

    def _run_generator_via_sdk(
        self,
        *,
        question: str,
        context: Optional[str],
        playbook: Playbook,
        reflection: Optional[str],
        **llm_kwargs: Any,
    ) -> Optional[GeneratorOutput]:
        payload = {
            "question": question,
            "context": context,
            "playbook": playbook.as_prompt(),
            "reflection": reflection,
            "llm_kwargs": llm_kwargs or None,
        }
        result = self._invoke_claude_agent("ace-generator", payload)
        if result is None:
            return None
        return self._coerce_generator_output(result)

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

        output = None
        if self.sdk_available:
            try:
                output = self._run_reflector_via_sdk(
                    question=question,
                    generator_output=generator_output,
                    playbook=playbook,
                    ground_truth=ground_truth,
                    feedback=feedback,
                    **llm_kwargs,
                )
            except ClaudeAgentRuntimeUnavailable:
                raise
            except Exception:
                LOGGER.exception("Claude reflector invocation failed; using local fallback.")

        if output is None:
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

    def _run_reflector_via_sdk(
        self,
        *,
        question: str,
        generator_output: GeneratorOutput,
        playbook: Playbook,
        ground_truth: Optional[str],
        feedback: Optional[str],
        **llm_kwargs: Any,
    ) -> Optional[ReflectorOutput]:
        payload = {
            "question": question,
            "generator_reasoning": generator_output.reasoning,
            "generator_prediction": generator_output.final_answer,
            "generator_bullet_ids": list(generator_output.bullet_ids),
            "generator_raw": generator_output.raw,
            "playbook": playbook.as_prompt(),
            "ground_truth": ground_truth,
            "feedback": feedback,
            "llm_kwargs": llm_kwargs or None,
        }
        result = self._invoke_claude_agent("ace-reflector", payload)
        if result is None:
            return None
        return self._coerce_reflector_output(result)

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

        output = None
        if self.sdk_available:
            try:
                output = self._run_curator_via_sdk(
                    reflection=reflection,
                    playbook=playbook,
                    question_context=question_context,
                    progress=progress,
                    **llm_kwargs,
                )
            except ClaudeAgentRuntimeUnavailable:
                raise
            except Exception:
                LOGGER.exception("Claude curator invocation failed; using local fallback.")

        if output is None:
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

    def _run_curator_via_sdk(
        self,
        *,
        reflection: ReflectorOutput,
        playbook: Playbook,
        question_context: str,
        progress: str,
        **llm_kwargs: Any,
    ) -> Optional[CuratorOutput]:
        payload = {
            "reflection": reflection.raw,
            "playbook": playbook.as_prompt(),
            "question_context": question_context,
            "progress": progress,
            "llm_kwargs": llm_kwargs or None,
        }
        result = self._invoke_claude_agent("ace-curator", payload)
        if result is None:
            return None
        return self._coerce_curator_output(result)

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

    # ------------------------------------------------------------------ #
    # SDK invocation helpers
    # ------------------------------------------------------------------ #
    def _build_session_options(self) -> ClaudeAgentOptions:
        if ClaudeAgentOptions is None:
            raise ClaudeAgentRuntimeUnavailable(
                "Claude Agent SDK options are unavailable in this environment."
            )
        options = self.session_options
        if options is None or not isinstance(options, ClaudeAgentOptions):
            options = ClaudeAgentOptions(
                agents=self.agents,
                setting_sources=list(self.setting_sources),
            )
        else:
            updated = options
            if updated.agents is None:
                updated = replace(updated, agents=self.agents)
            if updated.setting_sources is None:
                updated = replace(updated, setting_sources=list(self.setting_sources))
            options = updated
        return options

    def _invoke_claude_agent(self, agent: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if self._agent_invoker is not None:
            return self._agent_invoker(agent, payload)
        return self._invoke_claude_agent_via_sdk(agent, payload)

    def _invoke_claude_agent_via_sdk(
        self, agent: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        if not self.sdk_available or query is None or ToolResultBlock is None:
            raise ClaudeAgentRuntimeUnavailable(
                "Claude Agent SDK is not fully available for agent execution."
            )
        self.ensure_session()
        options = self._build_session_options()
        tool_use_id = f"{agent}-{uuid.uuid4().hex}"

        async def _input_stream() -> Iterable[Dict[str, Any]]:
            yield {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_use_id,
                            "name": agent,
                            "input": payload,
                        }
                    ],
                },
                "parent_tool_use_id": None,
            }

        async def _collect_messages() -> List[Any]:
            responses: List[Any] = []
            async for message in query(prompt=_input_stream(), options=options):
                responses.append(message)
            return responses

        messages = asyncio.run(_collect_messages())

        tool_content: Any = None
        for message in messages:
            if AssistantMessage is not None and isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, ToolResultBlock) and block.tool_use_id == tool_use_id:
                        if getattr(block, "is_error", False):
                            raise RuntimeError(
                                f"Claude agent {agent} returned an error: {block.content}"
                            )
                        tool_content = block.content
            if ResultMessage is not None and isinstance(message, ResultMessage):
                if message.is_error:
                    raise RuntimeError(
                        message.result or f"Claude agent {agent} reported an error."
                    )

        if tool_content is None:
            return None

        return self._parse_tool_result(tool_content)

    def _parse_tool_result(self, content: Any) -> Dict[str, Any]:
        if isinstance(content, dict):
            return content
        text = ""
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    parts.append(str(item["text"]))
            text = "".join(parts).strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude agent returned non-JSON payload: {text}") from exc
        if not isinstance(data, dict):
            raise ValueError("Claude agent result must be a JSON object.")
        return data

    def _coerce_generator_output(self, data: Dict[str, Any]) -> GeneratorOutput:
        reasoning = str(data.get("reasoning", ""))
        final_answer = str(data.get("final_answer", ""))
        bullet_ids_payload = data.get("bullet_ids", [])
        bullet_ids: List[str] = []
        if isinstance(bullet_ids_payload, Sequence):
            for item in bullet_ids_payload:
                if isinstance(item, (str, int)):
                    bullet_ids.append(str(item))
        return GeneratorOutput(
            reasoning=reasoning,
            final_answer=final_answer,
            bullet_ids=bullet_ids,
            raw=data,
        )

    def _coerce_reflector_output(self, data: Dict[str, Any]) -> ReflectorOutput:
        from ..roles import BulletTag

        tags_payload = data.get("bullet_tags", [])
        bullet_tags: List[BulletTag] = []
        if isinstance(tags_payload, Sequence):
            for item in tags_payload:
                if isinstance(item, dict) and "id" in item and "tag" in item:
                    bullet_tags.append(
                        BulletTag(id=str(item["id"]), tag=str(item["tag"]).lower())
                    )
        return ReflectorOutput(
            reasoning=str(data.get("reasoning", "")),
            error_identification=str(data.get("error_identification", "")),
            root_cause_analysis=str(data.get("root_cause_analysis", "")),
            correct_approach=str(data.get("correct_approach", "")),
            key_insight=str(data.get("key_insight", "")),
            bullet_tags=bullet_tags,
            raw=data,
        )

    def _coerce_curator_output(self, data: Dict[str, Any]) -> CuratorOutput:
        delta_payload = data.get("delta") if isinstance(data, dict) else None
        target = delta_payload if isinstance(delta_payload, dict) else data
        if not isinstance(target, dict):
            raise ValueError("Claude curator response must be a JSON object.")
        delta = DeltaBatch.from_json(target)
        return CuratorOutput(delta=delta, raw=data)


__all__ = ["ACEClaudeSession", "ClaudeAgentRuntimeUnavailable"]
