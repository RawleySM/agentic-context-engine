"""
ACE Integration with Claude Code SDK (codex exec)

This module provides the integration layer between ACE's Generator/Reflector/Curator
roles and the Claude Code SDK (codex exec) to enable skills-based development loops.

Key Features:
- Wraps AgentsClient for ACE-compatible session management
- Converts SDK messages to ACE trajectory entries
- Manages skills registration and tool invocation tracking
- Supports Plan→Build→Test→Review→Document automation loop
- Captures JSONL transcripts for inspector replay

Note: This is a stub implementation that provides the interface contract.
The actual AgentsClient integration requires the Claude Code SDK to be available.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field

from ace.playbook import Playbook
from ace.skills_builder.models import (
    AgentSessionConfig,
    DeltaInput,
    PermissionMode,
    PhaseTransition,
    SkillOutcome,
    SkillsLoopConfig,
    SkillsSessionMetadata,
    TaskStub,
    TestResult,
    TranscriptEvent,
)

logger = logging.getLogger(__name__)


class TaskTrajectory(BaseModel):
    """
    ACE trajectory captured during a skills loop session.

    Contains all assistant reasoning, tool invocations, and skill outcomes
    for reflector/curator analysis.
    """

    task_id: str
    session_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    events: List[TranscriptEvent] = Field(default_factory=list)
    skill_outcomes: List[SkillOutcome] = Field(default_factory=list)
    test_results: List[TestResult] = Field(default_factory=list)
    phase_transitions: List[PhaseTransition] = Field(default_factory=list)
    final_result: Optional[str] = None


class CodexExecAdapter:
    """
    Adapter for integrating ACE with Claude Code SDK.

    Provides async methods for session management, task execution,
    and transcript capture.

    Note: This is a stub implementation. Actual SDK integration requires
    the Claude Code SDK (codex exec) to be installed and configured.
    """

    def __init__(
        self,
        config: SkillsLoopConfig,
        transcript_dir: Optional[Path] = None,
    ):
        """
        Initialize the codex exec adapter.

        Args:
            config: Skills loop configuration
            transcript_dir: Directory for JSONL transcript storage
        """
        self.config = config
        self.transcript_dir = transcript_dir or Path("docs/transcripts")
        self.transcript_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"CodexExecAdapter initialized with {len(config.registry)} skills"
        )

    async def run_task(
        self,
        prompt: str,
        playbook: Playbook,
        task_id: Optional[str] = None,
    ) -> TaskTrajectory:
        """
        Run a single task using the codex exec session.

        Args:
            prompt: Task prompt for the generator
            playbook: Current ACE playbook context
            task_id: Optional task identifier

        Returns:
            TaskTrajectory containing all events and outcomes
        """
        task_id = task_id or self._generate_task_id()
        session_id = self._generate_session_id()

        trajectory = TaskTrajectory(
            task_id=task_id,
            session_id=session_id,
            started_at=datetime.now(),
        )

        logger.info(f"Starting task {task_id} in session {session_id}")

        try:
            # Note: Actual SDK integration would happen here
            # For now, this is a stub that demonstrates the interface

            # Step 1: Initialize session with playbook context
            await self._initialize_session(session_id, playbook)

            # Step 2: Execute task prompt
            async for event in self._execute_task(prompt, session_id, task_id):
                trajectory.events.append(event)

            # Step 3: Finalize trajectory
            trajectory.finished_at = datetime.now()

            # Step 4: Write transcript
            if self.config.hook_logging:
                await self._write_transcript(trajectory)

            logger.info(
                f"Task {task_id} completed with {len(trajectory.events)} events"
            )

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            trajectory.finished_at = datetime.now()
            trajectory.final_result = f"ERROR: {e}"

        return trajectory

    async def run_closed_cycle_task(
        self,
        prompt: str,
        playbook: Playbook,
        task_id: Optional[str] = None,
    ) -> TaskTrajectory:
        """
        Run a task through the full Plan→Build→Test→Review→Document loop.

        Args:
            prompt: High-level objective for planning
            playbook: Current ACE playbook
            task_id: Optional task identifier

        Returns:
            TaskTrajectory with phase-tagged entries
        """
        if not self.config.skills_loop_closed_cycle:
            raise ValueError("Closed cycle not enabled in configuration")

        task_id = task_id or self._generate_task_id()
        session_id = self._generate_session_id()

        trajectory = TaskTrajectory(
            task_id=task_id,
            session_id=session_id,
            started_at=datetime.now(),
        )

        logger.info(
            f"Starting closed cycle for task {task_id} in session {session_id}"
        )

        try:
            # Phase 1: Plan
            await self._run_plan_phase(
                prompt, playbook, trajectory, session_id, task_id
            )

            # Phase 2: Build
            await self._run_build_phase(trajectory, session_id, task_id)

            # Phase 3: Test
            test_result = await self._run_test_phase(
                trajectory, session_id, task_id
            )
            trajectory.test_results.append(test_result)

            # Phase 4: Review (only if tests passed)
            if test_result.passed:
                await self._run_review_phase(trajectory, session_id, task_id)
            else:
                logger.warning("Tests failed, skipping review phase")

            # Phase 5: Document
            await self._run_document_phase(trajectory, session_id, task_id)

            trajectory.finished_at = datetime.now()

            # Write transcript
            if self.config.hook_logging:
                await self._write_transcript(trajectory)

            logger.info(f"Closed cycle for task {task_id} completed")

        except Exception as e:
            logger.error(f"Closed cycle for task {task_id} failed: {e}")
            trajectory.finished_at = datetime.now()
            trajectory.final_result = f"ERROR: {e}"

        return trajectory

    async def fetch_server_commands(
        self, session_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch available slash commands from codex exec server.

        Args:
            session_id: Active session identifier

        Returns:
            List of command descriptors
        """
        # Note: Actual SDK integration would call get_server_info() here
        logger.info(f"Fetching server commands for session {session_id}")
        return []

    def enter_skill_loop(
        self,
        delta_input: Optional[DeltaInput] = None,
    ) -> SkillsSessionMetadata:
        """
        Enter the skills loop and capture session metadata.

        Args:
            delta_input: Optional delta to target during skills session

        Returns:
            Session metadata including available tools and commands
        """
        session_id = self._generate_session_id()

        metadata = SkillsSessionMetadata(
            session_id=session_id,
            started_at=datetime.now(),
            permission_mode=self.config.session.permission_mode,
            model=self.config.session.model,
        )

        logger.info(f"Entered skills loop with session {session_id}")

        # Note: Actual SDK integration would call get_server_info() here
        # and populate available_slash_commands, available_tools, etc.

        return metadata

    # Private helper methods

    def _generate_task_id(self) -> str:
        """Generate a unique task identifier."""
        return f"task_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    def _generate_session_id(self) -> str:
        """Generate a unique session identifier."""
        return f"session_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    async def _initialize_session(
        self, session_id: str, playbook: Playbook
    ) -> None:
        """Initialize a codex exec session with playbook context."""
        logger.debug(f"Initializing session {session_id} with playbook")
        # Stub: would initialize AgentsClient here

    async def _execute_task(
        self, prompt: str, session_id: str, task_id: str
    ) -> AsyncIterator[TranscriptEvent]:
        """Execute a task prompt and yield transcript events."""
        logger.debug(f"Executing task {task_id} with prompt: {prompt[:100]}...")

        # Stub: would call AgentsClient.query() and stream events
        # For now, yield a placeholder event
        yield TranscriptEvent(
            event_type="assistant_message",
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
            payload={"content": "Stub implementation - SDK not available"},
        )

    async def _run_plan_phase(
        self,
        prompt: str,
        playbook: Playbook,
        trajectory: TaskTrajectory,
        session_id: str,
        task_id: str,
    ) -> None:
        """Execute the Plan phase of the closed cycle."""
        transition = PhaseTransition(
            from_phase="idle",
            to_phase="plan",
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
            trigger_reason="Starting closed cycle",
        )
        trajectory.phase_transitions.append(transition)

        logger.info(f"Plan phase for task {task_id}")
        # Stub: would use gpt-5 model to synthesize plan

    async def _run_build_phase(
        self, trajectory: TaskTrajectory, session_id: str, task_id: str
    ) -> None:
        """Execute the Build phase."""
        transition = PhaseTransition(
            from_phase="plan",
            to_phase="build",
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
        )
        trajectory.phase_transitions.append(transition)

        logger.info(f"Build phase for task {task_id}")
        # Stub: would invoke tools and execute code edits

    async def _run_test_phase(
        self, trajectory: TaskTrajectory, session_id: str, task_id: str
    ) -> TestResult:
        """Execute the Test phase and return results."""
        transition = PhaseTransition(
            from_phase="build",
            to_phase="test",
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
        )
        trajectory.phase_transitions.append(transition)

        logger.info(f"Test phase for task {task_id}")

        # Stub: would run pytest and capture coverage
        return TestResult(
            test_mode="dry_run",
            passed=True,
            total_tests=0,
            failed_tests=0,
        )

    async def _run_review_phase(
        self, trajectory: TaskTrajectory, session_id: str, task_id: str
    ) -> None:
        """Execute the Review phase."""
        transition = PhaseTransition(
            from_phase="test",
            to_phase="review",
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
        )
        trajectory.phase_transitions.append(transition)

        logger.info(f"Review phase for task {task_id}")
        # Stub: would invoke Reflector/Curator

    async def _run_document_phase(
        self, trajectory: TaskTrajectory, session_id: str, task_id: str
    ) -> None:
        """Execute the Document phase."""
        transition = PhaseTransition(
            from_phase="review",
            to_phase="document",
            timestamp=datetime.now(),
            session_id=session_id,
            task_id=task_id,
        )
        trajectory.phase_transitions.append(transition)

        logger.info(f"Document phase for task {task_id}")
        # Stub: would generate summary with gpt-5

    async def _write_transcript(self, trajectory: TaskTrajectory) -> None:
        """Write trajectory to JSONL transcript file."""
        transcript_path = (
            self.transcript_dir
            / f"{trajectory.started_at.strftime('%Y-%m-%d')}_{trajectory.task_id}.jsonl"
        )

        with open(transcript_path, "w") as f:
            # Write session header
            header = {
                "type": "session_header",
                "task_id": trajectory.task_id,
                "session_id": trajectory.session_id,
                "started_at": trajectory.started_at.isoformat(),
            }
            f.write(json.dumps(header) + "\n")

            # Write all events
            for event in trajectory.events:
                f.write(event.model_dump_json() + "\n")

            # Write phase transitions
            for transition in trajectory.phase_transitions:
                f.write(transition.model_dump_json() + "\n")

            # Write footer
            footer = {
                "type": "session_footer",
                "task_id": trajectory.task_id,
                "finished_at": (
                    trajectory.finished_at.isoformat()
                    if trajectory.finished_at
                    else None
                ),
                "total_events": len(trajectory.events),
            }
            f.write(json.dumps(footer) + "\n")

        logger.info(f"Transcript written to {transcript_path}")


