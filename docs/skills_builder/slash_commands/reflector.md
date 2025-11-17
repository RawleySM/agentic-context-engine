# Reflector Agent Slash Commands

This document defines the custom slash commands available to the Reflector role in the ACE Skills Loop. The Reflector analyzes task trajectories, evaluates errors, and classifies the contribution of playbook bullets to task outcomes.

## Command Definitions

### `/review`

Initiates analysis of a task trajectory, requesting Codex Exec tools for detailed inspection.

**Canonical Command Text:**
```
/review <trajectory_id>
```

**Parameters:**
- `trajectory_id` (required): Identifier for the task trajectory to review
- `--focus <aspect>` (optional): Specific aspect to review (`reasoning`, `tool_usage`, `accuracy`, `all`). Default: `all`
- `--include-tools` (optional): Comma-separated list of tool names to analyze in detail
- `--bullet-filter <tag>` (optional): Only review bullets with specific tag

**Permission Mode:**
- `plan` - Read-only review mode (default and recommended)
- Codex Exec tools are permitted for analysis but not modification

**Observable Side Effects:**
- Creates `ReviewInitiated` JSONL event with `trajectory_id`, `session_id`, `focus_aspect`
- Emits `TranscriptEvent` entries for each analysis tool invocation
- Records `ToolUseBlock` and `ToolResultBlock` pairs for all analysis operations
- May create provisional `BulletClassification` records for curator consumption

**Expected Tool Invocations:**
- `load_trajectory(trajectory_id)` - Retrieves full trajectory including assistant messages and tool results
- `extract_reasoning_chain(trajectory)` - Parses decision points and reasoning steps
- `classify_bullet_impact(bullet_id, trajectory)` - Determines if bullet was helpful/harmful/neutral
- `identify_error_patterns(trajectory)` - Extracts common failure modes
- `compute_trajectory_metrics(trajectory)` - Calculates success rate, tool usage stats, etc.

**Completion Criteria:**
- Review analysis is complete and stored as structured `ReviewOutcome`
- All bullet classifications are recorded with confidence scores
- `ReviewComplete` event emitted with `classification_count` and `error_pattern_count`
- Session can proceed to hypothesis generation or curator phase

---

### `/hypothesis`

Generates hypotheses about why specific bullets helped or harmed task performance, asserting required telemetry fields.

**Canonical Command Text:**
```
/hypothesis <bullet_id> <classification>
```

**Parameters:**
- `bullet_id` (required): Identifier of the playbook bullet to analyze
- `classification` (required): One of `helpful`, `harmful`, `neutral`
- `--trajectory-ref <trajectory_id>` (optional): Reference trajectory demonstrating the effect
- `--confidence <float>` (optional): Confidence score [0.0, 1.0] for classification (default: 0.5)
- `--rationale <text>` (optional): Free-text explanation for the hypothesis

**Permission Mode:**
- `plan` - Read-only hypothesis generation

**Observable Side Effects:**
- Creates `HypothesisGenerated` JSONL event with all parameters and timestamp
- Records `TranscriptEvent` with `event_type=assistant_message` containing hypothesis reasoning
- Updates trajectory analysis with new hypothesis linking bullet to outcome
- Increments bullet's helpful/harmful counter provisionally (pending curator approval)

**Expected Tool Invocations:**
- `get_bullet_content(bullet_id)` - Retrieves bullet text and metadata
- `load_trajectory(trajectory_ref)` - Loads reference trajectory if provided
- `extract_bullet_usage(bullet_id, trajectory)` - Finds where bullet influenced generation
- `compute_attribution_score(bullet, trajectory)` - Quantifies bullet's causal contribution

**Completion Criteria:**
- Hypothesis is structured with all required telemetry fields:
  - `bullet_id`, `classification`, `confidence`, `rationale`, `trajectory_ref`, `timestamp`
- Hypothesis is stored for curator review
- `HypothesisRecorded` event emitted with `hypothesis_id`

---

### `/coverage`

Analyzes test coverage and trajectory telemetry to constrain analysis to high-confidence areas.

**Canonical Command Text:**
```
/coverage [--trajectory <trajectory_id>] [--playbook-section <section>]
```

**Parameters:**
- `--trajectory <trajectory_id>` (optional): Analyze coverage for specific trajectory
- `--playbook-section <section>` (optional): Analyze bullet coverage for playbook section
- `--metric <type>` (optional): Coverage metric type (`bullet_usage`, `tool_coverage`, `reasoning_paths`). Default: `all`
- `--threshold <float>` (optional): Minimum coverage threshold to report [0.0, 1.0]

**Permission Mode:**
- `plan` - Read-only coverage analysis

**Observable Side Effects:**
- Creates `CoverageAnalysis` JSONL event with coverage metrics and session context
- Emits `TranscriptEvent` with coverage report as structured payload
- May flag low-coverage areas as `attention_needed` for curator review
- Records tool invocation patterns and unused capabilities

**Expected Tool Invocations:**
- `compute_bullet_coverage(playbook_section)` - Calculates percentage of bullets used in trajectories
- `analyze_tool_usage(trajectory_id)` - Identifies which tools were invoked and frequency
- `trace_reasoning_paths(trajectory_id)` - Maps decision branches taken during generation
- `identify_unused_bullets(playbook_section, trajectories)` - Finds bullets never referenced
- `compute_coverage_metrics()` - Aggregates coverage statistics across multiple dimensions

**Completion Criteria:**
- Coverage report is generated with required fields:
  - `bullet_usage_pct`, `tool_coverage_pct`, `reasoning_path_coverage`, `low_coverage_items[]`
- Report includes actionable recommendations for improving coverage
- `CoverageAnalysisComplete` event emitted with summary statistics
- Low-coverage areas are flagged for potential playbook expansion or bullet refinement

---

## Usage Guidelines

### Integration with ACE Roles
- Reflector commands are invoked after Generator produces task outcomes
- Commands operate on completed trajectories and do not modify them
- Analysis results feed directly into Curator decision-making

### Read-Only Constraint
- All Reflector commands enforce `permission_mode="plan"` by default
- Codex Exec tools may be used for analysis (grep, file reads, trajectory parsing)
- No code modifications, playbook edits, or destructive operations permitted
- Permission violations are logged and block command completion

### Telemetry Requirements
- All commands must capture minimum telemetry fields:
  - `session_id`, `trajectory_id`, `timestamp`, `permission_mode`, `tool_invocations[]`
- Hypothesis generation requires confidence scores and rationale text
- Coverage analysis requires quantitative metrics (percentages, counts)

### Structured Output
- Analysis results are stored as structured JSON objects
- Hypothesis records conform to `HypothesisRecord` schema
- Coverage reports conform to `CoverageReport` schema
- All outputs include machine-readable confidence/certainty indicators

### Error Handling
- Missing trajectory_id or bullet_id triggers descriptive error
- Invalid classification values (`helpful`/`harmful`/`neutral` only) are rejected
- Tool failures during analysis are logged but do not block other analyses
- Incomplete telemetry results in warning but may allow completion with degraded data

---

## Version History

- **v1.0.0** (2024-01-15): Initial specification for Reflector slash commands
