"""
Closed Cycle Automation

Coordinates the Plan→Build→Test→Review→Document automation loop.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from ace.playbook import Playbook
from ace.skills_builder.models import (
    ClosedCycleSummary,
    PhaseTransition,
    SkillsLoopConfig,
    TestResult,
)
from ace.skills_builder.tools.test_runner import TestRunner

logger = logging.getLogger(__name__)


class ClosedCycleCoordinator:
    """
    Coordinates the automated Plan→Build→Test→Review→Document loop.

    Manages phase transitions, test execution, and artifact collection
    for curator review.
    """

    def __init__(
        self,
        config: SkillsLoopConfig,
        playbook: Playbook,
    ):
        """
        Initialize the closed cycle coordinator.

        Args:
            config: Skills loop configuration
            playbook: ACE playbook
        """
        self.config = config
        self.playbook = playbook
        self.test_runner = TestRunner(
            coverage_thresholds=config.coverage_thresholds
        )

        self.session_id: Optional[str] = None
        self.task_id: Optional[str] = None
        self.phase_transitions: List[PhaseTransition] = []
        self.test_results: List[TestResult] = []
        self.accepted_deltas: List[str] = []
        self.rejected_deltas: List[str] = []

    def start_cycle(
        self,
        session_id: str,
        task_id: str,
        objective: str,
    ) -> Dict[str, Any]:
        """
        Start a closed cycle automation run.

        Args:
            session_id: Session identifier
            task_id: Task identifier
            objective: High-level objective for planning

        Returns:
            Cycle metadata
        """
        self.session_id = session_id
        self.task_id = task_id

        logger.info(
            f"Starting closed cycle for task {task_id}: {objective[:100]}"
        )

        self._transition_phase("idle", "plan", "Starting closed cycle")

        return {
            "session_id": session_id,
            "task_id": task_id,
            "objective": objective,
            "phases": ["plan", "build", "test", "review", "document"],
        }

    def execute_plan_phase(self, objective: str) -> Dict[str, Any]:
        """
        Execute the Plan phase.

        Args:
            objective: Planning objective

        Returns:
            Plan phase result
        """
        logger.info("Executing Plan phase")

        # Stub: would use gpt-5 model for planning
        plan = {
            "objective": objective,
            "steps": [
                "Analyze playbook for relevant strategies",
                "Identify required tools",
                "Generate implementation plan",
            ],
            "estimated_duration": "5 minutes",
        }

        self._transition_phase("plan", "build", "Plan created successfully")

        return {"plan": plan, "phase": "plan"}

    def execute_build_phase(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the Build phase.

        Args:
            plan: Plan from previous phase

        Returns:
            Build phase result
        """
        logger.info("Executing Build phase")

        # Stub: would invoke tools and execute code edits
        build_artifacts = {
            "files_modified": [],
            "tools_invoked": [],
            "permission_mode": "acceptEdits",
        }

        self._transition_phase("build", "test", "Build completed")

        return {"artifacts": build_artifacts, "phase": "build"}

    def execute_test_phase(
        self,
        test_path: Optional[str] = None,
        dry_run: bool = False,
    ) -> TestResult:
        """
        Execute the Test phase.

        Args:
            test_path: Path to test directory/file
            dry_run: Whether to run dry-run validation

        Returns:
            Test result
        """
        logger.info("Executing Test phase")

        self._transition_phase("build", "test", "Running tests")

        test_result = self.test_runner.run_tests(
            test_path=test_path, dry_run=dry_run
        )

        self.test_results.append(test_result)

        if test_result.passed:
            self._transition_phase("test", "review", "Tests passed")
        else:
            self._transition_phase(
                "test",
                "build",
                f"Tests failed: {test_result.failed_tests} failures",
            )

        return test_result

    def execute_review_phase(
        self, build_artifacts: Dict[str, Any], test_result: TestResult
    ) -> Dict[str, Any]:
        """
        Execute the Review phase.

        Args:
            build_artifacts: Artifacts from build phase
            test_result: Test results

        Returns:
            Review phase result
        """
        logger.info("Executing Review phase")

        # Stub: would invoke Reflector/Curator
        review = {
            "test_passed": test_result.passed,
            "coverage_ok": (
                test_result.coverage_branch
                >= self.config.coverage_thresholds["branch"]
                and test_result.coverage_lines
                >= self.config.coverage_thresholds["lines"]
            ),
            "recommendation": "accept" if test_result.passed else "reject",
        }

        if review["recommendation"] == "accept":
            self.accepted_deltas.append(f"delta_{len(self.accepted_deltas) + 1}")
            self._transition_phase("review", "document", "Delta accepted")
        else:
            self.rejected_deltas.append(f"delta_{len(self.rejected_deltas) + 1}")
            self._transition_phase(
                "review", "build", "Delta rejected, retrying"
            )

        return {"review": review, "phase": "review"}

    def execute_document_phase(self) -> ClosedCycleSummary:
        """
        Execute the Document phase.

        Returns:
            Closed cycle summary
        """
        logger.info("Executing Document phase")

        self._transition_phase("review", "document", "Generating documentation")

        summary = self._generate_summary()

        self._transition_phase("document", "complete", "Cycle completed")

        return summary

    def _transition_phase(
        self,
        from_phase: str,
        to_phase: str,
        reason: str,
    ) -> None:
        """
        Record a phase transition.

        Args:
            from_phase: Current phase
            to_phase: Target phase
            reason: Transition reason
        """
        transition = PhaseTransition(
            from_phase=from_phase,  # type: ignore
            to_phase=to_phase,  # type: ignore
            timestamp=datetime.now(),
            session_id=self.session_id or "unknown",
            task_id=self.task_id or "unknown",
            trigger_reason=reason,
        )

        self.phase_transitions.append(transition)
        logger.debug(f"Phase transition: {from_phase} → {to_phase} ({reason})")

    def _generate_summary(self) -> ClosedCycleSummary:
        """
        Generate a closed cycle summary document.

        Returns:
            ClosedCycleSummary
        """
        # Collect artifact links
        artifact_links = {}

        for i, test_result in enumerate(self.test_results):
            if test_result.json_report_path:
                artifact_links[f"test_report_{i}"] = test_result.json_report_path

        # Generate markdown summary
        markdown_lines = [
            f"# Closed Cycle Summary",
            f"",
            f"**Session**: {self.session_id}",
            f"**Task**: {self.task_id}",
            f"**Completed**: {datetime.now().isoformat()}",
            f"",
            f"## Results",
            f"",
            f"- **Accepted Deltas**: {len(self.accepted_deltas)}",
            f"- **Rejected Deltas**: {len(self.rejected_deltas)}",
            f"- **Test Runs**: {len(self.test_results)}",
            f"",
        ]

        # Add test results
        if self.test_results:
            markdown_lines.extend(
                [
                    "## Test Results",
                    "",
                ]
            )

            for i, test_result in enumerate(self.test_results, 1):
                status = "✓ PASSED" if test_result.passed else "✗ FAILED"
                markdown_lines.extend(
                    [
                        f"### Test Run {i} - {status}",
                        f"",
                        f"- **Mode**: {test_result.test_mode}",
                        f"- **Total Tests**: {test_result.total_tests}",
                        f"- **Failed Tests**: {test_result.failed_tests}",
                        f"- **Branch Coverage**: {test_result.coverage_branch:.1%}",
                        f"- **Line Coverage**: {test_result.coverage_lines:.1%}",
                        f"- **Duration**: {test_result.duration_seconds:.1f}s",
                        f"",
                    ]
                )

                if test_result.json_report_path:
                    markdown_lines.append(
                        f"[View Report]({test_result.json_report_path})"
                    )
                    markdown_lines.append("")

        # Add phase transitions
        markdown_lines.extend(
            [
                "## Phase Timeline",
                "",
            ]
        )

        for transition in self.phase_transitions:
            markdown_lines.append(
                f"- **{transition.timestamp.strftime('%H:%M:%S')}**: "
                f"{transition.from_phase} → {transition.to_phase} "
                f"({transition.trigger_reason})"
            )

        markdown_summary = "\n".join(markdown_lines)

        # Extract permission modes used
        permission_modes = [
            self.config.session.permission_mode
        ]  # Would extract from actual execution

        summary = ClosedCycleSummary(
            session_id=self.session_id or "unknown",
            task_id=self.task_id or "unknown",
            completed_at=datetime.now(),
            accepted_deltas=self.accepted_deltas,
            rejected_deltas=self.rejected_deltas,
            test_results=self.test_results,
            permission_escalations=permission_modes,  # type: ignore
            artifact_links=artifact_links,
            markdown_summary=markdown_summary,
        )

        logger.info(
            f"Generated summary: {len(self.accepted_deltas)} accepted, "
            f"{len(self.rejected_deltas)} rejected"
        )

        return summary
