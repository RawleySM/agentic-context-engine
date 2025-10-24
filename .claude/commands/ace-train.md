---
name: ace-train
description: Train the Agentic Context Engine with Claude sub-agents.
usage: /ace-train dataset_path=<path> epochs=3
allowed-tools:
  - python
setting-sources:
  - project
  - user
---

Run offline adaptation with Claude-managed Generator, Reflector, and Curator
agents. The command invokes `python scripts/run_local_adapter.py` with the
provided dataset path.

Parameters:
- `dataset_path`: JSONL file with questions, context, and optional ground truth.
- `epochs`: Number of offline training epochs to run (default: 3).

Example invocation:
```
/ace-train dataset_path=data/questions.jsonl epochs=2
```
