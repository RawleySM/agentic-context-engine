"""
Developer CLI for ACE Skills Builder

Command-line tool for scaffolding skills, previewing tool wiring,
and running local smoke tests.

Usage:
    python -m ace.skills_builder.session_entrypoints.dev_cli [command] [options]

Commands:
    scaffold    - Create a new skill template
    preview     - Preview tool wiring for a config
    validate    - Validate skill configuration
    test        - Run smoke tests for skills
    export      - Export skill registry configuration
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional

from ace.skills_builder.models import SkillDescriptor, SkillsLoopConfig
from ace.skills_builder.registry import AceSkillRegistry, SkillNotFoundError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def command_scaffold(args: argparse.Namespace) -> int:
    """
    Scaffold a new skill template.

    Args:
        args: Command arguments

    Returns:
        Exit code
    """
    skill_name = args.name
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create skill file
    skill_file = output_dir / f"{skill_name}.py"

    template = f'''"""
{skill_name.replace("_", " ").title()} Skill

ACE skill for [description].
"""

from typing import Any, Dict


async def {skill_name}_tool(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    [Tool description]

    Args:
        args: Tool arguments

    Returns:
        Tool result with content blocks
    """
    # Implement skill logic here
    result = "Skill executed successfully"

    return {{
        "content": [
            {{
                "type": "text",
                "text": result,
            }}
        ]
    }}
