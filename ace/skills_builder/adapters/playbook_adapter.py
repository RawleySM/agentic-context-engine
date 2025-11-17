"""
Playbook Adapter

Converts ACE playbook structures to codex exec session context and system prompts.
"""

import logging
from typing import Dict, List, Optional

from ace.delta import DeltaBatch, DeltaOperation
from ace.playbook import Bullet, Playbook

logger = logging.getLogger(__name__)


class PlaybookAdapter:
    """
    Adapter for converting ACE playbooks to codex exec context.

    Transforms playbook bullets into system prompts, context summaries,
    and tool parameters for skills loop sessions.
    """

    def __init__(self, playbook: Playbook):
        """
        Initialize the playbook adapter.

        Args:
            playbook: ACE playbook to adapt
        """
        self.playbook = playbook

    def to_system_prompt(
        self,
        max_bullets: Optional[int] = None,
        include_counters: bool = True,
    ) -> str:
        """
        Convert playbook to a system prompt for codex exec.

        Args:
            max_bullets: Maximum number of bullets to include (None for all)
            include_counters: Whether to include helpful/harmful counters

        Returns:
            Formatted system prompt string
        """
        bullets = self.playbook.bullets
        if max_bullets is not None:
            bullets = bullets[:max_bullets]

        lines = [
            "# ACE Playbook Context",
            "",
            "The following strategies have been learned through previous task adaptations:",
            "",
        ]

        for i, bullet in enumerate(bullets, 1):
            if include_counters:
                counter_info = f" [+{bullet.helpful_count}/-{bullet.harmful_count}]"
            else:
                counter_info = ""

            lines.append(f"{i}. {bullet.strategy}{counter_info}")

            if bullet.tags:
                tags_str = ", ".join(sorted(bullet.tags))
                lines.append(f"   Tags: {tags_str}")

        lines.extend(
            [
                "",
                "Use these strategies to inform your approach to the current task.",
                "",
            ]
        )

        prompt = "\n".join(lines)
        logger.debug(
            f"Generated system prompt with {len(bullets)} bullets "
            f"({len(prompt)} chars)"
        )

        return prompt

    def to_context_summary(self) -> Dict[str, any]:
        """
        Create a structured context summary for tool injection.

        Returns:
            Dictionary with playbook statistics and top strategies
        """
        bullets = self.playbook.bullets

        # Calculate statistics
        total_helpful = sum(b.helpful_count for b in bullets)
        total_harmful = sum(b.harmful_count for b in bullets)

        # Get top strategies by net score
        sorted_bullets = sorted(
            bullets,
            key=lambda b: b.helpful_count - b.harmful_count,
            reverse=True,
        )

        top_strategies = [
            {
                "strategy": b.strategy,
                "net_score": b.helpful_count - b.harmful_count,
                "tags": list(b.tags),
            }
            for b in sorted_bullets[:5]
        ]

        summary = {
            "total_bullets": len(bullets),
            "total_helpful_signals": total_helpful,
            "total_harmful_signals": total_harmful,
            "top_strategies": top_strategies,
            "all_tags": sorted(self._collect_all_tags()),
        }

        return summary

    def get_relevant_bullets(
        self, tags: List[str], min_score: int = 1
    ) -> List[Bullet]:
        """
        Get bullets relevant to specific tags with minimum net score.

        Args:
            tags: Tags to filter by
            min_score: Minimum net score (helpful - harmful)

        Returns:
            List of relevant bullets
        """
        relevant = []

        for bullet in self.playbook.bullets:
            # Check if any requested tag is in bullet's tags
            if any(tag in bullet.tags for tag in tags):
                net_score = bullet.helpful_count - bullet.harmful_count
                if net_score >= min_score:
                    relevant.append(bullet)

        # Sort by net score descending
        relevant.sort(
            key=lambda b: b.helpful_count - b.harmful_count, reverse=True
        )

        logger.debug(
            f"Found {len(relevant)} relevant bullets for tags: {tags}"
        )

        return relevant

    def apply_delta_batch(self, batch: DeltaBatch) -> None:
        """
        Apply a delta batch to the playbook.

        Args:
            batch: Delta batch to apply
        """
        for operation in batch.operations:
            self._apply_delta_operation(operation)

        logger.info(
            f"Applied delta batch with {len(batch.operations)} operations"
        )

    def _apply_delta_operation(self, operation: DeltaOperation) -> None:
        """
        Apply a single delta operation.

        Args:
            operation: Delta operation to apply
        """
        op_type = operation.op_type

        if op_type == "ADD":
            # Add new bullet
            bullet = Bullet(
                strategy=operation.content,
                helpful_count=0,
                harmful_count=0,
            )
            if operation.tags:
                bullet.tags.update(operation.tags)
            self.playbook.bullets.append(bullet)
            logger.debug(f"Added bullet: {operation.content[:50]}...")

        elif op_type == "UPDATE":
            # Find and update bullet
            for bullet in self.playbook.bullets:
                if bullet.strategy == operation.target:
                    bullet.strategy = operation.content
                    if operation.tags:
                        bullet.tags.update(operation.tags)
                    logger.debug(f"Updated bullet: {operation.target[:50]}...")
                    break

        elif op_type == "TAG":
            # Add tags to bullet
            for bullet in self.playbook.bullets:
                if bullet.strategy == operation.target:
                    if operation.tags:
                        bullet.tags.update(operation.tags)
                    logger.debug(
                        f"Tagged bullet with: {operation.tags}"
                    )
                    break

        elif op_type == "REMOVE":
            # Remove bullet
            self.playbook.bullets = [
                b for b in self.playbook.bullets if b.strategy != operation.target
            ]
            logger.debug(f"Removed bullet: {operation.target[:50]}...")

    def _collect_all_tags(self) -> set:
        """
        Collect all unique tags from playbook bullets.

        Returns:
            Set of all tags
        """
        all_tags = set()
        for bullet in self.playbook.bullets:
            all_tags.update(bullet.tags)
        return all_tags

    @staticmethod
    def format_bullet_for_tool(bullet: Bullet) -> str:
        """
        Format a single bullet for tool output.

        Args:
            bullet: Bullet to format

        Returns:
            Formatted string representation
        """
        net_score = bullet.helpful_count - bullet.harmful_count
        score_str = f"[Net: {net_score:+d}]"

        if bullet.tags:
            tags_str = f" #{' #'.join(sorted(bullet.tags))}"
        else:
            tags_str = ""

        return f"{bullet.strategy} {score_str}{tags_str}"
