"""Tests for the ACE Claude session integration."""

from __future__ import annotations

from collections import deque
import unittest

from ace import (
    ACEClaudeSession,
    HookMatcher,
    OfflineAdapter,
    Sample,
    TaskEnvironment,
    EnvironmentResult,
    Generator,
    GeneratorOutput,
    Reflector,
    ReflectorOutput,
    Curator,
)
from ace.llm import DummyLLMClient
from ace.playbook import Playbook


try:  # pragma: no cover - optional dependency
    import claude_agent_sdk  # type: ignore[import-not-found]

    CLAUDE_SDK_AVAILABLE = True
except Exception:  # pragma: no cover
    CLAUDE_SDK_AVAILABLE = False


class _EchoEnvironment(TaskEnvironment):
    def evaluate(self, sample: Sample, generator_output):
        return EnvironmentResult(
            feedback="accepted",
            ground_truth=sample.ground_truth,
            metrics={"accuracy": 1.0},
        )


class _FailingGenerator:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, **_kwargs):
        self.calls += 1
        raise AssertionError("local generator should not run")


class _FailingReflector:
    def __init__(self) -> None:
        self.calls = 0

    def reflect(self, **_kwargs):
        self.calls += 1
        raise AssertionError("local reflector should not run")


class _FailingCurator:
    def __init__(self) -> None:
        self.calls = 0

    def curate(self, **_kwargs):
        self.calls += 1
        raise AssertionError("local curator should not run")


class _StaticAgentInvoker:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, agent: str, payload):
        self.calls.append((agent, payload))
        return self.responses.get(agent)


def _build_llm_client() -> DummyLLMClient:
    client = DummyLLMClient(responses=deque())
    client.queue('{"reasoning": "calc", "final_answer": "4", "bullet_ids": ["b-1"]}')
    client.queue(
        '{"reasoning": "ok", "error_identification": "", "root_cause_analysis": "",'
        ' "correct_approach": "", "key_insight": "Use addition",'
        ' "bullet_tags": [{"id": "b-1", "tag": "helpful"}]}'
    )
    client.queue(
        '{"reasoning": "update", "operations": '
        '[{"type": "ADD", "section": "General", "content": "Add numbers", "bullet_id": "b-1"}]}'
    )
    return client


def test_claude_session_fallback_runs_adapter() -> None:
    client = _build_llm_client()
    generator = Generator(client)
    reflector = Reflector(client)
    curator = Curator(client)
    playbook = Playbook()

    hook_events = []

    def capture(event: str, payload):
        hook_events.append((event, payload.get("agent")))

    session = ACEClaudeSession(
        generator=generator,
        reflector=reflector,
        curator=curator,
        hooks=[
            HookMatcher(event="pre_tool_use", callback=capture),
            HookMatcher(event="post_tool_use", callback=capture),
            HookMatcher(event="environment_feedback", callback=capture),
        ],
    )

    adapter = OfflineAdapter(
        playbook=playbook,
        generator=generator,
        reflector=reflector,
        curator=curator,
        claude_session=session,
    )

    sample = Sample(question="What is 2+2?", ground_truth="4", metadata={"sample_id": "s-1"})
    environment = _EchoEnvironment()

    results = adapter.run([sample], environment, epochs=1)

    assert len(results) == 1
    step = results[0]
    assert step.generator_output.final_answer == "4"
    assert playbook.get_bullet("b-1") is not None

    # Hooks should capture generator/reflector/curator traffic plus environment feedback.
    events_by_type = [event for event, _ in hook_events]
    assert "pre_tool_use" in events_by_type
    assert "post_tool_use" in events_by_type
    assert "environment_feedback" in events_by_type


@unittest.skipUnless(CLAUDE_SDK_AVAILABLE, "Claude Agent SDK not available")
def test_claude_session_prefers_sdk_generator() -> None:
    playbook = Playbook()

    generator = _FailingGenerator()
    reflector = _FailingReflector()
    curator = _FailingCurator()

    invoker = _StaticAgentInvoker(
        {
            "ace-generator": {
                "reasoning": "sdk",
                "final_answer": "sdk answer",
                "bullet_ids": ["b-1"],
            }
        }
    )

    session = ACEClaudeSession(
        generator=generator,
        reflector=reflector,
        curator=curator,
        agent_invoker=invoker,
    )

    output = session.run_generator(
        question="What is 2+2?",
        context="math",
        playbook=playbook,
    )

    assert output.final_answer == "sdk answer"
    assert generator.calls == 0
    assert invoker.calls and invoker.calls[0][0] == "ace-generator"


@unittest.skipUnless(CLAUDE_SDK_AVAILABLE, "Claude Agent SDK not available")
def test_claude_session_reflector_sdk_output() -> None:
    playbook = Playbook()
    generator_output = GeneratorOutput(
        reasoning="calc",
        final_answer="4",
        bullet_ids=["b-1"],
        raw={"reasoning": "calc", "final_answer": "4"},
    )

    generator = _FailingGenerator()
    reflector = _FailingReflector()
    curator = _FailingCurator()

    invoker = _StaticAgentInvoker(
        {
            "ace-reflector": {
                "reasoning": "analysis",
                "error_identification": "none",
                "root_cause_analysis": "",
                "correct_approach": "do math",
                "key_insight": "addition",
                "bullet_tags": [{"id": "b-1", "tag": "helpful"}],
            }
        }
    )

    session = ACEClaudeSession(
        generator=generator,
        reflector=reflector,
        curator=curator,
        agent_invoker=invoker,
    )

    output = session.run_reflector(
        question="What is 2+2?",
        generator_output=generator_output,
        playbook=playbook,
        ground_truth="4",
        feedback="correct",
    )

    assert output.key_insight == "addition"
    assert output.bullet_tags[0].tag == "helpful"
    assert reflector.calls == 0
    assert invoker.calls and invoker.calls[0][0] == "ace-reflector"


@unittest.skipUnless(CLAUDE_SDK_AVAILABLE, "Claude Agent SDK not available")
def test_claude_session_curator_sdk_output() -> None:
    playbook = Playbook()

    generator = _FailingGenerator()
    reflector = _FailingReflector()
    curator = _FailingCurator()

    invoker = _StaticAgentInvoker(
        {
            "ace-curator": {
                "reasoning": "update",
                "operations": [
                    {
                        "type": "ADD",
                        "section": "General",
                        "content": "Add numbers",
                        "bullet_id": "b-1",
                    }
                ],
            }
        }
    )

    session = ACEClaudeSession(
        generator=generator,
        reflector=reflector,
        curator=curator,
        agent_invoker=invoker,
    )

    reflection = ReflectorOutput(
        reasoning="analysis",
        error_identification="",
        root_cause_analysis="",
        correct_approach="",
        key_insight="",
        bullet_tags=[],
        raw={},
    )

    output = session.run_curator(
        reflection=reflection,
        playbook=playbook,
        question_context="math",
        progress="1/1",
    )

    assert output.delta.operations[0].content == "Add numbers"
    assert curator.calls == 0
    assert invoker.calls and invoker.calls[0][0] == "ace-curator"
