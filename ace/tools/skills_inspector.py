"""
ACE Skills Session Inspector

A Textual TUI for inspecting ACE skills loop transcripts.

Provides:
- Timeline view of events (assistant messages, tool use, results, subagents)
- Context pane with playbook summary and session metadata
- Skill detail pane for tool invocations
- Export functionality for curated deltas

Usage:
    python -m ace.tools.skills_inspector <transcript.jsonl>
    python -m ace.tools.skills_inspector docs/transcripts/2024-01-15.jsonl
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from textual.app import App, ComposeResult
    from textual.containers import Container, Horizontal, Vertical
    from textual.widgets import Button, DataTable, Footer, Header, Static, TabbedContent, TabPane

    TEXTUAL_AVAILABLE = True
except ImportError:
    TEXTUAL_AVAILABLE = False

from ace.skills_builder.models import (
    SkillOutcome,
    SkillsSessionMetadata,
    TranscriptEvent,
)


class SessionModel:
    """
    Model for a skills loop session loaded from JSONL transcript.
    """

    def __init__(self, transcript_path: Path):
        """
        Load a session from JSONL transcript.

        Args:
            transcript_path: Path to JSONL transcript file
        """
        self.transcript_path = transcript_path
        self.events: List[TranscriptEvent] = []
        self.session_metadata: Dict[str, Any] = {}
        self.sessions: Dict[str, List[TranscriptEvent]] = {}

        self._load_transcript()

    def _load_transcript(self) -> None:
        """Load and parse the JSONL transcript."""
        with open(self.transcript_path) as f:
            for line in f:
                if not line.strip():
                    continue

                try:
                    record = json.loads(line)

                    # Handle session header
                    if record.get("type") == "session_header":
                        self.session_metadata = record
                        continue

                    # Handle session footer
                    if record.get("type") == "session_footer":
                        continue

                    # Try to parse as TranscriptEvent
                    if "event_type" in record:
                        event = TranscriptEvent.model_validate(record)
                        self.events.append(event)

                        # Group by session
                        session_id = event.session_id
                        if session_id not in self.sessions:
                            self.sessions[session_id] = []
                        self.sessions[session_id].append(event)

                except Exception as e:
                    print(f"Warning: Failed to parse line: {e}", file=sys.stderr)

    def get_events_by_session(self, session_id: str) -> List[TranscriptEvent]:
        """Get all events for a specific session."""
        return self.sessions.get(session_id, [])

    def get_skill_outcomes(self) -> List[Dict[str, Any]]:
        """Extract skill outcomes from events."""
        outcomes = []
        tool_use_map = {}

        # Match tool use with tool results
        for event in self.events:
            if event.event_type == "tool_use_block":
                tool_use_id = event.payload.get("tool_use_id")
                if tool_use_id:
                    tool_use_map[tool_use_id] = {"use": event, "result": None}

            elif event.event_type == "tool_result_block":
                tool_use_id = event.payload.get("tool_use_id")
                if tool_use_id and tool_use_id in tool_use_map:
                    tool_use_map[tool_use_id]["result"] = event

        # Create outcomes
        for tool_use_id, data in tool_use_map.items():
            use_event = data["use"]
            result_event = data.get("result")

            if result_event:
                outcome = {
                    "skill_name": use_event.payload.get("tool_name", "unknown"),
                    "started_at": use_event.timestamp.isoformat(),
                    "finished_at": result_event.timestamp.isoformat(),
                    "tool_use_id": tool_use_id,
                    "success": not result_event.payload.get("is_error", False),
                }
                outcomes.append(outcome)

        return outcomes


class SkillsInspectorApp(App):
    """
    Textual TUI application for inspecting skills loop transcripts.
    """

    CSS = """
    Screen {
        background: $surface;
    }

    #timeline-pane {
        width: 60%;
    }

    #context-pane {
        width: 40%;
    }

    .event-card {
        margin: 1;
        padding: 1;
        background: $panel;
        border: solid $primary;
    }

    .assistant-message {
        border: solid green;
    }

    .tool-use {
        border: solid blue;
    }

    .tool-result {
        border: solid cyan;
    }

    .error {
        border: solid red;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("s", "toggle_slash_filter", "Filter Slash Commands"),
        ("e", "export_deltas", "Export Deltas"),
        ("left", "previous_tab", "Previous Tab"),
        ("right", "next_tab", "Next Tab"),
    ]

    def __init__(self, session_model: SessionModel):
        """
        Initialize the inspector app.

        Args:
            session_model: Loaded session model
        """
        super().__init__()
        self.session_model = session_model
        self.slash_filter_enabled = False

    def compose(self) -> ComposeResult:
        """Create child widgets."""
        yield Header()

        with TabbedContent():
            with TabPane("Timeline", id="timeline-tab"):
                yield self._create_timeline_view()

            with TabPane("Context", id="context-tab"):
                yield self._create_context_view()

            with TabPane("Skills", id="skills-tab"):
                yield self._create_skills_view()

        yield Footer()

    def _create_timeline_view(self) -> Container:
        """Create the timeline view widget."""
        container = Vertical(id="timeline-pane")

        # Add events
        for event in self.session_model.events:
            event_widget = self._create_event_widget(event)
            if event_widget:
                container.compose_add_child(event_widget)

        return container

    def _create_context_view(self) -> Container:
        """Create the context view widget."""
        container = Vertical(id="context-pane")

        # Session metadata
        metadata = self.session_model.session_metadata
        metadata_text = f"""
# Session Metadata

**Task ID**: {metadata.get('task_id', 'unknown')}
**Session ID**: {metadata.get('session_id', 'unknown')}
**Started**: {metadata.get('started_at', 'unknown')}

## Statistics

- Total events: {len(self.session_model.events)}
- Unique sessions: {len(self.session_model.sessions)}
- Skill outcomes: {len(self.session_model.get_skill_outcomes())}
"""

        container.compose_add_child(Static(metadata_text))
        return container

    def _create_skills_view(self) -> Container:
        """Create the skills detail view."""
        container = Vertical(id="skills-pane")

        # Create table of skill outcomes
        table = DataTable()
        table.add_columns("Skill", "Started", "Duration", "Status")

        for outcome in self.session_model.get_skill_outcomes():
            started = datetime.fromisoformat(outcome["started_at"])
            finished = datetime.fromisoformat(outcome["finished_at"])
            duration = (finished - started).total_seconds()

            status = "✓ Success" if outcome["success"] else "✗ Failed"

            table.add_row(
                outcome["skill_name"],
                started.strftime("%H:%M:%S"),
                f"{duration:.1f}s",
                status,
            )

        container.compose_add_child(table)
        return container

    def _create_event_widget(self, event: TranscriptEvent) -> Optional[Static]:
        """
        Create a widget for a transcript event.

        Args:
            event: Transcript event

        Returns:
            Widget or None if filtered
        """
        # Apply filters
        if self.slash_filter_enabled and event.event_type != "slash_command":
            return None

        # Format event content
        event_type = event.event_type
        timestamp = event.timestamp.strftime("%H:%M:%S")

        if event_type == "assistant_message":
            content = event.payload.get("content", "")
            text = f"[{timestamp}] Assistant: {content[:100]}"
            css_class = "assistant-message"

        elif event_type == "tool_use_block":
            tool_name = event.payload.get("tool_name", "unknown")
            text = f"[{timestamp}] Tool Use: {tool_name}"
            css_class = "tool-use"

        elif event_type == "tool_result_block":
            is_error = event.payload.get("is_error", False)
            status = "ERROR" if is_error else "OK"
            text = f"[{timestamp}] Tool Result: {status}"
            css_class = "error" if is_error else "tool-result"

        elif event_type == "slash_command":
            command = event.payload.get("command", "unknown")
            text = f"[{timestamp}] Command: {command}"
            css_class = "tool-use"

        else:
            text = f"[{timestamp}] {event_type}"
            css_class = "event-card"

        widget = Static(text, classes=f"event-card {css_class}")
        return widget

    def action_toggle_slash_filter(self) -> None:
        """Toggle slash command filter."""
        self.slash_filter_enabled = not self.slash_filter_enabled
        # Would re-render timeline here
        self.notify(
            f"Slash filter: {'ON' if self.slash_filter_enabled else 'OFF'}"
        )

    def action_export_deltas(self) -> None:
        """Export selected deltas to JSON."""
        output_path = (
            Path("ace/playbook_deltas")
            / f"{self.session_model.session_metadata.get('session_id', 'unknown')}.json"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect skill outcomes for export
        outcomes = self.session_model.get_skill_outcomes()

        with open(output_path, "w") as f:
            json.dump({"skill_outcomes": outcomes}, f, indent=2)

        self.notify(f"Exported to: {output_path}")


def load_transcript(path: Path) -> SessionModel:
    """
    Load a transcript file into a SessionModel.

    Args:
        path: Path to JSONL transcript

    Returns:
        Loaded SessionModel
    """
    if not path.exists():
        raise FileNotFoundError(f"Transcript not found: {path}")

    return SessionModel(path)


def main() -> int:
    """
    CLI entry point for the skills inspector.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="ACE Skills Session Inspector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Inspect a transcript
  python -m ace.tools.skills_inspector docs/transcripts/2024-01-15.jsonl

  # Export deltas from a session
  python -m ace.tools.skills_inspector transcript.jsonl --export

Keyboard shortcuts:
  q     - Quit
  s     - Toggle slash command filter
  e     - Export deltas to JSON
  ←/→   - Switch tabs
""",
    )

    parser.add_argument(
        "transcript",
        type=Path,
        help="Path to JSONL transcript file",
    )

    parser.add_argument(
        "--export",
        action="store_true",
        help="Export deltas without launching TUI",
    )

    args = parser.parse_args()

    # Check if Textual is available
    if not TEXTUAL_AVAILABLE and not args.export:
        print(
            "Error: Textual library not found. Install with: pip install textual",
            file=sys.stderr,
        )
        print("\nAlternatively, use --export to export deltas without TUI")
        return 1

    try:
        # Load transcript
        session_model = load_transcript(args.transcript)

        print(f"Loaded transcript: {args.transcript}")
        print(f"  Events: {len(session_model.events)}")
        print(f"  Sessions: {len(session_model.sessions)}")
        print(f"  Skill outcomes: {len(session_model.get_skill_outcomes())}")
        print()

        if args.export:
            # Export mode
            output_path = (
                Path("ace/playbook_deltas")
                / f"{session_model.session_metadata.get('session_id', 'unknown')}.json"
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)

            outcomes = session_model.get_skill_outcomes()

            with open(output_path, "w") as f:
                json.dump({"skill_outcomes": outcomes}, f, indent=2)

            print(f"✓ Exported to: {output_path}")
            return 0

        else:
            # Launch TUI
            app = SkillsInspectorApp(session_model)
            app.run()
            return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
