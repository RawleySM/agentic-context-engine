---
name: ace-evaluate
description: Evaluate the ACE playbook using Claude-directed workflows.
usage: /ace-evaluate dataset_path=<path>
allowed-tools:
  - python
setting-sources:
  - project
  - user
---

Run `python scripts/run_questions.py` to execute the Generator-only pathway with
the current playbook snapshot. Results are streamed back to Claude for
inspection.

Parameters:
- `dataset_path`: JSONL evaluation set.
- `max_samples`: Optional cap on the number of questions to evaluate.

Example:
```
/ace-evaluate dataset_path=data/eval.jsonl max_samples=20
```
