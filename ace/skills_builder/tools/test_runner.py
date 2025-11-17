"""
Test Runner for ACE Skills Loop

Executes pytest with coverage tracking and generates test artifacts
for curator review.
"""

import json
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ace.skills_builder.models import TestResult

logger = logging.getLogger(__name__)


class TestRunner:
    """
    Test runner for the Build/Test phase of the skills loop.

    Executes pytest with coverage tracking, enforces coverage thresholds,
    and generates JSON reports for curator consumption.
    """

    def __init__(
        self,
        coverage_thresholds: Optional[Dict[str, float]] = None,
        pytest_args: Optional[List[str]] = None,
    ):
        """
        Initialize the test runner.

        Args:
            coverage_thresholds: Required coverage ratios (branch, lines)
            pytest_args: Additional pytest arguments
        """
        self.coverage_thresholds = coverage_thresholds or {
            "branch": 0.8,
            "lines": 0.85,
        }
        self.pytest_args = pytest_args or []

    def run_tests(
        self,
        test_path: Optional[str] = None,
        dry_run: bool = False,
        output_dir: Optional[Path] = None,
    ) -> TestResult:
        """
        Run pytest with coverage tracking.

        Args:
            test_path: Path to test directory/file (None for all tests)
            dry_run: If True, skip actual test execution
            output_dir: Directory for test artifacts

        Returns:
            TestResult with execution details
        """
        if dry_run:
            return self._run_dry_run(test_path)

        output_dir = output_dir or Path("docs/transcripts/test_reports")
        output_dir.mkdir(parents=True, exist_ok=True)

        started_at = datetime.now()

        # Prepare pytest command
        cmd = self._build_pytest_command(test_path, output_dir)

        logger.info(f"Running tests: {' '.join(cmd)}")

        try:
            # Run pytest
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
            )

            # Parse results
            test_result = self._parse_pytest_output(
                result, output_dir, started_at
            )

            # Check coverage thresholds
            if test_result.passed:
                test_result.passed = self._check_coverage_thresholds(
                    test_result
                )

            return test_result

        except subprocess.TimeoutExpired:
            logger.error("Test execution timed out")
            return TestResult(
                test_mode="pytest",
                passed=False,
                stderr_summary="Test execution timed out after 600 seconds",
                duration_seconds=600,
            )

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return TestResult(
                test_mode="pytest",
                passed=False,
                stderr_summary=str(e),
                duration_seconds=(datetime.now() - started_at).total_seconds(),
            )

    def _build_pytest_command(
        self, test_path: Optional[str], output_dir: Path
    ) -> List[str]:
        """
        Build the pytest command with all arguments.

        Args:
            test_path: Path to tests
            output_dir: Output directory for reports

        Returns:
            Command as list of strings
        """
        json_report_path = output_dir / f"test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        cmd = [
            "python",
            "-m",
            "pytest",
            "-q",  # Quiet mode
            "--maxfail=1",  # Stop after first failure
            "--disable-warnings",  # Suppress warnings
            "--tb=short",  # Short traceback format
            f"--json-report",  # Enable JSON report
            f"--json-report-file={json_report_path}",
            "--cov=ace",  # Coverage for ace package
            "--cov-branch",  # Branch coverage
            "--cov-report=term",  # Terminal report
            f"--cov-report=json:{output_dir}/coverage.json",  # JSON coverage
        ]

        # Add custom pytest args
        cmd.extend(self.pytest_args)

        # Add test path if specified
        if test_path:
            cmd.append(test_path)
        else:
            cmd.append("tests/")

        return cmd

    def _parse_pytest_output(
        self,
        result: subprocess.CompletedProcess,
        output_dir: Path,
        started_at: datetime,
    ) -> TestResult:
        """
        Parse pytest output and coverage data.

        Args:
            result: Subprocess result from pytest
            output_dir: Output directory for reports
            started_at: Test start time

        Returns:
            TestResult with parsed data
        """
        duration = (datetime.now() - started_at).total_seconds()

        # Try to load JSON report
        json_report_path = self._find_latest_report(output_dir, "test_report_")
        coverage_json_path = output_dir / "coverage.json"

        total_tests = 0
        failed_tests = 0

        if json_report_path and json_report_path.exists():
            try:
                with open(json_report_path) as f:
                    report_data = json.load(f)
                    summary = report_data.get("summary", {})
                    total_tests = summary.get("total", 0)
                    failed_tests = summary.get("failed", 0)
            except Exception as e:
                logger.warning(f"Failed to parse JSON report: {e}")

        # Parse coverage
        coverage_branch = 0.0
        coverage_lines = 0.0

        if coverage_json_path.exists():
            try:
                with open(coverage_json_path) as f:
                    coverage_data = json.load(f)
                    totals = coverage_data.get("totals", {})

                    # Calculate coverage percentages
                    if totals.get("num_statements", 0) > 0:
                        coverage_lines = (
                            totals.get("covered_lines", 0)
                            / totals.get("num_statements", 1)
                        )

                    if totals.get("num_branches", 0) > 0:
                        coverage_branch = (
                            totals.get("covered_branches", 0)
                            / totals.get("num_branches", 1)
                        )
            except Exception as e:
                logger.warning(f"Failed to parse coverage data: {e}")

        # Determine if tests passed
        passed = result.returncode == 0 and failed_tests == 0

        # Extract stderr summary
        stderr_summary = None
        if not passed:
            stderr_lines = result.stderr.split("\n")
            # Take last 10 lines for summary
            stderr_summary = "\n".join(stderr_lines[-10:])

        return TestResult(
            test_mode="pytest",
            passed=passed,
            total_tests=total_tests,
            failed_tests=failed_tests,
            coverage_branch=coverage_branch,
            coverage_lines=coverage_lines,
            json_report_path=str(json_report_path) if json_report_path else None,
            stderr_summary=stderr_summary,
            duration_seconds=duration,
        )

    def _check_coverage_thresholds(self, test_result: TestResult) -> bool:
        """
        Check if coverage meets required thresholds.

        Args:
            test_result: Test result to check

        Returns:
            True if thresholds met, False otherwise
        """
        branch_threshold = self.coverage_thresholds.get("branch", 0.0)
        lines_threshold = self.coverage_thresholds.get("lines", 0.0)

        branch_ok = test_result.coverage_branch >= branch_threshold
        lines_ok = test_result.coverage_lines >= lines_threshold

        if not branch_ok:
            logger.warning(
                f"Branch coverage {test_result.coverage_branch:.2%} "
                f"below threshold {branch_threshold:.2%}"
            )

        if not lines_ok:
            logger.warning(
                f"Line coverage {test_result.coverage_lines:.2%} "
                f"below threshold {lines_threshold:.2%}"
            )

        return branch_ok and lines_ok

    def _run_dry_run(self, test_path: Optional[str]) -> TestResult:
        """
        Run a dry-run validation without executing tests.

        Args:
            test_path: Path to test directory/file

        Returns:
            TestResult for dry-run
        """
        logger.info("Running dry-run validation (no tests executed)")

        # Basic import check
        try:
            import ace  # noqa

            passed = True
            stderr_summary = None
        except ImportError as e:
            passed = False
            stderr_summary = f"Import validation failed: {e}"

        return TestResult(
            test_mode="dry_run",
            passed=passed,
            total_tests=0,
            failed_tests=0,
            stderr_summary=stderr_summary,
            duration_seconds=0.0,
        )

    @staticmethod
    def _find_latest_report(output_dir: Path, prefix: str) -> Optional[Path]:
        """
        Find the most recent report file with given prefix.

        Args:
            output_dir: Directory to search
            prefix: File name prefix

        Returns:
            Path to latest report or None
        """
        reports = list(output_dir.glob(f"{prefix}*.json"))
        if not reports:
            return None

        # Sort by modification time (most recent first)
        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return reports[0]


