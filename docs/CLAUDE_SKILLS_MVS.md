# Minimal Viable Solution: ACE Skills Session Inspector

## Purpose
Provide a fast, inspectable view of Claude Agent SDK skill loops that is more informative than raw terminal logs. The inspector highlights tool invocations, slash commands, and subagent hops within an ACE trajectory so curators can replay decisions and extract deltas efficiently.

## User Experience Overview
1. **Launch** the inspector with a single command (`python -m ace.tools.skills_inspector transcript.jsonl`).
2. **Select a trajectory** from the left-side list (per ACE run or task id).
3. **Browse structured panes**:
   - **Timeline Pane**: chronological stream of `AssistantMessage`, `ToolUseBlock`, `ToolResultBlock`, and `SubagentStop` events rendered as collapsible cards.
   - **Context Pane**: current playbook summary, applied deltas, and session metadata.
   - **Skill Detail Pane**: parameters, stdout/stderr, and curator annotations for each tool invocation.
4. **Export** curated deltas back to the playbook as JSON patches.

The UI is built with the [`textual` TUI framework](https://textual.textualize.io/) for minimal dependencies but can be replaced later by a web dashboard.

## Architecture
```
+----------------------+        +---------------------------+
| ACE run (skills loop)|        | docs/transcripts/*.jsonl |
| writes transcript via|        | structured SDK messages   |
| ClaudeSDKClient hooks |-----> | (JSONL storage)           |
+----------------------+        +---------------------------+
           |                                    |
           v                                    v
+----------------------+        +---------------------------+
| skills_inspector CLI |        | Inspector UI widgets      |
| loads transcript ->  |        | - TimelineView            |
| SessionModel         |        | - ContextView             |
+----------------------+        | - SkillDetailView         |
                                +---------------------------+
```

### Data Model
- **SessionModel**: wraps `ClaudeSDKClient` transcripts captured through ACE hooks (`HookEvent.UserPromptSubmit`, `HookEvent.SubagentStop`, `HookEvent.ToolStart`).
- **EventRecord**: normalized schema containing `event_type`, `timestamp`, `sdk_block` payload, and curator tags.
- **SkillOutcome**: derived from `ToolUseBlock` + `ToolResultBlock` pairs, enriched with `permission_mode` and `AgentDefinition` metadata at execution time.

### Data Source
- Reuse the Claude SDK streaming callbacks already introduced in the spec: call `client.get_server_info()` at session start, store the result, and mirror every streamed `Message` into a JSONL transcript. Example hook registration:

```python
from claude_sdk.hooks import HookEvent

sdk_client.add_hook(HookEvent.UserPromptSubmit, record_event)
sdk_client.add_hook(HookEvent.ToolStart, record_event)
sdk_client.add_hook(HookEvent.ToolFinish, record_event)
```

Each recorded message is serialized with `Message.model_dump()` so the inspector can faithfully reconstruct the session.

## CLI Workflow
```bash
python -m ace.tools.skills_inspector docs/transcripts/2024-09-12.jsonl
```

Internally, the CLI:
1. Loads all session entries into `SessionModel` using standard `pydantic` validators from the SDK (`Message`, `ToolUseBlock`, `ToolResultBlock`).
2. Groups events by `session_id` and `task_id`.
3. Boots a Textual application with keyboard shortcuts:
   - `←/→` switch tabs (Timeline / Context / Skill Detail)
   - `s` toggles slash-command filter
   - `e` exports selected skill delta to `ace/playbook_deltas/{session_id}.json`

## Minimal Implementation Steps
1. **Transcript Capture**
   - Extend `ace/integrations/claude_sdk.py` to write JSONL transcripts when the skills feature flag is enabled.
   - Ensure we capture `ClaudeAgentOptions.agents`, `allowed_tools`, and `permission_mode` per session header.

2. **Inspector CLI**
   - Add `ace/tools/skills_inspector.py` implementing:
     - `load_transcript(path)` -> `SessionModel`
     - `SkillInspectorApp` (Textual `App`) with widgets for timeline/context/detail.
     - Export command writing filtered deltas.

3. **Documentation**
   - Document workflow in `docs/CLAUDE_SKILLS_MVS.md` (this file) and link from README once feature stabilizes.

## Why This Beats Raw Logs
- **Structured filtering**: toggle to view only tool failures, slash commands, or subagent activity.
- **Replay fidelity**: reconstructs the exact order of `ClaudeSDKClient` events with metadata, avoiding loss in noisy terminal streams.
- **Curator workflow**: integrates export actions for deltas, letting curators update the playbook without leaving the inspector.
- **Extensible**: we can later add a WebSocket backend or React UI without changing the transcript schema.

## Future Enhancements
- Live mode by tailing an in-progress transcript file (Textual supports async updates).
- Browser dashboard built on the same `SessionModel`.
- Metrics overlay summarizing tool success rates and permission escalations per run.
