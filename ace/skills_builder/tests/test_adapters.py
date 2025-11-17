"""
Integration tests for ACE Skills Builder Adapters.
"""

import unittest
from datetime import datetime

from ace.delta import DeltaBatch, DeltaOperation
from ace.playbook import Bullet, Playbook
from ace.skills_builder.adapters import PlaybookAdapter, TrajectoryAdapter
from ace.skills_builder.models import TranscriptEvent


class TestPlaybookAdapter(unittest.TestCase):
    """Test cases for PlaybookAdapter."""

    def setUp(self):
        """Set up test playbook."""
        self.playbook = Playbook()
        self.playbook.bullets = [
            Bullet(
                strategy="Use descriptive variable names",
                helpful_count=5,
                harmful_count=1,
                tags={"code_quality", "readability"},
            ),
            Bullet(
                strategy="Write unit tests first",
                helpful_count=8,
                harmful_count=0,
                tags={"testing", "tdd"},
            ),
            Bullet(
                strategy="Avoid premature optimization",
                helpful_count=3,
                harmful_count=2,
                tags={"performance"},
            ),
        ]

    def test_to_system_prompt(self):
        """Test converting playbook to system prompt."""
        adapter = PlaybookAdapter(self.playbook)
        prompt = adapter.to_system_prompt()

        # Check content
        self.assertIn("ACE Playbook Context", prompt)
        self.assertIn("Use descriptive variable names", prompt)
        self.assertIn("Write unit tests first", prompt)
        self.assertIn("[+5/-1]", prompt)  # Counters included by default

    def test_to_system_prompt_without_counters(self):
        """Test system prompt without counters."""
        adapter = PlaybookAdapter(self.playbook)
        prompt = adapter.to_system_prompt(include_counters=False)

        self.assertNotIn("[+", prompt)
        self.assertNotIn("/-", prompt)

    def test_to_system_prompt_max_bullets(self):
        """Test limiting bullets in system prompt."""
        adapter = PlaybookAdapter(self.playbook)
        prompt = adapter.to_system_prompt(max_bullets=2)

        # Should only include first 2 bullets
        lines = prompt.split("\n")
        bullet_lines = [l for l in lines if l.strip().startswith("1.") or l.strip().startswith("2.") or l.strip().startswith("3.")]
        self.assertLessEqual(len(bullet_lines), 3)  # At most 2 bullets + potential tag lines

    def test_to_context_summary(self):
        """Test generating context summary."""
        adapter = PlaybookAdapter(self.playbook)
        summary = adapter.to_context_summary()

        self.assertEqual(summary["total_bullets"], 3)
        self.assertEqual(summary["total_helpful_signals"], 16)
        self.assertEqual(summary["total_harmful_signals"], 3)
        self.assertEqual(len(summary["top_strategies"]), 3)

    def test_get_relevant_bullets(self):
        """Test filtering bullets by tags."""
        adapter = PlaybookAdapter(self.playbook)

        # Get bullets tagged with "testing"
        relevant = adapter.get_relevant_bullets(["testing"], min_score=0)
        self.assertEqual(len(relevant), 1)
        self.assertEqual(relevant[0].strategy, "Write unit tests first")

        # Get bullets with min score
        relevant = adapter.get_relevant_bullets(["code_quality"], min_score=4)
        self.assertEqual(len(relevant), 1)

    def test_apply_delta_batch(self):
        """Test applying delta operations to playbook."""
        adapter = PlaybookAdapter(self.playbook)

        # Create delta batch
        operations = [
            DeltaOperation(
                op_type="ADD",
                content="Always validate input parameters",
                tags=["validation", "security"],
            ),
            DeltaOperation(
                op_type="TAG",
                target="Use descriptive variable names",
                tags=["best_practice"],
            ),
        ]

        batch = DeltaBatch(operations=operations)
        initial_count = len(adapter.playbook.bullets)

        adapter.apply_delta_batch(batch)

        # Verify ADD operation
        self.assertEqual(len(adapter.playbook.bullets), initial_count + 1)

        # Verify TAG operation
        first_bullet = adapter.playbook.bullets[0]
        self.assertIn("best_practice", first_bullet.tags)


class TestTrajectoryAdapter(unittest.TestCase):
    """Test cases for TrajectoryAdapter."""

    def test_sdk_message_to_event(self):
        """Test converting SDK messages to transcript events."""
        # Assistant message
        msg = {
            "type": "assistant_message",
            "content": "Hello, I can help with that.",
        }

        event = TrajectoryAdapter.sdk_message_to_event(
            msg, "session_123", "task_456"
        )

        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, "assistant_message")
        self.assertEqual(event.session_id, "session_123")
        self.assertEqual(event.task_id, "task_456")

        # Tool use message
        tool_msg = {
            "type": "tool_use",
            "name": "playbook_diff",
            "input": {"arg": "value"},
            "id": "tool_123",
        }

        tool_event = TrajectoryAdapter.sdk_message_to_event(
            tool_msg, "session_123", "task_456"
        )

        self.assertIsNotNone(tool_event)
        self.assertEqual(tool_event.event_type, "tool_use_block")
        self.assertEqual(tool_event.payload["tool_name"], "playbook_diff")

    def test_extract_skill_outcomes(self):
        """Test extracting skill outcomes from events."""
        events = [
            TranscriptEvent(
                event_type="tool_use_block",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_456",
                payload={
                    "tool_name": "playbook_diff",
                    "tool_use_id": "tool_1",
                    "tool_input": {},
                },
            ),
            TranscriptEvent(
                event_type="tool_result_block",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_456",
                payload={
                    "tool_use_id": "tool_1",
                    "content": "Result",
                    "is_error": False,
                },
            ),
        ]

        outcomes = TrajectoryAdapter.extract_skill_outcomes(events)

        self.assertEqual(len(outcomes), 1)
        self.assertEqual(outcomes[0].skill_name, "playbook_diff")
        self.assertFalse(outcomes[0].stderr_present)

    def test_filter_events_by_phase(self):
        """Test filtering events by phase."""
        events = [
            TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_456",
                payload={"phase": "plan", "content": "Planning..."},
            ),
            TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_456",
                payload={"phase": "build", "content": "Building..."},
            ),
            TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_456",
                payload={"phase": "plan", "content": "More planning..."},
            ),
        ]

        plan_events = TrajectoryAdapter.filter_events_by_phase(events, "plan")
        self.assertEqual(len(plan_events), 2)

        build_events = TrajectoryAdapter.filter_events_by_phase(events, "build")
        self.assertEqual(len(build_events), 1)

    def test_group_events_by_task(self):
        """Test grouping events by task ID."""
        events = [
            TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_1",
                payload={},
            ),
            TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_2",
                payload={},
            ),
            TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id="session_123",
                task_id="task_1",
                payload={},
            ),
        ]

        grouped = TrajectoryAdapter.group_events_by_task(events)

        self.assertEqual(len(grouped), 2)
        self.assertEqual(len(grouped["task_1"]), 2)
        self.assertEqual(len(grouped["task_2"]), 1)


if __name__ == "__main__":
    unittest.main()
