"""
Skills Runtime Factory

Creates and configures skill runtimes for codex exec integration.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

from ace.playbook import Playbook
from ace.skills_builder.models import SkillsLoopConfig
from ace.skills_builder.registry import AceSkillRegistry

logger = logging.getLogger(__name__)


class SkillsRuntimeFactory:
    """
    Factory for creating skill runtimes with tool bindings.

    Wraps registered skills with codex exec tool decorators and provides
    them to AgentOptions for session initialization.
    """

    def __init__(self, registry: AceSkillRegistry):
        """
        Initialize the runtime factory.

        Args:
            registry: Skill registry with registered skills
        """
        self.registry = registry

    def create_tool_bindings(
        self, playbook: Optional[Playbook] = None
    ) -> List[Dict[str, Any]]:
        """
        Create tool bindings for all registered skills.

        Args:
            playbook: Optional ACE playbook for context injection

        Returns:
            List of tool definitions ready for AgentOptions.tools

        Note:
            This returns a simplified tool definition format.
            Actual codex exec integration would use the @tool decorator.
        """
        tools = []

        for skill in self.registry.list_skills():
            try:
                tool_callable = self.registry.get_tool_callable(skill.name)

                # Create tool definition
                tool_def = {
                    "name": skill.name,
                    "description": skill.description,
                    "version": skill.version,
                    "callable": tool_callable,
                    "allowed_tools": skill.allowed_tools,
                }

                # If playbook provided, inject as context
                if playbook is not None:
                    tool_def["playbook_context"] = self._serialize_playbook(
                        playbook
                    )

                tools.append(tool_def)
                logger.debug(f"Created tool binding for skill: {skill.name}")

            except Exception as e:
                logger.error(
                    f"Failed to create tool binding for {skill.name}: {e}"
                )

        logger.info(f"Created {len(tools)} tool bindings")
        return tools

    def get_allowed_tool_names(self) -> List[str]:
        """
        Get list of all allowed tool names from registered skills.

        Returns:
            List of tool names
        """
        all_tools = set()

        for skill in self.registry.list_skills():
            all_tools.add(skill.name)
            all_tools.update(skill.allowed_tools)

        return sorted(all_tools)

    @staticmethod
    def _serialize_playbook(playbook: Playbook) -> Dict[str, Any]:
        """
        Serialize playbook to dict for tool context injection.

        Args:
            playbook: ACE playbook

        Returns:
            Serialized playbook data
        """
        bullets_data = []
        for bullet in playbook.bullets:
            bullets_data.append(
                {
                    "strategy": bullet.strategy,
                    "helpful_count": bullet.helpful_count,
                    "harmful_count": bullet.harmful_count,
                    "tags": list(bullet.tags),
                }
            )

        return {
            "bullets": bullets_data,
            "total_bullets": len(playbook.bullets),
        }


def create_skills_runtime(
    config: SkillsLoopConfig,
    playbook: Optional[Playbook] = None,
) -> SkillsRuntimeFactory:
    """
    Convenience function to create a skills runtime.

    Args:
        config: Skills loop configuration
        playbook: Optional ACE playbook for context

    Returns:
        Configured SkillsRuntimeFactory
    """
    registry = AceSkillRegistry(config)
    factory = SkillsRuntimeFactory(registry)

    # Pre-create tool bindings if playbook provided
    if playbook is not None:
        tools = factory.create_tool_bindings(playbook)
        logger.info(
            f"Skills runtime initialized with {len(tools)} tools "
            f"and playbook context ({len(playbook.bullets)} bullets)"
        )
    else:
        logger.info("Skills runtime initialized without playbook context")

    return factory
