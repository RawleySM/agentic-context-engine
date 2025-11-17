# Reflector Slash Commands

Custom slash commands for the ACE Reflector role during skills loop sessions.

## Overview

The Reflector uses these slash commands to request codex exec tools for analysis, assert required telemetry fields, and constrain permissions for read-only reviews.

---

## `/review`

**Description**: Review a task trajectory and classify bullet contributions

**Parameters**:
- `trajectory_id` (required, string): ID of the trajectory to review
- `feedback` (required, string): Environment feedback (success/failure message)
- `analysis_depth` (optional, string): Level of analysis ("quick", "standard", "deep", default: "standard")

**Permission Mode**: `plan` (read-only)

**Observable Side Effects**:
- Invokes trajectory analysis tools
- Creates bullet classification records (helpful/harmful)
- Emits `TranscriptEvent` entries for each analysis step

**Completion Criteria**:
- Returns list of helpful bullets with rationale
- Returns list of harmful bullets with rationale
- Provides confidence scores for each classification

**Example**:
```
/review trajectory_id="task_20240115_103045" feedback="Test failed: authentication error" analysis_depth="deep"
```

---

## `/hypothesis`

**Description**: Generate hypotheses about why a task succeeded or failed

**Parameters**:
- `task_result` (required, dict): Task execution result
- `playbook_context` (optional, dict): Relevant playbook bullets used
- `max_hypotheses` (optional, int): Maximum hypotheses to generate (default: 5)

**Permission Mode**: `plan`

**Observable Side Effects**:
- Analyzes correlation between playbook bullets and task outcome
- Emits hypothesis records to transcript
- No playbook modifications

**Required Telemetry Fields**:
- `task_result.answer`: Generated answer
- `task_result.tools_used`: List of tools invoked
- `task_result.thinking_tokens`: Optional thinking process

**Completion Criteria**:
- Returns ordered list of hypotheses (most likely first)
- Each hypothesis includes supporting evidence
- Identifies causal relationships between bullets and outcome

**Example**:
```
/hypothesis task_result={...} max_hypotheses=3
```

---

## `/coverage`

**Description**: Analyze playbook coverage relative to a task domain

**Parameters**:
- `task_domain` (required, string): Domain description (e.g., "database optimization")
- `bullet_tags` (optional, list[string]): Tags to filter playbook bullets

**Permission Mode**: `plan`

**Observable Side Effects**:
- Scans playbook for relevant bullets
- Generates coverage statistics
- Emits coverage report to transcript

**Required Telemetry Fields**:
- `playbook.total_bullets`: Total bullets in playbook
- `playbook.tags`: All unique tags

**Completion Criteria**:
- Returns coverage percentage for the domain
- Lists gaps where coverage is weak
- Suggests new bullet directions

**Example**:
```
/coverage task_domain="async error handling" bullet_tags=["async", "errors"]
```

---

## Implementation Notes

- All Reflector slash commands run in `plan` mode (read-only)
- Commands should not modify the playbook directly (that's the Curator's role)
- Analysis tools have access to trajectory transcripts and playbook context
- Telemetry validation occurs before command execution; missing fields cause failure

## Telemetry Requirements

The Reflector commands assert the following telemetry fields are present:

### Required Fields
- `session_id`: Current skills session identifier
- `task_id`: Task being analyzed
- `permission_mode`: Must be "plan" for all Reflector commands
- `trajectory_events`: List of transcript events

### Optional Fields
- `thinking_snippet`: Redacted thinking tokens (for hypothesis generation)
- `tool_invocations`: Detailed tool usage (for `/coverage`)

## Transcript Format

When a Reflector slash command is invoked:

```json
{
  "event_type": "slash_command",
  "timestamp": "2024-01-15T10:35:12.456Z",
  "session_id": "session_...",
  "task_id": "task_...",
  "payload": {
    "command": "/review",
    "parameters": {
      "trajectory_id": "task_20240115_103045",
      "feedback": "Test failed: authentication error",
      "analysis_depth": "deep"
    },
    "command_source": "custom",
    "permission_mode": "plan",
    "telemetry_validated": true
  }
}
```

## Error Handling

If required telemetry fields are missing:

```json
{
  "event_type": "slash_command",
  "timestamp": "2024-01-15T10:35:12.456Z",
  "session_id": "session_...",
  "task_id": "task_...",
  "payload": {
    "command": "/hypothesis",
    "error": "Missing required telemetry field: task_result.answer",
    "permission_mode": "plan"
  }
}
```
