"""
Playbook Diff Skill

Example ACE skill that compares playbook states and generates diff reports.
This demonstrates the idiomatic @tool usage pattern.
"""

from typing import Any, Dict

from ace.playbook import Bullet, Playbook


async def playbook_diff(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two playbook states and generate a diff report.

    This skill allows agents to analyze how the playbook has evolved
    during a skills loop session.

    Args:
        args: Tool arguments with keys:
            - before_bullets (list[dict]): Bullets from before state
            - after_bullets (list[dict]): Bullets from after state
            - show_scores (bool): Include helpful/harmful scores (default: True)

    Returns:
        Tool result with diff summary
    """
    before_bullets = args.get("before_bullets", [])
    after_bullets = args.get("after_bullets", [])
    show_scores = args.get("show_scores", True)

    # Calculate changes
    before_strategies = {b["strategy"] for b in before_bullets}
    after_strategies = {b["strategy"] for b in after_bullets}

    added = after_strategies - before_strategies
    removed = before_strategies - after_strategies
    common = before_strategies & after_strategies

    # Find modified bullets
    modified = []
    if show_scores:
        before_map = {b["strategy"]: b for b in before_bullets}
        after_map = {b["strategy"]: b for b in after_bullets}

        for strategy in common:
            before_score = (
                before_map[strategy].get("helpful_count", 0)
                - before_map[strategy].get("harmful_count", 0)
            )
            after_score = (
                after_map[strategy].get("helpful_count", 0)
                - after_map[strategy].get("harmful_count", 0)
            )

            if before_score != after_score:
                modified.append(
                    {
                        "strategy": strategy,
                        "score_delta": after_score - before_score,
                        "before_score": before_score,
                        "after_score": after_score,
                    }
                )

    # Format result
    lines = [
        "# Playbook Diff Report",
        "",
        f"**Added**: {len(added)} bullets",
        f"**Removed**: {len(removed)} bullets",
        f"**Modified**: {len(modified)} bullets",
        f"**Unchanged**: {len(common) - len(modified)} bullets",
        "",
    ]

    if added:
        lines.extend(["## Added Bullets", ""])
        for strategy in sorted(added):
            lines.append(f"- ✓ {strategy}")
        lines.append("")

    if removed:
        lines.extend(["## Removed Bullets", ""])
        for strategy in sorted(removed):
            lines.append(f"- ✗ {strategy}")
        lines.append("")

    if modified:
        lines.extend(["## Modified Bullets", ""])
        for mod in sorted(modified, key=lambda m: m["score_delta"], reverse=True):
            delta_sign = "+" if mod["score_delta"] > 0 else ""
            lines.append(
                f"- {mod['strategy'][:80]}... "
                f"[{delta_sign}{mod['score_delta']} points]"
            )
        lines.append("")

    result_text = "\n".join(lines)

    return {
        "content": [
            {
                "type": "text",
                "text": result_text,
            }
        ],
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": len(common) - len(modified),
        },
    }


# Tool metadata for registration
SKILL_DESCRIPTOR = {
    "name": "playbook_diff",
    "version": "1.0.0",
    "description": "Compare playbook states and generate diff reports",
    "entrypoint": "ace.skills_builder.examples.playbook_diff_skill:playbook_diff",
    "allowed_tools": [],
}
