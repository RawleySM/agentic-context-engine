"""
Integration tests for ACE Skills Registry.
"""

import unittest
from pathlib import Path

from ace.skills_builder.models import SkillDescriptor, SkillsLoopConfig
from ace.skills_builder.registry import AceSkillRegistry, SkillNotFoundError


class TestSkillRegistry(unittest.TestCase):
    """Test cases for AceSkillRegistry."""

    def test_empty_registry(self):
        """Test creating an empty registry."""
        config = SkillsLoopConfig(enabled=True, registry=[])
        registry = AceSkillRegistry(config)

        self.assertEqual(len(registry.list_skills()), 0)

    def test_register_skill(self):
        """Test registering a skill."""
        config = SkillsLoopConfig(enabled=True)
        registry = AceSkillRegistry(config)

        # Register example skill
        descriptor = SkillDescriptor(
            name="test_skill",
            version="1.0.0",
            description="Test skill",
            entrypoint="ace.skills_builder.examples.playbook_diff_skill:playbook_diff",
            allowed_tools=[],
        )

        registry.register_skill(descriptor)

        # Verify registration
        self.assertEqual(len(registry.list_skills()), 1)
        retrieved = registry.get_skill("test_skill")
        self.assertEqual(retrieved.name, "test_skill")
        self.assertEqual(retrieved.version, "1.0.0")

    def test_get_nonexistent_skill(self):
        """Test getting a skill that doesn't exist."""
        config = SkillsLoopConfig(enabled=True)
        registry = AceSkillRegistry(config)

        with self.assertRaises(SkillNotFoundError):
            registry.get_skill("nonexistent")

    def test_duplicate_registration(self):
        """Test that duplicate skill names are rejected."""
        config = SkillsLoopConfig(enabled=True)
        registry = AceSkillRegistry(config)

        descriptor = SkillDescriptor(
            name="duplicate",
            version="1.0.0",
            description="Test",
            entrypoint="ace.skills_builder.examples.playbook_diff_skill:playbook_diff",
        )

        registry.register_skill(descriptor)

        # Try to register again
        with self.assertRaises(ValueError):
            registry.register_skill(descriptor)

    def test_validate_skill_config(self):
        """Test skill configuration validation."""
        config = SkillsLoopConfig(enabled=True)
        registry = AceSkillRegistry(config)

        # Valid descriptor
        valid_descriptor = SkillDescriptor(
            name="valid_skill",
            version="1.0.0",
            description="Valid",
            entrypoint="module.path:function",
        )
        errors = registry.validate_skill_config(valid_descriptor)
        self.assertEqual(len(errors), 0)

        # Invalid version
        invalid_version = SkillDescriptor(
            name="invalid_version",
            version="1.0",  # Not semver
            description="Invalid",
            entrypoint="module.path:function",
        )
        errors = registry.validate_skill_config(invalid_version)
        self.assertGreater(len(errors), 0)

        # Invalid name
        invalid_name = SkillDescriptor(
            name="invalid name!",  # Contains invalid characters
            version="1.0.0",
            description="Invalid",
            entrypoint="module.path:function",
        )
        errors = registry.validate_skill_config(invalid_name)
        self.assertGreater(len(errors), 0)

    def test_get_tool_callable(self):
        """Test retrieving tool callable."""
        config = SkillsLoopConfig(enabled=True)
        registry = AceSkillRegistry(config)

        descriptor = SkillDescriptor(
            name="playbook_diff",
            version="1.0.0",
            description="Playbook diff tool",
            entrypoint="ace.skills_builder.examples.playbook_diff_skill:playbook_diff",
        )

        registry.register_skill(descriptor)

        # Get callable
        callable_fn = registry.get_tool_callable("playbook_diff")
        self.assertIsNotNone(callable_fn)
        self.assertTrue(callable(callable_fn))

    def test_allowed_tools(self):
        """Test allowed tools configuration."""
        config = SkillsLoopConfig(enabled=True)
        registry = AceSkillRegistry(config)

        descriptor = SkillDescriptor(
            name="skill_with_tools",
            version="1.0.0",
            description="Skill with allowed tools",
            entrypoint="ace.skills_builder.examples.playbook_diff_skill:playbook_diff",
            allowed_tools=["read", "grep", "glob"],
        )

        registry.register_skill(descriptor)

        allowed = registry.get_allowed_tools_for_skill("skill_with_tools")
        self.assertEqual(allowed, ["read", "grep", "glob"])


if __name__ == "__main__":
    unittest.main()
