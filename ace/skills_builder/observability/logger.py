"""
Structured Logger for ACE Skills Loop

Provides JSON-structured logging with curator-visible fields, thinking token exposure,
and stdout/stderr parity.
"""

import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ace.skills_builder.models import PermissionMode


class SkillsLoopLogger:
    """
    Structured logger for skills loop sessions.

    Emits JSON logs with standardized fields for curator visibility,
    inspector replay, and metrics collection.
    """

    def __init__(
        self,
        session_id: str,
        log_file: Optional[Path] = None,
        log_level: str = "INFO",
    ):
        """
        Initialize the skills loop logger.

        Args:
            session_id: Session identifier
            log_file: Optional file path for log persistence
            log_level: Logging level (DEBUG, INFO, WARN, ERROR)
        """
        self.session_id = session_id
        self.log_file = log_file

        # Set up Python logger
        self.logger = logging.getLogger(f"ace.skills.{session_id}")
        self.logger.setLevel(getattr(logging, log_level.upper()))

        # Create JSON formatter
        formatter = JSONFormatter(session_id)

        # Add console handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Add file handler if specified
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)

    def log_tool_invocation(
        self,
        tool_name: str,
        tool_status: str,
        duration_ms: float,
        permission_mode: PermissionMode,
        phase: str,
        stderr_present: bool = False,
        stderr_content: Optional[str] = None,
    ) -> None:
        """
        Log a tool invocation event.

        Args:
            tool_name: Name of the invoked tool
            tool_status: Status (success, failure, timeout)
            duration_ms: Execution duration in milliseconds
            permission_mode: Permission mode during invocation
            phase: Development phase (plan, build, test, review, document)
            stderr_present: Whether stderr output was captured
            stderr_content: Optional stderr content (truncated)
        """
        extra = {
            "event_type": "tool_invocation",
            "tool_name": tool_name,
            "tool_status": tool_status,
            "duration_ms": duration_ms,
            "permission_mode": permission_mode,
            "phase": phase,
            "stderr_present": stderr_present,
            "curator_visibility": True,
        }

        if stderr_present and stderr_content:
            # Truncate stderr to reasonable length
            extra["stderr_preview"] = self._truncate_stderr(stderr_content)

        level = logging.ERROR if tool_status == "failure" else logging.INFO
        self.logger.log(
            level, f"Tool invocation: {tool_name} ({tool_status})", extra=extra
        )

    def log_thinking_snippet(
        self,
        task_id: str,
        thinking_content: str,
        phase: str,
    ) -> None:
        """
        Log thinking tokens with redaction.

        Args:
            task_id: Task identifier
            thinking_content: Raw thinking content
            phase: Current phase
        """
        # Redact sensitive information
        redacted = self._redact_thinking(thinking_content)

        extra = {
            "event_type": "thinking_tokens",
            "task_id": task_id,
            "phase": phase,
            "thinking_snippet": redacted,
            "curator_visibility": True,
        }

        self.logger.debug("Thinking tokens captured", extra=extra)

    def log_phase_transition(
        self,
        from_phase: str,
        to_phase: str,
        trigger_reason: str,
        task_id: str,
    ) -> None:
        """
        Log a phase transition.

        Args:
            from_phase: Source phase
            to_phase: Target phase
            trigger_reason: Reason for transition
            task_id: Task identifier
        """
        extra = {
            "event_type": "phase_transition",
            "from_phase": from_phase,
            "to_phase": to_phase,
            "trigger_reason": trigger_reason,
            "task_id": task_id,
            "curator_visibility": True,
        }

        self.logger.info(
            f"Phase transition: {from_phase} → {to_phase}", extra=extra
        )

    def log_hook_event(
        self,
        hook_event: str,
        hook_data: Dict[str, Any],
        permission_mode: PermissionMode,
    ) -> None:
        """
        Log a hook event (e.g., SubagentStop, ToolStart).

        Args:
            hook_event: Hook event type
            hook_data: Hook event data
            permission_mode: Current permission mode
        """
        extra = {
            "event_type": "hook_event",
            "hook_event": hook_event,
            "hook_data": hook_data,
            "permission_mode": permission_mode,
            "curator_visibility": True,
        }

        self.logger.info(f"Hook event: {hook_event}", extra=extra)

    def log_coverage_delta(
        self,
        task_id: str,
        before_branch: float,
        after_branch: float,
        before_lines: float,
        after_lines: float,
    ) -> None:
        """
        Log coverage changes.

        Args:
            task_id: Task identifier
            before_branch: Branch coverage before
            after_branch: Branch coverage after
            before_lines: Line coverage before
            after_lines: Line coverage after
        """
        extra = {
            "event_type": "coverage_delta",
            "task_id": task_id,
            "coverage_delta": {
                "branch": {
                    "before": before_branch,
                    "after": after_branch,
                    "delta": after_branch - before_branch,
                },
                "lines": {
                    "before": before_lines,
                    "after": after_lines,
                    "delta": after_lines - before_lines,
                },
            },
            "curator_visibility": True,
        }

        self.logger.info("Coverage delta calculated", extra=extra)

    def log_artifact(
        self,
        artifact_type: str,
        artifact_path: str,
        task_id: str,
        phase: str,
    ) -> None:
        """
        Log an artifact creation.

        Args:
            artifact_type: Type of artifact (test_report, implementation, etc.)
            artifact_path: Path to artifact file
            task_id: Task identifier
            phase: Phase that created artifact
        """
        extra = {
            "event_type": "artifact_created",
            "artifact_type": artifact_type,
            "artifact_path": artifact_path,
            "task_id": task_id,
            "phase": phase,
            "curator_visibility": True,
        }

        self.logger.info(f"Artifact created: {artifact_type}", extra=extra)

    @staticmethod
    def _redact_thinking(content: str) -> str:
        """
        Redact sensitive information from thinking tokens.

        Args:
            content: Raw thinking content

        Returns:
            Redacted content
        """
        redacted = content

        # Redact file paths
        redacted = re.sub(r"/[a-zA-Z0-9_/.-]+", "[PATH]", redacted)

        # Redact API keys and secrets
        redacted = re.sub(r"[a-zA-Z0-9_-]{20,}", "[REDACTED]", redacted)

        # Redact email addresses
        redacted = re.sub(r"\S+@\S+\.\S+", "[EMAIL]", redacted)

        # Truncate if too long
        max_length = 500
        if len(redacted) > max_length:
            redacted = redacted[:max_length] + "... [truncated]"

        return redacted

    @staticmethod
    def _truncate_stderr(content: str, max_lines: int = 20) -> str:
        """
        Truncate stderr content to reasonable size.

        Args:
            content: Raw stderr content
            max_lines: Maximum lines to include

        Returns:
            Truncated content
        """
        lines = content.split("\n")
        if len(lines) <= max_lines:
            return content

        # Take first and last lines
        half = max_lines // 2
        truncated_lines = (
            lines[:half]
            + [f"... [{len(lines) - max_lines} lines omitted] ..."]
            + lines[-half:]
        )

        return "\n".join(truncated_lines)


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logs.

    Formats log records as JSON with standardized fields for curator consumption.
    """

    def __init__(self, session_id: str):
        """
        Initialize the JSON formatter.

        Args:
            session_id: Session identifier to include in all logs
        """
        super().__init__()
        self.session_id = session_id

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as JSON.

        Args:
            record: Log record to format

        Returns:
            JSON-formatted log string
        """
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "session_id": self.session_id,
            "message": record.getMessage(),
        }

        # Add extra fields from record
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "created",
                    "filename",
                    "funcName",
                    "levelname",
                    "levelno",
                    "lineno",
                    "module",
                    "msecs",
                    "message",
                    "pathname",
                    "process",
                    "processName",
                    "relativeCreated",
                    "thread",
                    "threadName",
                ]:
                    log_data[key] = value

        return json.dumps(log_data)


# Module-level logger cache
_loggers: Dict[str, SkillsLoopLogger] = {}


def get_logger(
    session_id: str,
    log_file: Optional[Path] = None,
    log_level: str = "INFO",
) -> SkillsLoopLogger:
    """
    Get or create a skills loop logger.

    Args:
        session_id: Session identifier
        log_file: Optional log file path
        log_level: Logging level

    Returns:
        SkillsLoopLogger instance
    """
    if session_id not in _loggers:
        _loggers[session_id] = SkillsLoopLogger(
            session_id=session_id,
            log_file=log_file,
            log_level=log_level,
        )

    return _loggers[session_id]
