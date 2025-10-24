"""Tests for the ACE Claude session integration."""

from __future__ import annotations

from collections import deque

from ace import (
    ACEClaudeSession,
    HookMatcher,
    OfflineAdapter,
    Sample,
    TaskEnvironment,
    EnvironmentResult,
    Generator,
    Reflector,
    Curator,
)
from ace.llm import DummyLLMClient
from ace.playbook import Playbook


class _EchoEnvironment(TaskEnvironment):
    def evaluate(self, sample: Sample, generator_output):
        return EnvironmentResult(
            feedback="accepted",
            ground_truth=sample.ground_truth,
            metrics={"accuracy": 1.0},
        )


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
