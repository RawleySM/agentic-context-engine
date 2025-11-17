# Subagent Slash Commands

This document defines the custom slash commands for ephemeral subagents in the ACE Skills Loop. Subagents are specialized agents spun up during the skills loop to handle focused tasks, inheriting session context while maintaining isolated scope.

## Command Definitions

### `/delegate`

Delegates a specific task to a new subagent with defined capabilities and scope.

**Canonical Command Text:**
```
/delegate <task_description>
```

**Parameters:**
- `task_description` (required): Natural language description of the delegated task
- `--agent-type <type>` (required): Type of subagent to spawn (`builder`, `tester`, `analyzer`, `retriever`)
- `--inherit-context` (optional): Inherit parent session's playbook context (default: true)
- `--permission-mode <mode>` (optional): Permission level for subagent (`plan`, `acceptEdits`, `bypassPermissions`). Default: `plan`
- `--timeout <seconds>` (optional): Maximum execution time for subagent (default: 300)
- `--tools <tool1,tool2>` (optional): Restrict subagent to specific tool subset

**Permission Mode:**
- Inherits parent session's permission mode by default
- Can be restricted but not elevated beyond parent's permissions
- `bypassPermissions` requires explicit parent approval

**Observable Side Effects:**
- Creates `SubagentSpawned` JSONL event with `subagent_id`, `agent_type`, `parent_session_id`
- Emits `TranscriptEvent` with `event_type=subagent_start` containing task description
- Spawns isolated `AgentsClient` session with new `session_id`
- Registers `HookEvent.SubagentStop` callback for lifecycle tracking
- Links subagent trajectory to parent via `parent_session_ref`

**Expected Tool Invocations:**
- `create_subagent_definition(agent_type, task_description)` - Generates `AgentDefinition`
- `initialize_subagent_session(definition, options)` - Spawns new AgentsClient
- `transfer_context(parent_session, subagent_session)` - (Optional) Copies playbook context
- `register_subagent_hooks(subagent_id)` - Wires lifecycle and telemetry callbacks

**Completion Criteria:**
- Subagent session is successfully initialized
- Subagent receives task prompt and begins execution
- `SubagentActive` event emitted with `subagent_id` and `initial_state`
- Parent session continues without blocking (async delegation)

**Agent Type Specifications:**

#### `builder`
- **Purpose**: Code generation, file modifications, build operations
- **Default tools**: File I/O, code editing, build/compile tools
- **Default permission**: `acceptEdits` (requires parent approval)
- **Typical usage**: Implementing features, refactoring, applying deltas

#### `tester`
- **Purpose**: Test execution, coverage analysis, validation
- **Default tools**: pytest, coverage tools, file readers
- **Default permission**: `plan` (read-only)
- **Typical usage**: Running test suites, validating changes, collecting artifacts

#### `analyzer`
- **Purpose**: Code analysis, trajectory inspection, pattern detection
- **Default tools**: grep, file readers, analysis utilities
- **Default permission**: `plan` (read-only)
- **Typical usage**: Reviewing code, analyzing trajectories, gap detection

#### `retriever`
- **Purpose**: External information gathering, documentation lookup
- **Default tools**: Web fetch, API clients, document parsers
- **Default permission**: `plan` with network access
- **Typical usage**: Fetching docs, searching codebases, gathering context

---

### `/handoff`

Transfers control from parent session to subagent, blocking parent until subagent completes.

**Canonical Command Text:**
```
/handoff <subagent_id>
```

**Parameters:**
- `subagent_id` (required): Identifier of the active subagent to hand off to
- `--transfer-control` (optional): Full control transfer (parent suspends). Default: false (monitor mode)
- `--timeout <seconds>` (optional): Maximum time to wait for subagent completion (default: 600)
- `--on-failure <action>` (optional): Action if subagent fails (`retry`, `abort`, `escalate`). Default: `escalate`

**Permission Mode:**
- Inherits subagent's permission mode during handoff
- Parent session's permissions are restored after handoff completes

**Observable Side Effects:**
- Creates `HandoffInitiated` JSONL event with `parent_session_id`, `subagent_id`, `handoff_mode`
- Parent session enters `suspended` state if `--transfer-control` is true
- Emits `TranscriptEvent` entries for all subagent activities during handoff
- On completion: creates `HandoffComplete` event with subagent outcome
- Links subagent results back to parent trajectory

**Expected Tool Invocations:**
- `get_subagent_status(subagent_id)` - Checks subagent state before handoff
- `suspend_parent_session(session_id)` - (Optional) Pauses parent session
- `monitor_subagent_progress(subagent_id)` - Streams subagent events to parent
- `collect_subagent_results(subagent_id)` - Gathers outcome after completion
- `resume_parent_session(session_id, results)` - Restores parent with subagent output

**Completion Criteria:**
- Subagent completes task successfully OR fails with error
- All subagent trajectory events are merged into parent transcript
- Parent session resumes with subagent results available
- `HandoffResolved` event emitted with `outcome` and `artifacts`
- If failure: action specified by `--on-failure` is executed

**Handoff Modes:**

#### Monitor Mode (default)
- Parent continues receiving events but does not act
- Subagent has full autonomy within its scope
- Parent can observe but not intervene
- Suitable for async background tasks

#### Transfer Control Mode (`--transfer-control`)
- Parent suspends completely
- Subagent has exclusive control
- Parent resumes only after subagent completes
- Suitable for critical sequential operations

---

### `/converge`

