# Generator Agent Slash Commands

This document defines the custom slash commands available to the Generator role in the ACE Skills Loop. The Generator is responsible for producing answers using the current playbook and initiating the planning phase for new tasks.

## Command Definitions

### `/plan`

Seeds the Generator's planning prompts to create a structured task plan from a high-level objective.

**Canonical Command Text:**
```
/plan <objective>
```

**Parameters:**
- `objective` (required): High-level task description or goal to plan for
- `--context <playbook_section>` (optional): Specific playbook section to reference
- `--model <model_name>` (optional): Override default model (defaults to gpt-5)

**Permission Mode:**
- `plan` - Read-only mode, no code modifications permitted

**Observable Side Effects:**
- Creates a `TaskStub` entry tagged with `source=delta` and `phase=plan`
- Emits `PlanInitiated` JSONL event with `session_id`, `task_id`, `objective`
- Records planning reasoning as a `TranscriptEvent` with `event_type=assistant_message`
- May invoke `get_playbook_context` tool to fetch relevant strategies

**Expected Tool Invocations:**
- `get_playbook_context(section=<playbook_section>)` - Retrieves relevant playbook bullets
- `create_task_stub(objective, phase="plan")` - Generates structured task stub

**Completion Criteria:**
- Plan artifact is captured as a playbook delta
- `PlanFinalized` event is emitted with delta_id
- Session transitions to next phase or closes with `ResultMessage`

---

### `/scope`

Lists accepted tool contexts and determines which Codex Exec capabilities are available for the current task.

**Canonical Command Text:**
```
/scope [--tools] [--commands] [--permissions]
```

**Parameters:**
- `--tools` (optional): List available tools from `AgentOptions.allowed_tools`
- `--commands` (optional): List server-provided slash commands via `get_server_info()`
- `--permissions` (optional): Show current `permission_mode` and escalation rules

**Permission Mode:**
- `plan` - Read-only inspection of available capabilities

**Observable Side Effects:**
- Creates `ScopeInspection` JSONL event with requested scope details
- Records tool/command enumeration as `TranscriptEvent` with `event_type=tool_result_block`
- Updates session metadata with `capabilities_snapshot`

**Expected Tool Invocations:**
- `get_server_info()` - Fetches server-provided slash commands and subagents
- `list_allowed_tools()` - Enumerates tools registered in current session
- `get_permission_mode()` - Returns current permission level

**Completion Criteria:**
- Scope information is returned in structured format
- No state changes or playbook modifications
- Completes with single response message containing scope details

---

### `/playbook-gap`

Identifies gaps in the current playbook where new strategies might be needed, triggering context expansion.

**Canonical Command Text:**
```
/playbook-gap <query>
```

**Parameters:**
- `query` (required): Natural language description of the problem domain or task type
- `--threshold <float>` (optional): Minimum relevance score for gap detection (default: 0.6)
- `--auto-expand` (optional): Flag to automatically expand playbook with new bullet templates

**Permission Mode:**
- `plan` - Gap detection is read-only
- `acceptEdits` - Required if `--auto-expand` is enabled

**Observable Side Effects:**
- Creates `PlaybookGapAnalysis` JSONL event with query, matched bullets, and gap score
- Emits `TranscriptEvent` with `event_type=tool_use_block` for gap detection tool
- If `--auto-expand`: creates provisional delta operations tagged with `source=gap_analysis`

**Expected Tool Invocations:**
- `analyze_playbook_coverage(query, threshold)` - Computes coverage score
- `find_relevant_bullets(query)` - Retrieves existing strategies matching query
- `suggest_bullet_template(query)` - (Optional) Generates provisional bullet if gap detected

**Completion Criteria:**
- Gap analysis results are returned with coverage score and identified gaps
- If gaps found and `--auto-expand`: provisional deltas are created for curator review
- `GapAnalysisComplete` event emitted with `gap_count` and `provisional_delta_ids`

---

## Usage Guidelines

### Integration with ACE Roles
- Generator slash commands are invoked at the start of adaptation cycles
- Commands should be used to establish context before generating answers
- All commands operate within the constraints of the current `AgentSessionConfig`

### Session Lifecycle
- Commands are available immediately after `AgentsClient.connect()`
- Server commands are cached via `get_server_info()` at session start
- Custom ACE commands are registered through `AgentOptions.custom_commands`

### Trajectory Recording
- All slash command invocations are captured as `TranscriptEvent` entries
- Event payloads include full parameter sets and execution timestamps
- Tool invocations triggered by commands are linked via `stub_ref`

### Error Handling
- Invalid parameters trigger immediate failure with error code
- Permission violations (e.g., `/playbook-gap --auto-expand` in `plan` mode) are logged as blocked operations
- Failures do not advance the task phase; session remains in current state

---

## Version History

- **v1.0.0** (2024-01-15): Initial specification for Generator slash commands