async def run_tests(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Tool function for running tests during skills loop.

    This is the entrypoint for the `run_tests` skill that gets registered
    with the skills runtime.

    Args:
        args: Tool arguments with optional keys:
            - test_path (str): Path to test directory/file
            - dry_run (bool): Whether to run dry-run validation
            - coverage_thresholds (dict): Custom coverage thresholds

    Returns:
        Tool result with test outcome
    """
    test_path = args.get("test_path")
    dry_run = args.get("dry_run", False)
    coverage_thresholds = args.get("coverage_thresholds")

    runner = TestRunner(coverage_thresholds=coverage_thresholds)
    result = runner.run_tests(test_path=test_path, dry_run=dry_run)

    # Format result for tool response
    if result.passed:
        summary = (
            f"✓ Tests passed: {result.total_tests} tests, "
            f"coverage: {result.coverage_lines:.1%} lines, "
            f"{result.coverage_branch:.1%} branches"
        )
    else:
        summary = (
            f"✗ Tests failed: {result.failed_tests}/{result.total_tests} failures"
        )
        if result.stderr_summary:
            summary += f"\n\nError summary:\n{result.stderr_summary}"

    content_blocks = [
        {
            "type": "text",
            "text": summary,
        }
    ]

    # Include link to JSON report if available
    if result.json_report_path:
        content_blocks.append(
            {
                "type": "text",
                "text": f"\nDetailed report: {result.json_report_path}",
            }
        )

    return {
        "content": content_blocks,
        "test_result": result.model_dump(),
    }
