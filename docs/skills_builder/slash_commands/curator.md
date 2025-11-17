# Curator Agent Slash Commands

This document defines the custom slash commands available to the Curator role in the ACE Skills Loop. The Curator evaluates skill outcomes and reflection results, deciding which deltas to accept into the playbook and ensuring all changes are properly documented.

## Command Definitions

### `/accept-delta`

Accepts a skill outcome or hypothesis as a playbook delta, promoting it to the curated playbook.

**Canonical Command Text:**
```
/accept-delta <delta_id>
```

**Parameters:**
- `delta_id` (required): Identifier of the delta to accept (from skill outcome or hypothesis)
- `--rationale <text>` (required): Justification for accepting this delta
- `--confidence <float>` (optional): Confidence score [0.0, 1.0] for the acceptance (default: 0.8)
- `--test-proof <artifact_path>` (optional): Path to test artifacts validating the delta
- `--tags <tag1,tag2>` (optional): Comma-separated tags for categorizing the delta

**Permission Mode:**
- `acceptEdits` - Required to modify the playbook
- Enforced before any playbook mutations occur

**Observable Side Effects:**
- Creates `DeltaAccepted` JSONL event with `delta_id`, `rationale`, `timestamp`, `curator_id`
- Emits `DeltaOperation` (ADD, UPDATE, or TAG) to the playbook store
- Updates bullet helpful/harmful counters based on delta classification
- Records `TranscriptEvent` with `event_type=tool_use_block` for playbook modification
- If test proof provided: links artifact to delta in playbook metadata

**Expected Tool Invocations:**
- `load_delta(delta_id)` - Retrieves full delta content and metadata
- `validate_delta(delta)` - Checks delta conforms to playbook schema
- `apply_delta_operation(delta, playbook)` - Executes the playbook update
- `verify_test_artifacts(artifact_path)` - (Optional) Validates test proof if provided
- `update_playbook_version(playbook)` - Increments playbook version counter

**Completion Criteria:**
- Delta is successfully applied to playbook
- Playbook version is incremented
- `DeltaApplicationComplete` event emitted with `new_playbook_version`
- Test artifacts (if provided) are validated and linked
- Rationale and confidence are recorded for audit trail

**Mandatory Proof Requirements:**
- Deltas with `phase=build` tag MUST include `--test-proof` with passing test results
- Test artifacts must demonstrate coverage thresholds met (branch ≥ 80%, lines ≥ 85%)
- Deltas without required proof are rejected with `InsufficientEvidence` error

---

### `/reject-delta`

Rejects a skill outcome or hypothesis, preventing it from entering the curated playbook.

**Canonical Command Text:**
```
/reject-delta <delta_id>
```

**Parameters:**
- `delta_id` (required): Identifier of the delta to reject
- `--reason <text>` (required): Explanation for rejection
- `--category <type>` (optional): Rejection category (`insufficient_evidence`, `test_failure`, `conflicts_playbook`, `low_confidence`, `other`). Default: `other`
- `--suggest-revision` (optional): Flag to suggest delta author revise and resubmit

**Permission Mode:**
- `plan` - Rejection decisions are read-only (no playbook edits)
- May escalate to `acceptEdits` if rejection triggers cleanup operations

**Observable Side Effects:**
- Creates `DeltaRejected` JSONL event with `delta_id`, `reason`, `category`, `timestamp`
- Updates delta status to `rejected` in trajectory log
- Records `TranscriptEvent` documenting rejection rationale
- If `--suggest-revision`: creates `RevisionRequest` for delta author with feedback
- May trigger rollback operations if partial application occurred

**Expected Tool Invocations:**
- `load_delta(delta_id)` - Retrieves delta for rejection logging
- `record_rejection(delta_id, reason, category)` - Persists rejection decision
- `analyze_rejection_patterns(delta_id)` - Identifies systemic issues if applicable
- `create_revision_request(delta_id, feedback)` - (Optional) Notifies author of rejection

**Completion Criteria:**
- Delta status is updated to `rejected`
- Rejection reason and category are recorded
- `DeltaRejectionComplete` event emitted
- If revision requested: `RevisionRequest` is created and linked to delta
- Playbook remains unchanged (no mutations)

**Rejection Category Guidelines:**
- `insufficient_evidence`: Missing test artifacts, low confidence scores, or weak rationale
- `test_failure`: Provided test proof shows failures or insufficient coverage
- `conflicts_playbook`: Delta contradicts existing bullets or creates inconsistency
- `low_confidence`: Confidence score below threshold (typically < 0.6)
- `other`: Edge cases requiring manual review or escalation

---

### `/document`

Generates documentation summarizing accepted deltas, test results, and playbook changes.

