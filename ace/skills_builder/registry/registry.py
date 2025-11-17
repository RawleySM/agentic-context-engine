"""
ACE Skill Registry

Central registry for managing ACE skills, their metadata, and tool bindings.
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import ValidationError

from ace.skills_builder.models import SkillDescriptor, SkillsLoopConfig

logger = logging.getLogger(__name__)


class SkillNotFoundError(Exception):
    """Raised when a requested skill is not registered."""

    pass


class AceSkillRegistry:
    """
    Registry for ACE skills.

    Manages skill descriptors, tool bindings, and runtime lookup.
    Validates skill configurations and provides safe access to skill callables.
    """

    def __init__(self, config: Optional[SkillsLoopConfig] = None):
        """
        Initialize the skill registry.

        Args:
            config: Optional skills loop configuration
        """
        self.config = config or SkillsLoopConfig()
        self._skills: Dict[str, SkillDescriptor] = {}
        self._tool_bindings: Dict[str, Callable] = {}

        # Register skills from config
        for skill in self.config.registry:
            self.register_skill(skill)

        logger.info(f"Initialized registry with {len(self._skills)} skills")

    def register_skill(self, descriptor: SkillDescriptor) -> None:
        """
        Register a skill with the registry.

        Args:
            descriptor: Skill descriptor with metadata

        Raises:
            ValueError: If skill name is already registered
            ImportError: If skill entrypoint cannot be loaded
        """
        if descriptor.name in self._skills:
            raise ValueError(f"Skill '{descriptor.name}' already registered")

        # Validate entrypoint can be imported
        try:
            tool_callable = self._load_entrypoint(descriptor.entrypoint)
            self._tool_bindings[descriptor.name] = tool_callable
        except Exception as e:
            logger.error(
                f"Failed to load skill '{descriptor.name}' from "
                f"'{descriptor.entrypoint}': {e}"
            )
            raise ImportError(
                f"Cannot load skill entrypoint: {descriptor.entrypoint}"
            ) from e

        self._skills[descriptor.name] = descriptor
        logger.info(f"Registered skill: {descriptor.name} v{descriptor.version}")

    def get_skill(self, name: str) -> SkillDescriptor:
        """
        Get a skill descriptor by name.

        Args:
            name: Skill name

        Returns:
            SkillDescriptor

        Raises:
            SkillNotFoundError: If skill is not registered
        """
        if name not in self._skills:
            raise SkillNotFoundError(
                f"Skill '{name}' not found. "
                f"Available skills: {list(self._skills.keys())}"
            )
        return self._skills[name]

    def get_tool_callable(self, name: str) -> Callable:
        """
        Get the callable tool for a skill.

        Args:
            name: Skill name

        Returns:
            Callable tool function

        Raises:
            SkillNotFoundError: If skill is not registered
        """
        if name not in self._tool_bindings:
            raise SkillNotFoundError(f"No tool binding for skill '{name}'")
        return self._tool_bindings[name]

    def list_skills(self) -> List[SkillDescriptor]:
        """
        List all registered skills.

        Returns:
            List of skill descriptors
        """
        return list(self._skills.values())

    def get_allowed_tools_for_skill(self, name: str) -> List[str]:
        """
        Get the allowed tools for a specific skill.

        Args:
            name: Skill name

        Returns:
            List of allowed tool names

        Raises:
            SkillNotFoundError: If skill is not registered
        """
        skill = self.get_skill(name)
        return skill.allowed_tools

    def validate_skill_config(
        self, descriptor: SkillDescriptor
    ) -> List[str]:
        """
        Validate a skill descriptor configuration.

        Args:
            descriptor: Skill descriptor to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check entrypoint format
        if "." not in descriptor.entrypoint:
            errors.append(
                f"Invalid entrypoint format: {descriptor.entrypoint}. "
                "Expected 'module.path:function'"
            )

        # Check version format (basic semver check)
        version_parts = descriptor.version.split(".")
        if len(version_parts) != 3:
            errors.append(
                f"Invalid version format: {descriptor.version}. "
                "Expected semver (e.g., 1.0.0)"
            )

        # Check name is valid identifier
        if not descriptor.name.replace("_", "").replace("-", "").isalnum():
            errors.append(
                f"Invalid skill name: {descriptor.name}. "
                "Must be alphanumeric with underscores/hyphens"
            )

        return errors

    @staticmethod
    def _load_entrypoint(entrypoint: str) -> Callable:
        """
        Load a skill callable from its entrypoint string.

        Args:
            entrypoint: Dotted path like 'module.submodule:function'

        Returns:
            Callable function

        Raises:
            ImportError: If module or function cannot be loaded
        """
        if ":" in entrypoint:
            module_path, func_name = entrypoint.rsplit(":", 1)
        else:
            # Assume last component is function name
            parts = entrypoint.rsplit(".", 1)
            if len(parts) == 2:
                module_path, func_name = parts
            else:
                raise ImportError(
                    f"Invalid entrypoint format: {entrypoint}. "
                    "Expected 'module.path:function' or 'module.path.function'"
                )

        module = importlib.import_module(module_path)
        if not hasattr(module, func_name):
            raise ImportError(
                f"Function '{func_name}' not found in module '{module_path}'"
            )

        return getattr(module, func_name)

    @classmethod
    def from_config_file(cls, config_path: Path) -> "AceSkillRegistry":
        """
        Create a registry from a JSON/YAML configuration file.

        Args:
            config_path: Path to skills loop configuration file

        Returns:
            Initialized AceSkillRegistry

        Raises:
            ValidationError: If configuration is invalid
            FileNotFoundError: If config file doesn't exist
        """
        import json

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path) as f:
            if config_path.suffix == ".json":
                config_data = json.load(f)
            elif config_path.suffix in (".yaml", ".yml"):
                try:
                    import yaml

                    config_data = yaml.safe_load(f)
                except ImportError:
                    raise ImportError(
                        "PyYAML required for YAML config files. "
                        "Install with: pip install pyyaml"
                    )
            else:
                raise ValueError(
                    f"Unsupported config format: {config_path.suffix}"
                )

        config = SkillsLoopConfig.model_validate(config_data)
        return cls(config)

    def export_config(self, output_path: Path) -> None:
        """
        Export the current registry configuration to a file.

        Args:
            output_path: Path to write configuration
        """
        import json

        config_data = self.config.model_dump(mode="json")

        with open(output_path, "w") as f:
            json.dump(config_data, f, indent=2)

        logger.info(f"Exported config to {output_path}")


def create_default_registry() -> AceSkillRegistry:
    """
    Create a registry with default ACE skills.

    Returns:
        AceSkillRegistry with built-in skills
    """
    config = SkillsLoopConfig(
        enabled=True,
        registry=[
            # Default ACE skills will be added here
            # For now, registry is empty until skills are implemented
        ],
    )

    return AceSkillRegistry(config)
