"""
Agent Runtime for ACE Skills Loop

Thin wrapper that receives task prompts and initializes the AgentsClient
plus skills runtime. This is the import target for runtime agents (Generator,
Reflector, Curator).

Usage:
    from ace.skills_builder.session_entrypoints.agent_runtime import (
        SkillsLoopRuntime,
        run_generator_with_skills,
        run_reflector_with_skills,
        run_curator_with_skills,
    )
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ace.playbook import Playbook
from ace.skills_builder.adapters import PlaybookAdapter, TrajectoryAdapter
from ace.skills_builder.models import (
    DeltaInput,
    PermissionMode,
    SkillsLoopConfig,
    SkillsSessionMetadata,
)
from ace.skills_builder.registry import AceSkillRegistry
from ace.skills_builder.runtimes import SkillsRuntimeFactory

logger = logging.getLogger(__name__)


class SkillsLoopRuntime:
    """
    Runtime coordinator for ACE skills loop sessions.

    Initializes skills registry, adapters, and provides convenience methods
    for Generator/Reflector/Curator roles to invoke skills-enhanced tasks.
    """

    def __init__(
        self,
        config: SkillsLoopConfig,
        playbook: Optional[Playbook] = None,
    ):
        """
        Initialize the skills loop runtime.

        Args:
            config: Skills loop configuration
            playbook: Optional ACE playbook for context
        """
        self.config = config
        self.playbook = playbook

        # Initialize components
        self.registry = AceSkillRegistry(config)
        self.runtime_factory = SkillsRuntimeFactory(self.registry)

        # Initialize adapters
        self.playbook_adapter = (
            PlaybookAdapter(playbook) if playbook else None
        )
        self.trajectory_adapter = TrajectoryAdapter()

        logger.info(
            f"Skills loop runtime initialized with "
            f"{len(self.registry.list_skills())} skills"
        )

    def prepare_system_prompt(
        self,
        role: str,
        max_bullets: Optional[int] = None,
    ) -> str:
        """
        Prepare a system prompt with playbook context for an ACE role.

        Args:
            role: ACE role (generator, reflector, curator)
            max_bullets: Maximum playbook bullets to include

        Returns:
            System prompt string
        """
        if not self.playbook_adapter:
            return f"You are the ACE {role}."

        playbook_context = self.playbook_adapter.to_system_prompt(
            max_bullets=max_bullets
        )

        role_prompts = {
            "generator": (
                "You are the ACE Generator. Your role is to produce answers "
                "using the current playbook strategies. Use the skills available "
                "to you to enhance your responses."
            ),
            "reflector": (
                "You are the ACE Reflector. Your role is to analyze task outcomes "
                "and classify which playbook strategies were helpful or harmful. "
                "Use analysis tools to review skill outcomes."
            ),
            "curator": (
                "You are the ACE Curator. Your role is to emit delta operations "
                "to update the playbook based on reflector feedback. Use curation "
                "tools to manage playbook evolution."
            ),
        }

        role_prompt = role_prompts.get(role, f"You are the ACE {role}.")

        return f"{role_prompt}\n\n{playbook_context}"

    def get_tool_bindings(self) -> List[Dict[str, Any]]:
        """
        Get tool bindings for the current session.

        Returns:
            List of tool definitions
        """
        return self.runtime_factory.create_tool_bindings(self.playbook)

    def get_session_metadata(self) -> Dict[str, Any]:
        """
        Get session metadata including skills and configuration.

        Returns:
            Session metadata dictionary
        """
        return {
            "skills_enabled": self.config.enabled,
            "registered_skills": [s.name for s in self.registry.list_skills()],
            "permission_mode": self.config.session.permission_mode,
            "model": self.config.session.model,
            "closed_cycle": self.config.skills_loop_closed_cycle,
            "playbook_bullets": (
                len(self.playbook.bullets) if self.playbook else 0
            ),
        }

    @classmethod
    def from_config_file(
        cls,
        config_path: Path,
        playbook: Optional[Playbook] = None,
    ) -> "SkillsLoopRuntime":
        """
        Create runtime from a configuration file.

        Args:
            config_path: Path to skills loop config
            playbook: Optional ACE playbook

        Returns:
            Initialized SkillsLoopRuntime
        """
        registry = AceSkillRegistry.from_config_file(config_path)
        return cls(registry.config, playbook)


async def run_generator_with_skills(
    prompt: str,
    playbook: Playbook,
    config: SkillsLoopConfig,
    max_bullets: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the ACE Generator with skills loop integration.

    Args:
        prompt: Task prompt for generation
        playbook: Current ACE playbook
        config: Skills loop configuration
        max_bullets: Maximum playbook bullets to include

    Returns:
        Generator result with trajectory
    """
    runtime = SkillsLoopRuntime(config, playbook)

    system_prompt = runtime.prepare_system_prompt(
        "generator", max_bullets=max_bullets
    )

    logger.info(f"Running generator with {len(runtime.get_tool_bindings())} tools")

    # Note: Actual SDK integration would use AgentsClient here
    # This is a stub showing the interface

    result = {
        "answer": "Generated answer (stub)",
        "system_prompt": system_prompt,
        "tools_available": [t["name"] for t in runtime.get_tool_bindings()],
        "session_metadata": runtime.get_session_metadata(),
    }

    return result


async def run_reflector_with_skills(
    task_result: Dict[str, Any],
    feedback: str,
    playbook: Playbook,
    config: SkillsLoopConfig,
) -> Dict[str, Any]:
    """
    Run the ACE Reflector with skills loop integration.

    Args:
        task_result: Generator task result
        feedback: Environment feedback
        playbook: Current ACE playbook
        config: Skills loop configuration

    Returns:
        Reflector analysis with bullet classifications
    """
    runtime = SkillsLoopRuntime(config, playbook)

    system_prompt = runtime.prepare_system_prompt("reflector")

    logger.info("Running reflector with analysis tools")

    # Note: Actual SDK integration would use AgentsClient here

    result = {
        "helpful_bullets": [],
        "harmful_bullets": [],
        "system_prompt": system_prompt,
        "tools_available": [t["name"] for t in runtime.get_tool_bindings()],
        "session_metadata": runtime.get_session_metadata(),
    }

    return result


async def run_curator_with_skills(
    reflector_result: Dict[str, Any],
    playbook: Playbook,
    config: SkillsLoopConfig,
) -> Dict[str, Any]:
    """
    Run the ACE Curator with skills loop integration.

    Args:
        reflector_result: Reflector analysis
        playbook: Current ACE playbook
        config: Skills loop configuration

    Returns:
        Curator delta operations
    """
    runtime = SkillsLoopRuntime(config, playbook)

    system_prompt = runtime.prepare_system_prompt("curator")

    logger.info("Running curator with delta tools")

    # Note: Actual SDK integration would use AgentsClient here

    result = {
        "delta_operations": [],
        "system_prompt": system_prompt,
        "tools_available": [t["name"] for t in runtime.get_tool_bindings()],
        "session_metadata": runtime.get_session_metadata(),
    }

    return result