# Convenience functions


async def run_task(
    prompt: str,
    playbook: Playbook,
    skills_config: SkillsLoopConfig,
) -> TaskTrajectory:
    """
    Convenience function to run a task with codex exec.

    Args:
        prompt: Task prompt
        playbook: ACE playbook
        skills_config: Skills loop configuration

    Returns:
        TaskTrajectory with execution results
    """
    adapter = CodexExecAdapter(skills_config)
    return await adapter.run_task(prompt, playbook)


async def run_closed_cycle_task(
    prompt: str,
    playbook: Playbook,
    skills_config: SkillsLoopConfig,
) -> TaskTrajectory:
    """
    Convenience function to run a closed cycle task.

    Args:
        prompt: High-level objective
        playbook: ACE playbook
        skills_config: Skills loop configuration

    Returns:
        TaskTrajectory with all phases completed
    """
    adapter = CodexExecAdapter(skills_config)
    return await adapter.run_closed_cycle_task(prompt, playbook)


def enter_skill_loop(
    skills_config: SkillsLoopConfig,
    delta_input: Optional[DeltaInput] = None,
) -> SkillsSessionMetadata:
    """
    Convenience function to enter skills loop.

    Args:
        skills_config: Skills loop configuration
        delta_input: Optional delta to target

    Returns:
        Session metadata
    """
    adapter = CodexExecAdapter(skills_config)
    return adapter.enter_skill_loop(delta_input)