**Canonical Command Text:**
```
/document <session_id>
```

**Parameters:**
- `session_id` (required): Skills session to document
- `--format <type>` (optional): Output format (`markdown`, `json`, `html`). Default: `markdown`
- `--include-rejected` (optional): Include rejected deltas in documentation
- `--output-path <path>` (optional): Write documentation to specified file
- `--link-artifacts` (optional): Include hyperlinks to test artifacts and trajectory transcripts

**Permission Mode:**
- `plan` - Documentation generation is read-only
- May escalate to `acceptEdits` if writing to `docs/` or release notes

**Observable Side Effects:**
- Creates `DocumentationGenerated` JSONL event with `session_id`, `format`, `output_path`
- Emits `TranscriptEvent` with documentation content as payload
- Writes documentation file if `--output-path` specified
- May update `docs/` directory or append to release notes
- Links to pytest JSON reports and coverage artifacts

**Expected Tool Invocations:**
- `load_session_summary(session_id)` - Retrieves all deltas and outcomes
- `format_accepted_deltas(deltas, format)` - Renders accepted deltas as documentation
- `generate_test_summary(session_id)` - Aggregates test results and coverage metrics
- `create_artifact_links(session_id)` - Builds hyperlinks to stored artifacts
- `render_phase_timeline(session_id)` - Creates visual timeline of Plan/Build/Test/Review/Document phases
- `write_documentation(content, output_path)` - (Optional) Persists to file

**Completion Criteria:**
- Documentation is generated with required sections:
  - Executive summary of session outcomes
  - List of accepted deltas with rationales
  - Test results and coverage metrics
  - Links to trajectory transcripts and artifacts
  - Phase timeline showing progression through skills loop
- If `--output-path`: file is written successfully
- If `--include-rejected`: rejection reasons are summarized
- `DocumentationComplete` event emitted with `artifact_count` and `output_location`

**Documentation Format Specification:**

#### Markdown Format (default)
```markdown
# Skills Session Documentation: {session_id}

## Summary
- Session started: {timestamp}
- Total deltas processed: {count}
- Accepted: {accepted_count}
- Rejected: {rejected_count}
- Test coverage: {coverage_pct}%

## Accepted Deltas
### {delta_id}: {delta_title}
- **Rationale**: {rationale}
- **Confidence**: {confidence}
- **Test proof**: [link to artifacts]
- **Phase**: {phase}

## Test Results
- Branch coverage: {branch_pct}%
- Line coverage: {line_pct}%
- Tests passed: {passed}/{total}
- Artifacts: [links]

## Phase Timeline
PLAN → BUILD → TEST → REVIEW → DOCUMENT
[duration details]
```

#### JSON Format
```json
{
  "session_id": "...",
  "summary": { ... },
  "accepted_deltas": [ ... ],
  "rejected_deltas": [ ... ],
  "test_results": { ... },
  "phase_timeline": [ ... ],
  "artifact_links": [ ... ]
}
```

---

## Usage Guidelines

### Integration with ACE Roles
- Curator commands execute after Reflector completes analysis
- Commands gate which skill outcomes enter the playbook
- All curation decisions are logged for audit and replay

### Permission Requirements
- `/accept-delta` requires `acceptEdits` mode
- `/reject-delta` operates in `plan` mode (read-only)
- `/document` defaults to `plan` but may need `acceptEdits` for file writes
- Permission violations block command execution with clear error messages

### Proof Validation
- Build-phase deltas MUST include test artifacts
- Test proof must demonstrate:
  - All tests passing (no failures)
  - Coverage thresholds met (branch ≥ 80%, lines ≥ 85%)
  - No regressions in existing functionality
- Missing or invalid proof triggers automatic rejection

### Decision Rationale
- All accept/reject decisions require human-readable rationale
- Rationale should explain:
  - Why this delta improves the playbook
  - How test evidence supports the decision
  - What risks were considered and mitigated
- Rationale becomes part of playbook audit trail

### Conflict Resolution
- Curator detects conflicts when delta contradicts existing bullets
- Conflicts must be explicitly resolved:
  - Update existing bullet (UPDATE operation)
  - Add new bullet with clarifying tag (ADD + TAG)
  - Reject new delta and retain existing bullet
- Unresolved conflicts block acceptance

### Artifact Linking
- Test artifacts stored with predictable paths: `{session_id}/test_results_{delta_id}.json`
- Coverage reports: `{session_id}/coverage_{delta_id}.xml`
- Trajectory transcripts: `{session_id}/transcript.jsonl`
- Documentation includes hyperlinks for inspector replay

---

## Version History

- **v1.0.0** (2024-01-15): Initial specification for Curator slash commands