Merges results from multiple subagents, reconciling conflicts and producing unified output.

**Canonical Command Text:**
```
/converge <subagent_id1> <subagent_id2> [<subagent_id3> ...]
```

**Parameters:**
- `subagent_id1, subagent_id2, ...` (required): Two or more subagent IDs to converge
- `--strategy <type>` (required): Convergence strategy (`merge`, `vote`, `consensus`, `first_success`)
- `--conflict-resolution <method>` (optional): How to handle conflicts (`manual`, `auto_accept_latest`, `prefer_higher_confidence`). Default: `manual`
- `--output-format <format>` (optional): Format for unified output (`json`, `markdown`, `delta_batch`). Default: `delta_batch`

**Permission Mode:**
- `plan` - Convergence analysis is read-only
- `acceptEdits` - Required if convergence produces playbook deltas
- Must not exceed parent session's permission level

**Observable Side Effects:**
- Creates `ConvergenceInitiated` JSONL event with all `subagent_ids` and `strategy`
- Loads all subagent trajectories and results
- Emits `TranscriptEvent` for each conflict detection and resolution
- Creates unified `ConvergedResult` merging subagent outputs
- May produce `DeltaBatch` if convergence yields playbook updates

**Expected Tool Invocations:**
- `load_subagent_results(subagent_ids)` - Retrieves all subagent outcomes
- `detect_conflicts(results)` - Identifies incompatible or contradictory outputs
- `apply_convergence_strategy(results, strategy)` - Executes convergence algorithm
- `resolve_conflicts(conflicts, method)` - Handles conflicts per resolution method
- `create_unified_output(converged_results, format)` - Produces final output

**Completion Criteria:**
- All subagent results are loaded and analyzed
- Conflicts are detected and resolved (or flagged for manual review)
- Unified output is generated in requested format
- `ConvergenceComplete` event emitted with `conflict_count`, `resolution_count`, `output_size`
- If conflicts remain: `ManualReviewRequired` event with conflict details

**Convergence Strategies:**

#### `merge`
- Combines all subagent outputs additively
- Suitable when subagents handle disjoint subtasks
- Conflicts indicate overlapping work (flag for review)

#### `vote`
- Selects most common result among subagents
- Requires ≥3 subagents for meaningful voting
- Suitable for validation tasks with redundancy

#### `consensus`
- Requires all subagents to agree (within tolerance)
- Rejects output if any subagent disagrees significantly
- Suitable for critical operations requiring high confidence

#### `first_success`
- Returns result from first subagent to succeed
- Ignores results from other subagents
- Suitable for racing multiple approaches

**Conflict Resolution Methods:**

#### `manual`
- Flags conflicts for curator review
- Does not produce output until resolved
- Creates `ConflictReviewRequest` for curator

#### `auto_accept_latest`
- Uses most recent subagent's result
- Suitable when later subagents have more context
- Logs overridden results for audit

#### `prefer_higher_confidence`
- Selects result with highest confidence score
- Requires subagents to emit confidence metadata
- Suitable when subagent quality varies

---

## Usage Guidelines

### Subagent Lifecycle
1. **Spawn**: Parent delegates task via `/delegate`
2. **Execute**: Subagent runs autonomously with scoped tools and permissions
3. **Monitor**: Parent tracks progress through `SubagentStop` hooks
4. **Complete**: Subagent emits `ResultMessage` and terminates
5. **Merge**: Results integrate into parent trajectory

### Session Inheritance
- Subagents inherit parent's `session_id` as `parent_session_ref`
- Subagent gets unique `session_id` for isolation
- Playbook context can be inherited via `--inherit-context`
- Permission mode cannot exceed parent's level
- Tools can be restricted but not expanded beyond parent's `allowed_tools`

### Telemetry and Hooks
- All subagent commands emit `HookEvent.SubagentStop` on completion
- Parent session receives subagent trajectory events in real-time
- Subagent thinking tokens captured if available
- Tool invocations linked to subagent via `subagent_ref`

### Permission Scoping
- Subagents cannot escalate permissions beyond parent
- Sandboxing rules apply based on subagent's permission mode
- `bypassPermissions` requires explicit parent approval and logging
- Failed permission checks terminate subagent with error event

### Error Handling
- Subagent failures emit `SubagentError` event with stderr and context
- Parent can retry, abort, or escalate based on failure handler
- Timeout triggers automatic termination and `SubagentTimeout` event
- Partial results may be available even on failure

### Trajectory Integration
- Subagent events tagged with `subagent_id` in parent transcript
- Enables filtering and replay of specific subagent contributions
- Convergence operations merge trajectories with conflict markers
- Inspector can render subagent trees for complex delegations

---

## Observability

### Structured Logging
All subagent commands emit detailed logs with required fields:
- `session_id` (parent)
- `subagent_id`
- `agent_type`
- `permission_mode`
- `task_description`
- `spawn_timestamp`
- `completion_timestamp`
- `outcome` (`success`, `failure`, `timeout`)
- `tool_invocation_count`
- `artifact_paths[]`

### Metrics Tracking
- Subagent spawn rate and success rate
- Average task completion time by agent type
- Permission escalation frequency
- Convergence conflict rate
- Timeout and retry statistics

### Audit Trail
- All subagent delegations logged for reproducibility
- Convergence decisions recorded with rationale
- Permission grants tracked with justification
- Failed subagents preserved for debugging

---

## Version History

- **v1.0.0** (2024-01-15): Initial specification for Subagent slash commands
