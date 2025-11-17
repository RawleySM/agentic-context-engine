"""
Pydantic data models for ACE Skills Loop

These typed schemas provide the contracts for skills loop configuration,
session management, and transcript capture. All models inherit from
pydantic.BaseModel and forbid extra fields to guard against drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# Type aliases
PermissionMode = Literal["plan", "acceptEdits", "bypassPermissions"]


class SkillDescriptor(BaseModel):
    """
    Metadata for a registered skill.

    Skills are tools exposed to the ACE agents during the skills loop,
    providing access to ACE utilities like playbook diffing and context fetching.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Unique skill slug used by slash commands.")
    version: str = Field(description="Semver string tracked in the registry.")
    description: str = Field(description="Human-readable summary of the skill.")
    entrypoint: str = Field(
        description="Dotted path to the callable bound by @tool."
    )
    allowed_tools: list[str] = Field(
        default_factory=list,
        description="Subset of tools exposed by the skills runtime.",
    )


class AgentSessionConfig(BaseModel):
    """
    Configuration for a codex exec agent session.

    Controls the model selection, tool availability, and permission mode
    for ACE's interaction with the Claude Code SDK.
    """

    model_config = ConfigDict(extra="forbid")

    model: Literal["gpt-5", "gpt-4o"] = Field(
        default="gpt-5",
        description="Reasoning model for non-coding phases.",
    )
    codex_tools_enabled: bool = Field(
        default=True,
        description="Whether Codex Exec-backed tools are permitted.",
    )
    permission_mode: PermissionMode = Field(
        default="plan",
        description="SDK permission level.",
    )
    fork_session: bool = Field(
        default=False,
        description="Enable trajectory branching for experiments.",
    )


class SkillOutcome(BaseModel):
    """
    Result of a skill invocation captured during the skills loop.

    Tracks execution metadata, artifacts, and permission context for
    curator review and playbook delta generation.
    """

    model_config = ConfigDict(extra="forbid")

    skill_name: str
    started_at: datetime
    finished_at: datetime
    result_summary: str
    permission_mode: PermissionMode
    stderr_present: bool
    artifact_paths: list[str] = Field(default_factory=list)


class TranscriptEvent(BaseModel):
    """
    Single event in a skills loop transcript.

    Captures SDK messages, tool invocations, slash commands, and subagent
    activity for replay and curator analysis.
    """

    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "assistant_message",
        "user_message",
        "tool_use_block",
        "tool_result_block",
        "slash_command",
        "subagent_stop",
    ]
    timestamp: datetime
    session_id: str
    task_id: str
    payload: dict[str, Any]
    thinking_snippet: Optional[str] = Field(
        default=None,
        description="Redacted thinking tokens when available.",
    )


class SlashCommandConfig(BaseModel):
    """
    Configuration for a custom ACE slash command.

    Defines the command metadata, argument schema, and permission requirements
    for codex exec registration.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Command name without leading slash.")
    description: str = Field(description="Human-readable command description.")
    args_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON schema for command arguments.",
    )
    permission_mode: PermissionMode = Field(
        default="plan",
        description="Required permission level for execution.",
    )
    default_visibility: bool = Field(
        default=True,
        description="Whether command appears in default listings.",
    )


class SkillsLoopConfig(BaseModel):
    """
    Top-level configuration for the ACE skills loop.

    Single source of truth for adapter wiring, CLI flag parsing,
    and inspector validation.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(
        default=False,
        description="Feature flag for the skills loop.",
    )
    registry: list[SkillDescriptor] = Field(
        default_factory=list,
        description="Registered skills available to agents.",
    )
    session: AgentSessionConfig = Field(
        default_factory=AgentSessionConfig,
        description="Session configuration for codex exec.",
    )
    hook_logging: bool = Field(
        default=True,
        description="Whether to persist hook events to JSONL transcripts.",
    )
    coverage_thresholds: dict[str, float] = Field(
        default_factory=lambda: {"branch": 0.8, "lines": 0.85},
        description="Required coverage ratios for automated tests.",
    )
    custom_commands: list[SlashCommandConfig] = Field(
        default_factory=list,
        description="Custom slash commands for ACE agents.",
    )
    skills_loop_closed_cycle: bool = Field(
        default=False,
        description="Enable automated Plan→Build→Test→Review→Document loop.",
    )


