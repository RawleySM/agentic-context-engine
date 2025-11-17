# ACE Skills Builder

The Skills Builder module provides integration between ACE (Agentic Context Engineering) and Claude Code SDK (codex exec) to enable automated, skills-based development loops.

## Overview

The Skills Builder orchestrates a **Plan → Build → Test → Review → Document** automation loop where:

- **Generator** agents use skills to enhance answer generation
- **Reflector** agents analyze outcomes with analysis tools
- **Curator** agents manage playbook evolution with delta tools
- All phases are tracked in JSONL transcripts for inspector replay

## Architecture

```
ace/skills_builder/
├── models.py              # Pydantic data models (SkillsLoopConfig, etc.)
├── registry/              # Skill registration and metadata
│   └── registry.py
├── runtimes/              # Skill runtime factories and tool bindings
│   └── runtime_factory.py
├── adapters/              # ACE-to-codex-exec adapters
│   ├── playbook_adapter.py
│   └── trajectory_adapter.py
├── session_entrypoints/   # Developer and agent entry points
│   ├── dev_cli.py        # CLI for scaffolding and testing
│   └── agent_runtime.py  # Runtime for Generator/Reflector/Curator
├── tools/                 # Built-in automation tools
│   ├── test_runner.py    # pytest + coverage integration
│   └── closed_cycle.py   # Plan→Build→Test→Review→Document coordinator
├── observability/         # Structured logging and metrics
│   ├── logger.py         # JSON logger with curator visibility
│   └── metrics.py        # Metrics collector for sessions
├── examples/              # Example skills
│   ├── playbook_diff_skill.py
│   └── trajectory_analyzer_skill.py
└── tests/                 # Integration tests
    ├── test_registry.py
    └── test_adapters.py
```

## Quick Start

### 1. Create a Skills Configuration

```json
{
  "enabled": true,
  "registry": [
    {
      "name": "playbook_diff",
      "version": "1.0.0",
      "description": "Compare playbook states",
      "entrypoint": "ace.skills_builder.examples.playbook_diff_skill:playbook_diff",
      "allowed_tools": []
    }
  ],
  "session": {
    "model": "gpt-5",
    "codex_tools_enabled": true,
    "permission_mode": "plan"
  },
  "skills_loop_closed_cycle": true,
  "coverage_thresholds": {
    "branch": 0.8,
    "lines": 0.85
  }
}
```

Save as `skills_config.json`.

### 2. Use the Dev CLI

```bash
# Scaffold a new skill
python -m ace.skills_builder.session_entrypoints.dev_cli scaffold my_skill

# Preview tool wiring
python -m ace.skills_builder.session_entrypoints.dev_cli preview skills_config.json

# Validate configuration
python -m ace.skills_builder.session_entrypoints.dev_cli validate skills_config.json

# Run smoke tests
python -m ace.skills_builder.session_entrypoints.dev_cli test skills_config.json
```

### 3. Run a Skills Loop Session

```python
import asyncio
from pathlib import Path

from ace.playbook import Playbook
from ace.skills_builder.models import SkillsLoopConfig
from ace.skills_builder.session_entrypoints.agent_runtime import run_generator_with_skills

async def main():
    # Load configuration
    config = SkillsLoopConfig.model_validate_json(
        Path("skills_config.json").read_text()
    )

    # Load playbook
    playbook = Playbook.load("playbook.json")

    # Run generator with skills
    result = await run_generator_with_skills(
        prompt="Implement user authentication",
        playbook=playbook,
        config=config,
    )

    print(result)

asyncio.run(main())
```

### 4. Inspect Session Transcripts

```bash
# Launch TUI inspector
python -m ace.tools.skills_inspector docs/transcripts/2024-01-15_task_123.jsonl

# Export deltas without TUI
python -m ace.tools.skills_inspector transcript.jsonl --export
```

## Key Concepts

### Skills

Skills are Python async functions decorated with the `@tool` pattern (from codex exec). They expose ACE utilities to agents during sessions.

**Example Skill:**

```python
async def my_skill(args: Dict[str, Any]) -> Dict[str, Any]:
    """Skill description."""
    result = process_args(args)

    return {
        "content": [
            {"type": "text", "text": result}
        ]
    }
```

