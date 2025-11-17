# Subagent Slash Commands

Custom slash commands for ephemeral subagents during skills loop sessions.

## Overview

Subagents are specialized agents spun up during the skills loop to handle specific tasks. These slash commands manage their lifecycle, context inheritance, and result handoff.

---

## `/delegate`

**Description**: Delegate a subtask to a specialized subagent

**Parameters**:
- `agent_type` (required, string): Type of subagent to spawn ("analyzer", "builder", "tester", "reviewer")
- `task` (required, string): Task description for the subagent
- `inherit_context` (optional, bool): Whether subagent inherits session context (default: true)
- `timeout_seconds` (optional, int): Maximum execution time (default: 300)

**Permission Mode**: Inherits from parent session

**Observable Side Effects**:
- Creates new `AgentDefinition` for subagent
- Spawns subagent with scoped context
- Emits `SubagentStart` event with session ID inheritance
- Subagent events appear in main transcript with `subagent_id` tag

**Session ID Inheritance**:
- Subagent receives `parent_session_id` from main session
- Subagent creates own `subagent_session_id`
- Both IDs recorded in transcript for traceability

**Hooks Emitted**:
- `HookEvent.SubagentStart`: When subagent spawned
- `HookEvent.SubagentStop`: When subagent completes (see `/converge`)

**Completion Criteria**:
- Subagent spawned successfully
- Context inherited (if requested)
- Subagent session ID returned

**Example**:
```
/delegate agent_type="tester" task="Run integration tests for authentication module" inherit_context=true timeout_seconds=600
```

---

## `/handoff`

**Description**: Hand off control to a subagent and wait for its completion

**Parameters**:
- `subagent_id` (required, string): ID of the subagent to hand off to
- `await_completion` (optional, bool): Whether to block until subagent completes (default: true)

**Permission Mode**: Inherits from parent session

**Observable Side Effects**:
- Pauses parent session execution
- Activates subagent for exclusive control
- Parent session receives subagent events
- Emits `SubagentHandoff` event

**Completion Criteria**:
- Subagent receives control
- Parent session enters waiting state
- Handoff event recorded

**Example**:
```
/handoff subagent_id="subagent_abc123" await_completion=true
```

---

## `/converge`

**Description**: Converge subagent results back to the main session

**Parameters**:
- `subagent_id` (required, string): ID of the subagent to converge
- `merge_strategy` (optional, string): How to merge results ("append", "replace", "cherry-pick", default: "append")
- `include_transcript` (optional, bool): Include subagent transcript in main session (default: true)

**Permission Mode**: Inherits from parent session

**Observable Side Effects**:
- Terminates subagent session
- Merges subagent results into parent trajectory
- Emits `HookEvent.SubagentStop`
- Writes convergence record to transcript

**Hooks Emitted**:
- `HookEvent.SubagentStop`: Contains subagent completion metadata

**Completion Criteria**:
- Subagent session terminated cleanly
- Results merged according to strategy
- Convergence record includes subagent metrics (duration, tool usage, outcomes)

**Example**:
```
/converge subagent_id="subagent_abc123" merge_strategy="append" include_transcript=true
```

---

## `/fork`

**Description**: Fork the current session for experimental trajectory branching

**Parameters**:
- `fork_name` (required, string): Name for the forked session
- `permission_mode` (optional, PermissionMode): Permission mode for fork (default: same as parent)
- `copy_playbook` (optional, bool): Whether to copy playbook state (default: true)

**Permission Mode**: Specified by parameter or inherited

**Observable Side Effects**:
- Creates a forked session with `fork_session=true`
- Copies current trajectory up to fork point
- Emits `SessionForked` event
- Forked session runs independently

**Use Cases**:
- Experiment with different strategies without affecting main trajectory
- Parallel exploration of solution paths
- A/B testing of playbook deltas

**Completion Criteria**:
- Fork session created with unique ID
- Context copied (playbook, trajectory up to fork point)
- Fork registered in main session metadata

**Example**:
```
/fork fork_name="experimental_auth_v2" permission_mode="plan" copy_playbook=true
```

---

## Implementation Notes

- All subagent commands inherit permission mode from parent unless overridden
- Subagent sessions must emit their own session IDs for transcript clarity
- Parent sessions can spawn multiple subagents but should converge them sequentially
- Forked sessions do not converge back (they're experimental branches)

## Subagent Types

### Analyzer Subagent
- **Purpose**: Analyze code, trajectories, or playbook patterns
- **Tools**: Read-only analysis tools
- **Permission Mode**: `plan`

### Builder Subagent
- **Purpose**: Generate code, modify files
- **Tools**: Code generation, file operations
- **Permission Mode**: `acceptEdits`

### Tester Subagent
- **Purpose**: Run tests, validate coverage
- **Tools**: pytest, coverage tools
- **Permission Mode**: `plan` (tests are read-only)

### Reviewer Subagent
- **Purpose**: Review delta outcomes, suggest improvements
- **Tools**: Analysis and comparison tools
- **Permission Mode**: `plan`

## Session ID Hierarchy

```
main_session_id: "session_20240115_103045"
  ├─ subagent_session_id: "subagent_20240115_103100_analyzer"
  │  └─ parent_session_id: "session_20240115_103045"
  ├─ subagent_session_id: "subagent_20240115_103200_tester"
  │  └─ parent_session_id: "session_20240115_103045"
  └─ fork_session_id: "session_20240115_103300_fork_experimental"
     └─ parent_session_id: "session_20240115_103045"
```

## Transcript Format

### Subagent Delegation
```json
{
  "event_type": "slash_command",
  "timestamp": "2024-01-15T10:31:00.000Z",
  "session_id": "session_20240115_103045",
  "task_id": "task_...",
  "payload": {
    "command": "/delegate",
    "parameters": {
      "agent_type": "tester",
      "task": "Run integration tests for authentication module",
      "inherit_context": true,
      "timeout_seconds": 600
    },
    "subagent_id": "subagent_20240115_103100_tester",
    "parent_session_id": "session_20240115_103045"
  }
}
```

### Subagent Stop Hook
```json
{
  "event_type": "subagent_stop",
  "timestamp": "2024-01-15T10:41:30.000Z",
  "session_id": "session_20240115_103045",
  "task_id": "task_...",
  "payload": {
    "subagent_id": "subagent_20240115_103100_tester",
    "parent_session_id": "session_20240115_103045",
    "duration_seconds": 630,
    "tools_invoked": 5,
    "outcome_summary": "All tests passed, coverage: 87%",
    "merge_strategy": "append"
  }
}
```

## Best Practices

1. **Limit Subagent Depth**: Avoid subagents spawning more subagents (max depth: 2)
2. **Set Timeouts**: Always specify `timeout_seconds` for long-running subagents
3. **Converge Sequentially**: Don't spawn multiple subagents without converging previous ones
4. **Use Forks for Experiments**: Use `/fork` for exploratory work, not `/delegate`
5. **Track Session IDs**: Maintain clear parent/child relationships in transcripts
