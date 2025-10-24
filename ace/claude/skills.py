"""Utilities for exporting ACE playbooks as Claude agent skills."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

from ..playbook import Playbook


@dataclass
class SkillMetadata:
    """Metadata describing the exported Claude agent skill."""

    title: str
    description: str
    version: str = "0.1.0"
    tags: Optional[Iterable[str]] = None

    def to_front_matter(self) -> str:
        tags = list(self.tags or [])
        tags_block = "\n".join(f"  - {tag}" for tag in tags)
        front_matter = ["---", f"title: {self.title}", f"version: {self.version}"]
        if tags_block:
            front_matter.append("tags:")
            front_matter.append(tags_block)
        front_matter.append("---")
        return "\n".join(front_matter)


def export_playbook_skill(
    playbook: Playbook,
    output_dir: Path | str,
    *,
    metadata: SkillMetadata,
    include_playbook_json: bool = True,
) -> Dict[str, Path]:
    """Export a playbook into a Claude Agent SDK compatible skill folder."""

    base_path = Path(output_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    files: Dict[str, Path] = {}

    skill_md = base_path / "SKILL.md"
    playbook_summary = playbook.as_prompt() or "(empty playbook)"
    skill_body = (
        f"{metadata.to_front_matter()}\n\n"
        f"{metadata.description}\n\n"
        "## Strategy Playbook\n\n"
        f"````markdown\n{playbook_summary}\n````\n"
    )
    skill_md.write_text(skill_body, encoding="utf-8")
    files["skill_md"] = skill_md

    if include_playbook_json:
        playbook_json = base_path / "playbook.json"
        playbook_json.write_text(playbook.dumps(), encoding="utf-8")
        files["playbook_json"] = playbook_json

    resources_dir = base_path / "resources"
    resources_dir.mkdir(exist_ok=True)
    overview_file = resources_dir / "OVERVIEW.md"
    overview_file.write_text(
        """# ACE Claude Skill

This folder packages an Agentic Context Engine playbook so it can be
loaded as a Claude skill. Update the playbook JSON snapshot whenever the
training loop produces a new strategy bundle.
""",
        encoding="utf-8",
    )
    files["resources_overview"] = overview_file

    return files


__all__ = ["SkillMetadata", "export_playbook_skill"]