Register in `skills_config.json`:

```json
{
  "name": "my_skill",
  "version": "1.0.0",
  "description": "My custom skill",
  "entrypoint": "my_module:my_skill",
  "allowed_tools": ["read", "grep"]
}
```

### Custom Slash Commands

Define custom slash commands for each ACE agent role:

- **Generator**: `/plan`, `/scope`, `/playbook-gap`
- **Reflector**: `/review`, `/hypothesis`, `/coverage`
- **Curator**: `/accept-delta`, `/reject-delta`, `/document`
- **Subagent**: `/delegate`, `/handoff`, `/converge`, `/fork`

See `docs/skills_builder/slash_commands/` for full specifications.

### Closed Cycle Automation

Enable `skills_loop_closed_cycle: true` in config to run the full development loop automatically:

1. **Plan**: Synthesize task plan from objective (gpt-5)
2. **Build**: Execute plan with Codex Exec tools (acceptEdits mode)
3. **Test**: Run pytest with coverage enforcement
4. **Review**: Reflector/Curator analyze and accept/reject deltas
5. **Document**: Generate summary with test results and artifacts

### Test Runner Integration

Tests run automatically in the Test phase:

```bash
pytest -q --maxfail=1 --disable-warnings --json-report --cov=ace --cov-branch
```

Coverage thresholds (default: branch ≥ 80%, lines ≥ 85%) are enforced. Failures block delta acceptance.

**Dry-run mode** (for expensive suites):

```python
test_result = runner.run_tests(dry_run=True)
```

### Observability

Structured JSON logs with curator-visible fields:

```json
{
  "timestamp": "2024-01-15T10:30:45.123Z",
  "level": "INFO",
  "session_id": "session_abc123",
  "event_type": "tool_invocation",
  "tool_name": "playbook_diff",
  "tool_status": "success",
  "duration_ms": 120.5,
  "permission_mode": "plan",
  "phase": "build",
  "curator_visibility": true
}
```

Metrics are collected per session and exportable:

```python
from ace.skills_builder.observability import MetricsCollector

collector = MetricsCollector(session_id)
collector.record_tool_invocation("playbook_diff", "success", 120.5)
collector.export_json(Path("metrics.json"))
```

## Integration with ACE Roles

### Generator

```python
from ace.skills_builder.session_entrypoints.agent_runtime import run_generator_with_skills

result = await run_generator_with_skills(
    prompt="Add error handling to API client",
    playbook=playbook,
    config=skills_config,
    max_bullets=20,
)
```

The Generator receives:
- System prompt with playbook context
- Access to all registered skills
- Custom slash commands (`/plan`, `/scope`, `/playbook-gap`)

### Reflector

```python
from ace.skills_builder.session_entrypoints.agent_runtime import run_reflector_with_skills

result = await run_reflector_with_skills(
    task_result=generator_result,
    feedback="Test failed: null pointer exception",
    playbook=playbook,
    config=skills_config,
)
```

The Reflector receives:
- Trajectory events from Generator
- Analysis tools (`analyze_trajectory`)
- Custom slash commands (`/review`, `/hypothesis`, `/coverage`)
- Read-only permissions (`plan` mode)

### Curator

```python
from ace.skills_builder.session_entrypoints.agent_runtime import run_curator_with_skills

result = await run_curator_with_skills(
    reflector_result=reflector_result,
    playbook=playbook,
    config=skills_config,
)
```

The Curator receives:
- Reflector classifications
- Delta tools for playbook updates
- Custom slash commands (`/accept-delta`, `/reject-delta`, `/document`)
- Permission escalation to `acceptEdits` when accepting deltas

## Session Lifecycle

1. **Initialize**: Load skills config and playbook
2. **Enter Skills Loop**: Call `enter_skill_loop()` to get session metadata
3. **Execute Phases**: Run Plan → Build → Test → Review → Document
4. **Write Transcript**: Stream events to JSONL
5. **Collect Metrics**: Record tool usage, phase timings, coverage deltas
6. **Finalize**: Generate `ClosedCycleSummary` document

## Inspector Usage

The Skills Inspector is a Textual TUI for replaying sessions:

