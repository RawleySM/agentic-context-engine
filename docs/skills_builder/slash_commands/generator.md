# Generator Slash Commands

Custom slash commands for the ACE Generator role during skills loop sessions.

## Overview

The Generator uses these slash commands to seed planning prompts, list accepted tool contexts, and specify when Codex Exec can auto-expand requirements.

---

## `/plan`

**Description**: Seed a planning session for task decomposition

**Parameters**:
- `objective` (required, string): High-level objective to plan for
- `max_bullets` (optional, int): Maximum playbook bullets to consider (default: 20)
- `include_tags` (optional, list[string]): Filter playbook bullets by tags

**Permission Mode**: `plan`

**Observable Side Effects**:
- Creates a `TaskStub` entry with `source=command`
- Emits a `TranscriptEvent` of type `slash_command`
- Generates tool invocations for playbook analysis

**Completion Criteria**:
- Returns a structured plan with ordered steps
- Each step includes tool requirements and expected artifacts

**Example**:
```
/plan objective="Implement user authentication" include_tags=["security", "auth"]
```

---

## `/scope`

**Description**: List accepted tool contexts and available skills for the current session

**Parameters**:
- `filter_by` (optional, string): Filter tools by category (e.g., "playbook", "analysis")

**Permission Mode**: `plan`

**Observable Side Effects**:
- Emits a `TranscriptEvent` showing available tools
- No playbook modifications

**Completion Criteria**:
- Returns list of available tools with descriptions
- Includes permission requirements for each tool

**Example**:
```
/scope filter_by="playbook"
```

---

## `/playbook-gap`

**Description**: Identify gaps in the current playbook where new strategies might be helpful

**Parameters**:
- `task_context` (required, string): Description of the current task domain
- `min_confidence` (optional, float): Minimum confidence threshold for gap detection (0.0-1.0, default: 0.7)

**Permission Mode**: `plan`

**Observable Side Effects**:
- Analyzes current playbook bullets
- Creates `DeltaInput` records for identified gaps
- Emits analysis results to transcript

**Completion Criteria**:
- Returns list of identified gaps with rationale
- Each gap includes suggested strategy direction

**Example**:
```
/playbook-gap task_context="Error handling in async operations" min_confidence=0.8
```

---

## Implementation Notes

- All Generator slash commands run in `plan` mode (read-only)
- Commands should be invoked before generating answers to inform strategy selection
- Playbook context is automatically injected via system prompt
- Codex Exec auto-expansion is enabled when `codex_tools_enabled=true` in session config

## Transcript Format

When a Generator slash command is invoked, the following event is recorded:

```json
{
  "event_type": "slash_command",
  "timestamp": "2024-01-15T10:30:45.123Z",
  "session_id": "session_...",
  "task_id": "task_...",
  "payload": {
    "command": "/plan",
    "parameters": {
      "objective": "Implement user authentication",
      "include_tags": ["security", "auth"]
    },
    "command_source": "custom",
    "permission_mode": "plan"
  }
}
```