'''

    with open(skill_file, "w") as f:
        f.write(template)

    # Create skill descriptor
    descriptor = SkillDescriptor(
        name=skill_name,
        version="0.1.0",
        description=f"{skill_name.replace('_', ' ').title()} skill",
        entrypoint=f"{skill_file.stem}:{skill_name}_tool",
        allowed_tools=[],
    )

    descriptor_file = output_dir / f"{skill_name}_descriptor.json"
    with open(descriptor_file, "w") as f:
        f.write(descriptor.model_dump_json(indent=2))

    print(f"✓ Created skill template: {skill_file}")
    print(f"✓ Created descriptor: {descriptor_file}")
    print(f"\nNext steps:")
    print(f"  1. Edit {skill_file} to implement skill logic")
    print(f"  2. Update descriptor in {descriptor_file}")
    print(f"  3. Add to skills registry configuration")

    return 0


def command_preview(args: argparse.Namespace) -> int:
    """
    Preview tool wiring for a configuration.

    Args:
        args: Command arguments

    Returns:
        Exit code
    """
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"✗ Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        registry = AceSkillRegistry.from_config_file(config_path)

        print(f"Skills Registry Preview")
        print(f"=" * 60)
        print(f"\nConfiguration: {config_path}")
        print(f"Skills enabled: {registry.config.enabled}")
        print(f"Registered skills: {len(registry.list_skills())}")
        print()

        for skill in registry.list_skills():
            print(f"  • {skill.name} (v{skill.version})")
            print(f"    Description: {skill.description}")
            print(f"    Entrypoint: {skill.entrypoint}")
            if skill.allowed_tools:
                print(f"    Allowed tools: {', '.join(skill.allowed_tools)}")
            print()

        print(f"Session configuration:")
        print(f"  Model: {registry.config.session.model}")
        print(
            f"  Permission mode: {registry.config.session.permission_mode}"
        )
        print(
            f"  Codex tools: {registry.config.session.codex_tools_enabled}"
        )
        print()

        if registry.config.custom_commands:
            print(f"Custom slash commands: {len(registry.config.custom_commands)}")
            for cmd in registry.config.custom_commands:
                print(f"  /{cmd.name} - {cmd.description}")
            print()

        return 0

    except Exception as e:
        print(f"✗ Failed to load config: {e}", file=sys.stderr)
        return 1


def command_validate(args: argparse.Namespace) -> int:
    """
    Validate skill configuration.

    Args:
        args: Command arguments

    Returns:
        Exit code
    """
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"✗ Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        registry = AceSkillRegistry.from_config_file(config_path)

        print(f"Validating skills configuration...")
        print()

        errors = []
        warnings = []

        for skill in registry.list_skills():
            skill_errors = registry.validate_skill_config(skill)
            if skill_errors:
                errors.extend(
                    [f"{skill.name}: {err}" for err in skill_errors]
                )

            # Try to load entrypoint
            try:
                registry.get_tool_callable(skill.name)
                print(f"✓ {skill.name}: entrypoint loaded successfully")
            except Exception as e:
                errors.append(f"{skill.name}: failed to load entrypoint - {e}")

        print()

        if errors:
            print(f"✗ Validation failed with {len(errors)} error(s):")
            for error in errors:
                print(f"  • {error}")
            return 1
        else:
            print(f"✓ Validation passed! All skills are properly configured.")
            return 0

    except Exception as e:
        print(f"✗ Validation failed: {e}", file=sys.stderr)
        return 1


def command_test(args: argparse.Namespace) -> int:
    """
    Run smoke tests for skills.

    Args:
        args: Command arguments

    Returns:
        Exit code
    """
    config_path = Path(args.config)

    if not config_path.exists():
        print(f"✗ Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        registry = AceSkillRegistry.from_config_file(config_path)

        print(f"Running smoke tests for {len(registry.list_skills())} skills...")
        print()

        failures = []

        for skill in registry.list_skills():
            try:
                # Test: load callable
                callable_fn = registry.get_tool_callable(skill.name)

                # Test: inspect signature
                import inspect

                sig = inspect.signature(callable_fn)
                print(
                    f"✓ {skill.name}: callable with signature {sig}"
                )

            except Exception as e:
                failures.append(f"{skill.name}: {e}")
                print(f"✗ {skill.name}: {e}")

        print()

        if failures:
            print(f"✗ {len(failures)} test(s) failed")
            return 1
        else:
            print(f"✓ All smoke tests passed!")
            return 0

    except Exception as e:
        print(f"✗ Test suite failed: {e}", file=sys.stderr)
        return 1


def command_export(args: argparse.Namespace) -> int:
    """
    Export skill registry configuration.

    Args:
        args: Command arguments

    Returns:
        Exit code
    """
    config_path = Path(args.config)
    output_path = Path(args.output)

    if not config_path.exists():
        print(f"✗ Config file not found: {config_path}", file=sys.stderr)
        return 1

    try:
        registry = AceSkillRegistry.from_config_file(config_path)
        registry.export_config(output_path)
        print(f"✓ Configuration exported to: {output_path}")
        return 0

    except Exception as e:
        print(f"✗ Export failed: {e}", file=sys.stderr)
        return 1


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code
    """
    parser = argparse.ArgumentParser(
        description="ACE Skills Builder Developer CLI"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Scaffold command
    scaffold_parser = subparsers.add_parser(
        "scaffold", help="Create a new skill template"
    )
    scaffold_parser.add_argument("name", help="Skill name (e.g., playbook_diff)")
    scaffold_parser.add_argument(
        "-o",
        "--output",
        default="ace/skills_builder/examples",
        help="Output directory",
    )

    # Preview command
    preview_parser = subparsers.add_parser(
        "preview", help="Preview tool wiring"
    )
    preview_parser.add_argument("config", help="Path to skills config file")

    # Validate command
    validate_parser = subparsers.add_parser(
        "validate", help="Validate skill configuration"
    )
    validate_parser.add_argument("config", help="Path to skills config file")

    # Test command
    test_parser = subparsers.add_parser("test", help="Run smoke tests")
    test_parser.add_argument("config", help="Path to skills config file")

    # Export command
    export_parser = subparsers.add_parser(
        "export", help="Export skill configuration"
    )
    export_parser.add_argument("config", help="Path to skills config file")
    export_parser.add_argument("-o", "--output", required=True, help="Output path")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Dispatch to command handler
    commands = {
        "scaffold": command_scaffold,
        "preview": command_preview,
        "validate": command_validate,
        "test": command_test,
        "export": command_export,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
