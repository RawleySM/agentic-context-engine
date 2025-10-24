# Proposal: Temporal-based Observability for ACE

## Context
ACE orchestrates multi-agent learning loops (Generator, Reflector, Curator) and recently
introduced a Claude Agent SDK-driven skills loop. Current observability relies on
streamed logs and ad-hoc transcript captures, making it difficult to correlate
trajectory events, Claude SDK tool usage, and downstream playbook updates.
Temporal provides a durable, queryable event history that can model ACE task runs as
workflows, giving us auditability, replay, and flexible monitoring without bolting
custom infrastructure onto every adapter.

## Goals
- Capture end-to-end ACE task executions (generator -> skills loop -> curator) as
  Temporal workflows with deterministic history.
- Expose rich observability dashboards for task trajectories, tool invocations, and
  playbook deltas using Temporal Web UI and custom queries.
- Provide replayable traces for regression debugging and offline evaluation harnesses.
- Maintain minimal friction for existing adapters; Temporal should wrap the orchestration
  surface, not require refactoring individual agents.

## Non-Goals
- Replacing ACE's internal playbook persistence or SQLite-backed artifacts.
- Building production-grade alerting pipelines (can integrate later via Temporal signals
  and metrics).
- Introducing Temporal into generator/reflector business logic; workflows focus on
  orchestration telemetry.

## Solution Overview
1. **Workflow Definition**: Model each ACE task run as a Temporal workflow (`AceTaskWorkflow`).
   - Inputs: task prompt, adapter mode, playbook hash, skills config.
   - Deterministic history includes generator prompts/responses, skills tool calls,
     curator decisions, and final deltas.
2. **Activities**: Wrap existing ACE steps (Generator, Skills Session, Curator) as
   Temporal activities invoked by the workflow. Activities execute existing Python
   code (possibly async) and return structured telemetry payloads (JSON serializable).
3. **Signals**: Use Temporal signals to ingest mid-run events such as Claude SDK hooks
   (`ToolUseBlock`, `SlashCommand`). Activities emit signals to update the workflow
   state machine without blocking long-running tasks.
4. **Queries**: Implement Temporal workflow queries for lightweight inspection:
   - `get_current_phase` -> returns generator/skills/curator progress.
   - `get_skill_usage` -> aggregated tool invocations + outcomes.
   - `get_playbook_delta` -> final curated strategy changes.
5. **Temporal Web UI**: Configure namespaces + search attributes for quick filtering by
   dataset, experiment tag, or adapter type. Observers can replay any workflow to
   inspect decision paths.

## Architecture Diagram (Textual)
```
ACE Orchestrator -> AceTaskWorkflow (Temporal)
    |-- Activity: run_generator(prompt, playbook)
    |       emits signals: tool_use, slash_command
    |-- Activity: run_skills_session(transcript)
    |-- Activity: run_curator(trajectory)
    '-- Activity: persist_results(deltas)
Temporal History -> indexed by (experiment_id, task_id, model)
Temporal Web UI -> dashboards, manual replay, search attributes
```

## Data Model
- **Workflow Input**
  ```json
  {
    "task_id": "uuid",
    "prompt": "...",
    "adapter": "offline|online",
    "playbook_hash": "sha256",
    "skills_config": {"allowed_tools": ["plan", "inspect"], "permission_mode": "plan"}
  }
  ```
- **Activity Result Payloads** (examples)
  - `GeneratorResult`: prompt tokens, sampled plan, trajectory id.
  - `SkillSessionResult`: list of tool invocations `{name, args, result, accepted}`.
  - `CuratorResult`: accepted deltas, rationale, follow-up actions.
- **Search Attributes**
  - `ExperimentId`, `DatasetId`, `ModelName`, `AdapterType`, `ExitStatus`.

## Integration Steps
1. **Bootstrap Temporal**
   - Deploy Temporal locally via docker-compose for development (namespace `ace-dev`).
   - Add configuration to `ace/config/observability.yaml` toggling Temporal integration.
2. **Define Workflows & Activities**
   - Create `ace/observability/temporal/workflows.py` with `AceTaskWorkflow` using
     `temporalio` Python SDK (`@workflow.defn`).
   - Implement activity wrappers in `ace/observability/temporal/activities.py` calling
     existing orchestrator entry points (`Generator.run`, `SkillsManager.run`, etc.).
   - Serialize telemetry payloads with Pydantic models to ensure schema stability.
3. **Hook Claude SDK Events**
   - Extend `ace/integrations/claude_sdk.py` to broadcast relevant hook events to Temporal
     via workflow signals (`@workflow.signal def record_tool_event(self, event: ToolEvent)`).
   - Buffer events locally when Temporal is disabled to keep API parity.
4. **Adapter Integration Layer**
   - Add a `TemporalObserver` class implementing ACE's observer interface. When enabled,
     it starts a workflow using `temporalio.client.Client.start_workflow` and feeds
     adapter events into signals/activities.
   - Provide fallback `NullObserver` for non-Temporal runs.
5. **Observability CLI**
   - Extend `scripts/ace_cli.py` with commands:
     - `ace observe temporal tail --task-id <id>` -> uses Temporal queries to stream state.
     - `ace observe temporal replay --task-id <id>` -> triggers workflow replay locally.
6. **Dashboards & Docs**
   - Document expected search attributes and example Temporal Web UI queries.
   - Include guidance for combining Temporal history with existing playbook diffs.

## Rollout Phases
1. **Phase 0: Spike**
   - Implement skeleton workflow + generator activity.
   - Capture generator prompts/responses, verify history in Temporal Web UI.
2. **Phase 1: Skills Loop Telemetry**
   - Add signals for tool invocations and slash commands.
   - Validate event ordering against existing transcript logs.
3. **Phase 2: Curator & Deltas**
   - Complete activity coverage, store curated deltas + outcomes.
   - Expose `get_playbook_delta` query.
4. **Phase 3: Experimentation Support**
   - Add search attributes, CLI tooling, and documentation.
   - Integrate with offline replay harness for regression testing.

## Risks & Mitigations
- **Workflow Determinism**: Ensure activities encapsulate nondeterministic operations.
  Workflow code must remain deterministic—limit in-workflow logic to state machine updates.
- **Operational Overhead**: Temporal cluster requires maintenance; mitigate with managed
  Temporal Cloud or containerized deployments for dev/test.
- **Latency**: Workflow start/await adds latency; use async activities + signals to
  avoid blocking while still capturing events.
- **Cost**: Monitor event history size; prune raw transcripts after storing in
  artifact storage, keeping references in Temporal history.

## Success Criteria
- Every ACE run yields a Temporal workflow with searchable attributes and accessible
  transcripts within Temporal Web UI.
- On-call developers can replay a workflow to reproduce generator/skills/curator
  decisions without relying on raw log dumps.
- Observability CLI provides parity with current terminal streaming, with improved
  filtering and historical lookup capabilities.
