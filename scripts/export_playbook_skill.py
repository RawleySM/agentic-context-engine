"""CLI helper for exporting an ACE playbook as a Claude agent skill."""

from __future__ import annotations

import argparse
from pathlib import Path

from ace.playbook import Playbook
from ace.claude.skills import SkillMetadata, export_playbook_skill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--playbook",
        required=True,
        help="Path to the playbook JSON file to export.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Destination directory for the Claude skill bundle.",
    )
    parser.add_argument(
        "--title",
        default="Agentic Context Engine Skill",
        help="Title used in the generated SKILL.md front matter.",
    )
    parser.add_argument(
        "--description",
        default="Exported ACE playbook packaged for the Claude Agent SDK.",
        help="Description inserted into the SKILL.md body.",
    )
    parser.add_argument(
        "--version",
        default="0.1.0",
        help="Version number recorded in the SKILL.md front matter.",
    )
    parser.add_argument(
        "--tag",
        dest="tags",
        action="append",
        default=[],
        help="Optional tags added to the SKILL.md front matter. Repeat for multiple tags.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    playbook_path = Path(args.playbook)
    output_dir = Path(args.output_dir)

    playbook = Playbook.load_from_file(str(playbook_path))
    metadata = SkillMetadata(
        title=args.title,
        description=args.description,
        version=args.version,
        tags=args.tags,
    )
    files = export_playbook_skill(playbook, output_dir, metadata=metadata)

    print("Exported Claude skill files:")
    for name, path in files.items():
        print(f" - {name}: {path}")


if __name__ == "__main__":
    main()
