"""
Trajectory Adapter

Converts codex exec SDK messages to ACE trajectory entries and vice versa.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ace.skills_builder.models import (
    SkillOutcome,
    TranscriptEvent,
)

logger = logging.getLogger(__name__)


class TrajectoryAdapter:
    """
    Adapter for converting between codex exec SDK messages and ACE trajectory entries.

    Provides bidirectional conversion and filtering capabilities for skills loop
    transcript capture and replay.
    """

    @staticmethod
    def sdk_message_to_event(
        message: Dict[str, Any],
        session_id: str,
        task_id: str,
    ) -> Optional[TranscriptEvent]:
        """
        Convert a codex exec SDK message to an ACE transcript event.

        Args:
            message: SDK message dictionary
            session_id: Current session ID
            task_id: Current task ID

        Returns:
            TranscriptEvent or None if message type is not supported
        """
        msg_type = message.get("type")

        if msg_type == "assistant_message":
            return TranscriptEvent(
                event_type="assistant_message",
                timestamp=datetime.now(),
                session_id=session_id,
                task_id=task_id,
                payload={
                    "content": message.get("content", ""),
                    "role": "assistant",
                },
                thinking_snippet=TrajectoryAdapter._extract_thinking(
                    message
                ),
            )

        elif msg_type == "user_message":
            return TranscriptEvent(
                event_type="user_message",
                timestamp=datetime.now(),
                session_id=session_id,
                task_id=task_id,
                payload={
                    "content": message.get("content", ""),
                    "role": "user",
                },
            )

        elif msg_type == "tool_use":
            return TranscriptEvent(
                event_type="tool_use_block",
                timestamp=datetime.now(),
                session_id=session_id,
                task_id=task_id,
                payload={
                    "tool_name": message.get("name"),
                    "tool_input": message.get("input", {}),
                    "tool_use_id": message.get("id"),
                },
            )

        elif msg_type == "tool_result":
            return TranscriptEvent(
                event_type="tool_result_block",
                timestamp=datetime.now(),
                session_id=session_id,
                task_id=task_id,
                payload={
                    "tool_use_id": message.get("tool_use_id"),
                    "content": message.get("content"),
                    "is_error": message.get("is_error", False),
                },
            )

        else:
            logger.debug(f"Unsupported message type: {msg_type}")
            return None

    @staticmethod
    def extract_skill_outcomes(
        events: List[TranscriptEvent],
        permission_mode: str = "plan",
    ) -> List[SkillOutcome]:
        """
        Extract skill outcomes from a list of transcript events.

        Pairs tool_use_block and tool_result_block events to create SkillOutcome records.

        Args:
            events: List of transcript events
            permission_mode: Permission mode during execution

        Returns:
            List of SkillOutcome records
        """
        outcomes = []
        tool_use_map = {}

        # First pass: collect all tool use events
        for event in events:
            if event.event_type == "tool_use_block":
                tool_use_id = event.payload.get("tool_use_id")
                if tool_use_id:
                    tool_use_map[tool_use_id] = {
                        "event": event,
                        "result": None,
                    }

        # Second pass: match tool results
        for event in events:
            if event.event_type == "tool_result_block":
                tool_use_id = event.payload.get("tool_use_id")
                if tool_use_id and tool_use_id in tool_use_map:
                    tool_use_map[tool_use_id]["result"] = event

        # Third pass: create outcomes
        for tool_use_id, data in tool_use_map.items():
            use_event = data["event"]
            result_event = data.get("result")

            if result_event:
                outcome = SkillOutcome(
                    skill_name=use_event.payload.get("tool_name", "unknown"),
                    started_at=use_event.timestamp,
                    finished_at=result_event.timestamp,
                    result_summary=TrajectoryAdapter._summarize_result(
                        result_event.payload
                    ),
                    permission_mode=permission_mode,
                    stderr_present=result_event.payload.get("is_error", False),
                    artifact_paths=[],
                )
                outcomes.append(outcome)

        logger.debug(f"Extracted {len(outcomes)} skill outcomes from events")
        return outcomes

    @staticmethod
    def filter_events_by_phase(
        events: List[TranscriptEvent], phase: str
    ) -> List[TranscriptEvent]:
        """
        Filter events by development phase tag.

        Args:
            events: List of transcript events
            phase: Phase name (plan, build, test, review, document)

        Returns:
            Filtered list of events
        """
        filtered = []

        for event in events:
            event_phase = event.payload.get("phase")
            if event_phase == phase:
                filtered.append(event)

        logger.debug(
            f"Filtered {len(filtered)} events for phase: {phase}"
        )
        return filtered

    @staticmethod
    def _extract_thinking(message: Dict[str, Any]) -> Optional[str]:
        """
        Extract and redact thinking tokens from a message.

        Args:
            message: SDK message

        Returns:
            Redacted thinking snippet or None
        """
        thinking = message.get("thinking")
        if not thinking:
            return None

        # Basic redaction of potentially sensitive patterns
        redacted = thinking

        # Redact file paths
        import re

        redacted = re.sub(r"/[a-zA-Z0-9_/.-]+", "[PATH]", redacted)

        # Redact API keys
        redacted = re.sub(
            r"[a-zA-Z0-9_-]{20,}", "[REDACTED_KEY]", redacted
        )

        # Truncate if too long
        max_length = 500
        if len(redacted) > max_length:
            redacted = redacted[:max_length] + "..."

        return redacted

    @staticmethod
    def _summarize_result(result_payload: Dict[str, Any]) -> str:
        """
        Create a summary of a tool result.

        Args:
            result_payload: Tool result payload

        Returns:
            Summary string
        """
        content = result_payload.get("content", "")
        is_error = result_payload.get("is_error", False)

        if is_error:
            return f"ERROR: {str(content)[:200]}"

        # Truncate long results
        if isinstance(content, str):
            if len(content) > 300:
                return content[:300] + "..."
            return content

        return str(content)[:300]

    @staticmethod
    def group_events_by_task(
        events: List[TranscriptEvent],
    ) -> Dict[str, List[TranscriptEvent]]:
        """
        Group events by task_id.

        Args:
            events: List of transcript events

        Returns:
            Dictionary mapping task_id to events
        """
        grouped = {}

        for event in events:
            task_id = event.task_id
            if task_id not in grouped:
                grouped[task_id] = []
            grouped[task_id].append(event)

        logger.debug(f"Grouped events into {len(grouped)} tasks")
        return grouped

    @staticmethod
    def calculate_event_statistics(
        events: List[TranscriptEvent],
    ) -> Dict[str, Any]:
        """
        Calculate statistics from a list of events.

        Args:
            events: List of transcript events

        Returns:
            Dictionary with event statistics
        """
        stats = {
            "total_events": len(events),
            "by_type": {},
            "unique_sessions": set(),
            "unique_tasks": set(),
            "time_span": None,
        }

        if not events:
            return stats

        # Count by type
        for event in events:
            event_type = event.event_type
            stats["by_type"][event_type] = (
                stats["by_type"].get(event_type, 0) + 1
            )
            stats["unique_sessions"].add(event.session_id)
            stats["unique_tasks"].add(event.task_id)

        # Calculate time span
        timestamps = [e.timestamp for e in events]
        if timestamps:
            stats["time_span"] = {
                "start": min(timestamps).isoformat(),
                "end": max(timestamps).isoformat(),
                "duration_seconds": (
                    max(timestamps) - min(timestamps)
                ).total_seconds(),
            }

        # Convert sets to counts
        stats["unique_sessions"] = len(stats["unique_sessions"])
        stats["unique_tasks"] = len(stats["unique_tasks"])

        return stats