class TestResult(BaseModel):
    """
    Result of a test execution during the Build/Test phase.

    Captures pytest output, coverage metrics, and artifact paths for
    curator decision-making.
    """

    model_config = ConfigDict(extra="forbid")

    test_mode: Literal["pytest", "dry_run"] = Field(
        description="Type of test execution performed."
    )
    passed: bool = Field(description="Whether all tests passed.")
    total_tests: int = Field(default=0)
    failed_tests: int = Field(default=0)
    coverage_branch: float = Field(default=0.0, ge=0.0, le=1.0)
    coverage_lines: float = Field(default=0.0, ge=0.0, le=1.0)
    json_report_path: Optional[str] = Field(
        default=None,
        description="Path to pytest JSON report.",
    )
    stderr_summary: Optional[str] = Field(
        default=None,
        description="Truncated stderr for failures.",
    )
    duration_seconds: float = Field(default=0.0, ge=0.0)


class PhaseTransition(BaseModel):
    """
    Marks a transition between development loop phases.

    Used in transcript to track Plan→Build→Test→Review→Document flow.
    """

    model_config = ConfigDict(extra="forbid")

    from_phase: Literal["idle", "plan", "build", "test", "review", "document"]
    to_phase: Literal["plan", "build", "test", "review", "document", "complete"]
    timestamp: datetime
    session_id: str
    task_id: str
    retry_count: int = Field(default=0, ge=0)
    trigger_reason: Optional[str] = Field(
        default=None,
        description="Explanation for phase transition.",
    )


class DeltaInput(BaseModel):
    """
    Input to the skills loop from the curator.

    Represents a pending delta or playbook gap that needs skill-based
    implementation.
    """

    model_config = ConfigDict(extra="forbid")

    delta_id: str = Field(description="Unique identifier for this delta.")
    rationale: str = Field(
        description="Curator's explanation for this delta."
    )
    playbook_section: str = Field(
        description="Playbook section targeted by this delta."
    )
    source: Literal["delta", "gap", "manual"] = Field(
        description="Origin of this delta input."
    )


class TaskStub(BaseModel):
    """
    Lightweight task record created during skills loop entry.

    Links delta inputs to their corresponding SDK session for traceability.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: str
    session_id: str
    delta_input: Optional[DeltaInput] = None
    created_at: datetime
    source: Literal["delta", "command", "manual"]


class SkillsSessionMetadata(BaseModel):
    """
    Metadata captured at skills session start.

    Stores server info, allowed tools, and session configuration for
    transcript replay.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    started_at: datetime
    server_version: Optional[str] = None
    available_slash_commands: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    agent_definitions: list[str] = Field(
        default_factory=list,
        description="Names of registered subagents.",
    )
    permission_mode: PermissionMode
    model: str


class ClosedCycleSummary(BaseModel):
    """
    Summary document generated after Plan→Build→Test→Review→Document loop.

    Exported to docs/ for auditability and release notes.
    """

    model_config = ConfigDict(extra="forbid")

    session_id: str
    task_id: str
    completed_at: datetime
    accepted_deltas: list[str] = Field(
        default_factory=list,
        description="IDs of deltas accepted by curator.",
    )
    rejected_deltas: list[str] = Field(
        default_factory=list,
        description="IDs of deltas rejected by curator.",
    )
    test_results: list[TestResult] = Field(default_factory=list)
    permission_escalations: list[PermissionMode] = Field(
        default_factory=list,
        description="Permission modes used during loop.",
    )
    artifact_links: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of artifact types to file paths.",
    )
    markdown_summary: str = Field(
        description="Human-readable summary for documentation."
    )
