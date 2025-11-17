"""
ACE-to-Codex Exec Adapters

Provides adapter classes that bridge ACE abstractions (playbooks, trajectories, roles)
with codex exec constructs (AgentOptions, HookMatcher, AgentsClient).
"""

from ace.skills_builder.adapters.playbook_adapter import PlaybookAdapter
from ace.skills_builder.adapters.trajectory_adapter import TrajectoryAdapter

__all__ = ["PlaybookAdapter", "TrajectoryAdapter"]