**Launch:**
```bash
python -m ace.tools.skills_inspector docs/transcripts/session_abc123.jsonl
```

**Keyboard Shortcuts:**
- `q` - Quit
- `s` - Toggle slash command filter
- `e` - Export deltas to JSON
- `←/→` - Switch tabs (Timeline / Context / Skills)

**Export Mode:**
```bash
python -m ace.tools.skills_inspector transcript.jsonl --export
```

Exports to `ace/playbook_deltas/<session_id>.json`.

## Testing

Run integration tests:

```bash
# All skills builder tests
python -m unittest discover -s ace/skills_builder/tests -v

# Specific test module
python -m unittest ace.skills_builder.tests.test_registry

# With coverage
pytest ace/skills_builder/tests/ --cov=ace.skills_builder --cov-report=html
```

## Configuration Reference

### SkillsLoopConfig

```python
class SkillsLoopConfig(BaseModel):
    enabled: bool                          # Feature flag
    registry: List[SkillDescriptor]        # Registered skills
    session: AgentSessionConfig            # Session settings
    hook_logging: bool                     # Enable transcript capture
    coverage_thresholds: Dict[str, float]  # Test coverage requirements
    custom_commands: List[SlashCommandConfig]  # Custom slash commands
    skills_loop_closed_cycle: bool         # Enable automation loop
```

### AgentSessionConfig

```python
class AgentSessionConfig(BaseModel):
    model: Literal["gpt-5", "gpt-4o"]      # Reasoning model
    codex_tools_enabled: bool              # Allow Codex Exec tools
    permission_mode: PermissionMode        # "plan" | "acceptEdits" | "bypassPermissions"
    fork_session: bool                     # Enable trajectory branching
```

## Best Practices

1. **Start in Plan Mode**: Begin sessions with `permission_mode: "plan"` (read-only)
2. **Escalate Carefully**: Only use `acceptEdits` in Curator after proof validation
3. **Set Coverage Thresholds**: Enforce minimum branch (≥ 80%) and line (≥ 85%) coverage
4. **Use Dry-run for Expensive Tests**: Set `dry_run: true` for slow test suites
5. **Tag Bullets**: Apply meaningful tags for `get_relevant_bullets()` filtering
6. **Inspect Transcripts**: Review JSONL transcripts to debug failed sessions
7. **Export Metrics**: Collect session metrics for curator dashboards
8. **Version Skills**: Use semver for skill descriptors to track evolution

## Troubleshooting

**Skill not loading:**
- Check entrypoint format: `module.path:function_name`
- Verify module is importable: `python -c "import module.path"`
- Run validation: `dev_cli validate config.json`

**Tests failing:**
- Check pytest is installed: `pip install pytest pytest-cov`
- Verify coverage plugin: `pip install pytest-json-report`
- Run with verbose: `pytest -v`

**Inspector crashes:**
- Install Textual: `pip install textual`
- Check transcript format: must be valid JSONL
- Try export mode: `--export` flag

**Permission errors:**
- Verify `permission_mode` matches operation requirements
- Curator needs `acceptEdits` for `/accept-delta`
- Use `plan` for all read-only operations

## Contributing

To add a new skill:

1. Scaffold with dev CLI:
   ```bash
   python -m ace.skills_builder.session_entrypoints.dev_cli scaffold my_skill
   ```

2. Implement skill logic in generated file

3. Add descriptor to `skills_config.json`

4. Test with:
   ```bash
   python -m ace.skills_builder.session_entrypoints.dev_cli test skills_config.json
   ```

5. Add integration tests in `ace/skills_builder/tests/`

## References

- [ACE Skills Plan](../../docs/ACEskills_plan.md) - Full specification
- [Generator Slash Commands](../../docs/skills_builder/slash_commands/generator.md)
- [Reflector Slash Commands](../../docs/skills_builder/slash_commands/reflector.md)
- [Curator Slash Commands](../../docs/skills_builder/slash_commands/curator.md)
- [Subagent Slash Commands](../../docs/skills_builder/slash_commands/subagent.md)
- [Codex Exec Documentation](https://raw.githubusercontent.com/openai/codex/main/docs/exec.md)

## License

See repository root LICENSE file.
