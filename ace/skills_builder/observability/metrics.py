"""
Metrics Collector for ACE Skills Loop

Collects and aggregates metrics for session analysis and curator dashboards.
"""

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ToolMetrics:
    """Metrics for a single tool invocation."""

    tool_name: str
    invocation_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    total_duration_ms: float = 0.0
    avg_duration_ms: float = 0.0
    stderr_count: int = 0


@dataclass
class PhaseMetrics:
    """Metrics for a development phase."""

    phase_name: str
    entry_count: int = 0
    total_duration_seconds: float = 0.0
    tool_invocations: int = 0
    errors: int = 0


@dataclass
class SessionMetrics:
    """Aggregated metrics for a skills loop session."""

    session_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_duration_seconds: float = 0.0

    # Tool metrics
    tools: Dict[str, ToolMetrics] = field(default_factory=dict)

    # Phase metrics
    phases: Dict[str, PhaseMetrics] = field(default_factory=dict)

    # Coverage metrics
    coverage_deltas: List[Dict[str, float]] = field(default_factory=list)

    # Artifact metrics
    artifacts: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))

    # Hook events
    hook_events: Dict[str, int] = field(default_factory=lambda: defaultdict(int))


class MetricsCollector:
    """
    Collects and aggregates metrics for skills loop sessions.

    Provides methods for recording events and generating summary reports
    for curator analysis.
    """

    def __init__(self, session_id: str):
        """
        Initialize the metrics collector.

        Args:
            session_id: Session identifier
        """
        self.session_id = session_id
        self.metrics = SessionMetrics(
            session_id=session_id,
            started_at=datetime.now(),
        )

    def record_tool_invocation(
        self,
        tool_name: str,
        status: str,
        duration_ms: float,
        stderr_present: bool = False,
    ) -> None:
        """
        Record a tool invocation.

        Args:
            tool_name: Name of the tool
            status: Invocation status (success, failure, timeout)
            duration_ms: Duration in milliseconds
            stderr_present: Whether stderr was captured
        """
        if tool_name not in self.metrics.tools:
            self.metrics.tools[tool_name] = ToolMetrics(tool_name=tool_name)

        tool = self.metrics.tools[tool_name]
        tool.invocation_count += 1
        tool.total_duration_ms += duration_ms

        if status == "success":
            tool.success_count += 1
        elif status == "failure":
            tool.failure_count += 1

        if stderr_present:
            tool.stderr_count += 1

        # Update average duration
        tool.avg_duration_ms = tool.total_duration_ms / tool.invocation_count

    def record_phase_entry(
        self,
        phase_name: str,
        duration_seconds: float,
        tool_invocations: int,
        errors: int = 0,
    ) -> None:
        """
        Record a phase completion.

        Args:
            phase_name: Name of the phase
            duration_seconds: Phase duration
            tool_invocations: Number of tool invocations in phase
            errors: Number of errors encountered
        """
        if phase_name not in self.metrics.phases:
            self.metrics.phases[phase_name] = PhaseMetrics(phase_name=phase_name)

        phase = self.metrics.phases[phase_name]
        phase.entry_count += 1
        phase.total_duration_seconds += duration_seconds
        phase.tool_invocations += tool_invocations
        phase.errors += errors

    def record_coverage_delta(
        self,
        branch_before: float,
        branch_after: float,
        lines_before: float,
        lines_after: float,
    ) -> None:
        """
        Record a coverage change.

        Args:
            branch_before: Branch coverage before
            branch_after: Branch coverage after
            lines_before: Line coverage before
            lines_after: Line coverage after
        """
        delta = {
            "branch_delta": branch_after - branch_before,
            "lines_delta": lines_after - lines_before,
            "branch_after": branch_after,
            "lines_after": lines_after,
        }
        self.metrics.coverage_deltas.append(delta)

    def record_artifact(self, artifact_type: str, artifact_path: str) -> None:
        """
        Record an artifact creation.

        Args:
            artifact_type: Type of artifact
            artifact_path: Path to artifact
        """
        self.metrics.artifacts[artifact_type].append(artifact_path)

    def record_hook_event(self, hook_event: str) -> None:
        """
        Record a hook event.

        Args:
            hook_event: Hook event type
        """
        self.metrics.hook_events[hook_event] += 1

    def finalize(self) -> None:
        """Finalize metrics collection and calculate totals."""
        self.metrics.finished_at = datetime.now()
        self.metrics.total_duration_seconds = (
            self.metrics.finished_at - self.metrics.started_at
        ).total_seconds()

    def get_summary(self) -> Dict[str, any]:
        """
        Get a summary of collected metrics.

        Returns:
            Dictionary with summary statistics
        """
        summary = {
            "session_id": self.session_id,
            "duration_seconds": self.metrics.total_duration_seconds,
            "tools": {
                "total_invocations": sum(
                    t.invocation_count for t in self.metrics.tools.values()
                ),
                "unique_tools": len(self.metrics.tools),
                "success_rate": self._calculate_success_rate(),
                "by_tool": {
                    name: {
                        "invocations": t.invocation_count,
                        "success_rate": (
                            t.success_count / t.invocation_count
                            if t.invocation_count > 0
                            else 0.0
                        ),
                        "avg_duration_ms": t.avg_duration_ms,
                    }
                    for name, t in self.metrics.tools.items()
                },
            },
            "phases": {
                name: {
                    "entries": p.entry_count,
                    "total_duration_seconds": p.total_duration_seconds,
                    "avg_duration_seconds": (
                        p.total_duration_seconds / p.entry_count
                        if p.entry_count > 0
                        else 0.0
                    ),
                    "tool_invocations": p.tool_invocations,
                    "errors": p.errors,
                }
                for name, p in self.metrics.phases.items()
            },
            "coverage": {
                "total_deltas": len(self.metrics.coverage_deltas),
                "net_branch_change": sum(
                    d["branch_delta"] for d in self.metrics.coverage_deltas
                ),
                "net_lines_change": sum(
                    d["lines_delta"] for d in self.metrics.coverage_deltas
                ),
                "final_branch": (
                    self.metrics.coverage_deltas[-1]["branch_after"]
                    if self.metrics.coverage_deltas
                    else 0.0
                ),
                "final_lines": (
                    self.metrics.coverage_deltas[-1]["lines_after"]
                    if self.metrics.coverage_deltas
                    else 0.0
                ),
            },
            "artifacts": {
                artifact_type: len(paths)
                for artifact_type, paths in self.metrics.artifacts.items()
            },
            "hooks": dict(self.metrics.hook_events),
        }

        return summary

    def export_json(self, output_path: Path) -> None:
        """
        Export metrics to JSON file.

        Args:
            output_path: Path to output file
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        summary = self.get_summary()

        with open(output_path, "w") as f:
            json.dump(summary, f, indent=2)

    def _calculate_success_rate(self) -> float:
        """
        Calculate overall tool success rate.

        Returns:
            Success rate as fraction (0.0-1.0)
        """
        total_invocations = sum(
            t.invocation_count for t in self.metrics.tools.values()
        )
        total_successes = sum(t.success_count for t in self.metrics.tools.values())

        if total_invocations == 0:
            return 0.0

        return total_successes / total_invocations

    def get_phase_order(self) -> List[str]:
        """
        Get phases in chronological order of first entry.

        Returns:
            Ordered list of phase names
        """
        # This is a simplified version; would need timestamp tracking for real order
        phase_order = ["plan", "build", "test", "review", "document"]
        return [p for p in phase_order if p in self.metrics.phases]
