"""
Trajectory Analyzer Skill

Example ACE skill that analyzes task trajectories to identify patterns
and suggest playbook improvements.
"""

from collections import Counter
from typing import Any, Dict, List


async def analyze_trajectory(args: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze a task trajectory to identify patterns and insights.

    This skill helps the Reflector understand which strategies led to
    success or failure by analyzing the sequence of actions.

    Args:
        args: Tool arguments with keys:
            - events (list[dict]): Trajectory events
            - outcome (str): Task outcome ("success" or "failure")
            - playbook_bullets_used (list[str]): Bullets that were active

    Returns:
        Tool result with analysis summary
    """
    events = args.get("events", [])
    outcome = args.get("outcome", "unknown")
    bullets_used = args.get("playbook_bullets_used", [])

    # Analyze event types
    event_type_counts = Counter(e.get("event_type") for e in events)

    # Analyze tool usage
    tool_names = []
    for event in events:
        if event.get("event_type") == "tool_use_block":
            tool_name = event.get("payload", {}).get("tool_name")
            if tool_name:
                tool_names.append(tool_name)

    tool_usage = Counter(tool_names)

    # Analyze errors
    error_count = sum(
        1
        for e in events
        if e.get("event_type") == "tool_result_block"
        and e.get("payload", {}).get("is_error", False)
    )

    # Generate insights
    insights = []

    # Insight: Tool usage patterns
    if tool_usage:
        most_used_tool = tool_usage.most_common(1)[0]
        insights.append(
            f"Most used tool: {most_used_tool[0]} ({most_used_tool[1]} times)"
        )

    # Insight: Error correlation
    if error_count > 0 and outcome == "failure":
        insights.append(
            f"Task failed with {error_count} tool errors - likely causal"
        )
    elif error_count > 0 and outcome == "success":
        insights.append(
            f"Task succeeded despite {error_count} tool errors - resilient strategy"
        )

    # Insight: Playbook bullet effectiveness
    if bullets_used:
        if outcome == "success":
            insights.append(
                f"Success with {len(bullets_used)} active bullets - "
                f"consider marking as helpful"
            )
        else:
            insights.append(
                f"Failure with {len(bullets_used)} active bullets - "
                f"review for potential harmful strategies"
            )

    # Format result
    lines = [
        "# Trajectory Analysis",
        "",
        f"**Outcome**: {outcome.upper()}",
        f"**Total Events**: {len(events)}",
        f"**Tool Invocations**: {len(tool_names)}",
        f"**Errors**: {error_count}",
        "",
        "## Event Type Distribution",
        "",
    ]

    for event_type, count in event_type_counts.most_common():
        lines.append(f"- {event_type}: {count}")

    lines.extend(["", "## Tool Usage", ""])

    if tool_usage:
        for tool, count in tool_usage.most_common():
            lines.append(f"- {tool}: {count} invocations")
    else:
        lines.append("- No tools invoked")

    lines.extend(["", "## Insights", ""])

    for insight in insights:
        lines.append(f"- {insight}")

    if bullets_used:
        lines.extend(["", "## Active Playbook Bullets", ""])
        for bullet in bullets_used[:5]:  # Top 5
            lines.append(f"- {bullet[:80]}...")

    result_text = "\n".join(lines)

    return {
        "content": [
            {
                "type": "text",
                "text": result_text,
            }
        ],
        "analysis": {
            "outcome": outcome,
            "total_events": len(events),
            "tool_invocations": len(tool_names),
            "errors": error_count,
            "insights": insights,
        },
    }


# Tool metadata for registration
SKILL_DESCRIPTOR = {
    "name": "analyze_trajectory",
    "version": "1.0.0",
    "description": "Analyze task trajectories to identify patterns and insights",
    "entrypoint": "ace.skills_builder.examples.trajectory_analyzer_skill:analyze_trajectory",
    "allowed_tools": [],
}
