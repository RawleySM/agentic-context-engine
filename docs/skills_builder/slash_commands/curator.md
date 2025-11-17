# Curator Slash Commands

Custom slash commands for the ACE Curator role during skills loop sessions.

## Overview

The Curator uses these slash commands to gate which skill outcomes make it into curated playbook deltas and what proof (tests, artifacts) is mandatory.

---

## `/accept-delta`

**Description**: Accept a delta and apply it to the playbook

**Parameters**:
- `delta_id` (required, string): ID of the delta to accept
- `rationale` (required, string): Curator's rationale for acceptance
- `require_proof` (optional, bool): Whether test/artifact proof is required (default: true)
- `tags` (optional, list[string]): Additional tags to apply to the delta

**Permission Mode**: `acceptEdits`

**Observable Side Effects**:
- Applies delta operation to playbook
- Creates `SkillOutcome` record for the delta
- Emits `DeltaOutputFinalized` event
- Updates playbook bullets and persists changes

**Required Proof**:
When `require_proof=true`, the following must be present:
- Test results showing passing tests (if code changes)
- Artifact paths for generated files
- Coverage metrics meeting thresholds

**Completion Criteria**:
- Delta operation successfully applied to playbook
- Proof validated (if required)
- Playbook persisted to disk
- Transcript updated with acceptance record

**Example**:
```
/accept-delta delta_id="delta_001" rationale="Improves error handling based on test results" tags=["errors", "validated"]
```

---

## `/reject-delta`

**Description**: Reject a delta and document the reason

**Parameters**:
- `delta_id` (required, string): ID of the delta to reject
- `rationale` (required, string): Curator's rationale for rejection
- `feedback` (optional, string): Feedback for delta refinement

**Permission Mode**: `plan`

**Observable Side Effects**:
- Marks delta as rejected in trajectory
- Emits rejection record to transcript
- Does not modify playbook
- Optionally creates feedback for retry

**Completion Criteria**:
- Rejection record written to transcript
- Delta marked with `rejected=true` status
- Feedback provided (if applicable)

**Example**:
```
/reject-delta delta_id="delta_002" rationale="Tests failed with 3 errors" feedback="Fix authentication logic before retry"
```

---

## `/document`

**Description**: Generate documentation for accepted deltas

**Parameters**:
- `session_id` (required, string): Session to document
- `format` (optional, string): Output format ("markdown", "json", default: "markdown")
- `include_test_results` (optional, bool): Include test artifacts (default: true)

**Permission Mode**: `plan`

**Observable Side Effects**:
- Generates `ClosedCycleSummary` document
- Writes summary to `docs/` directory
- Links to test artifacts and transcripts
- Emits document generation event

**Completion Criteria**:
- Summary document created with all accepted deltas
- Test results and coverage metrics included
- Artifact links validated
- Document path returned

**Example**:
```
/document session_id="session_20240115" format="markdown" include_test_results=true
```

---

## `/verify-delta`

**Description**: Verify a delta's proof requirements before acceptance

**Parameters**:
- `delta_id` (required, string): ID of the delta to verify
- `strict_mode` (optional, bool): Enforce all proof requirements (default: true)

**Permission Mode**: `plan`

**Observable Side Effects**:
- Validates test results exist and pass
- Checks coverage thresholds
- Verifies artifact paths
- Emits verification report

**Completion Criteria**:
- Verification report with pass/fail status
- List of missing proof items (if any)
- Coverage delta calculation

**Example**:
```
/verify-delta delta_id="delta_003" strict_mode=true
```

---

## Implementation Notes

- `/accept-delta` requires `acceptEdits` permission mode
- All other commands run in `plan` mode
- Proof validation is enforced when `require_proof=true`
- Coverage thresholds are defined in `SkillsLoopConfig.coverage_thresholds`
- Delta operations follow ACE's existing delta types (ADD, UPDATE, TAG, REMOVE)

## Proof Requirements

For `/accept-delta` with `require_proof=true`:

### Test Proof
```json
{
  "test_mode": "pytest",
  "passed": true,
  "coverage_branch": 0.85,
  "coverage_lines": 0.90,
  "json_report_path": "docs/transcripts/test_report.json"
}
```

### Artifact Proof
```json
{
  "artifact_paths": [
    "ace/new_module.py",
    "tests/test_new_module.py"
  ],
  "artifact_types": ["implementation", "tests"]
}
```

### Coverage Proof
Must meet or exceed thresholds from config:
- `branch >= 0.8` (80%)
- `lines >= 0.85` (85%)

## Transcript Format

When a Curator slash command is invoked:

```json
{
  "event_type": "slash_command",
  "timestamp": "2024-01-15T10:40:30.789Z",
  "session_id": "session_...",
  "task_id": "task_...",
  "payload": {
    "command": "/accept-delta",
    "parameters": {
      "delta_id": "delta_001",
      "rationale": "Improves error handling based on test results",
      "require_proof": true,
      "tags": ["errors", "validated"]
    },
    "command_source": "custom",
    "permission_mode": "acceptEdits",
    "proof_validated": true,
    "playbook_modified": true
  }
}
```

## Error Handling

If proof validation fails:

```json
{
  "event_type": "slash_command",
  "timestamp": "2024-01-15T10:40:30.789Z",
  "session_id": "session_...",
  "task_id": "task_...",
  "payload": {
    "command": "/accept-delta",
    "delta_id": "delta_001",
    "error": "Proof validation failed: coverage_branch=0.75 below threshold 0.80",
    "permission_mode": "acceptEdits",
    "proof_validated": false
  }
}
```

## Permission Escalation

The `/accept-delta` command demonstrates permission mode escalation:

1. Session starts in `plan` mode
2. Curator invokes `/verify-delta` to check proof (still `plan`)
3. If proof valid, session escalates to `acceptEdits` mode
4. Curator invokes `/accept-delta` to modify playbook
5. After delta applied, session can return to `plan` mode
