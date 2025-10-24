---
name: ace-playbook
description: Export the current ACE playbook as a Claude agent skill.
usage: /ace-playbook output_dir=<path>
allowed-tools:
  - python
setting-sources:
  - project
  - user
---

Use this command to call `python scripts/export_playbook_skill.py` and package
the active playbook into a Claude skill folder. The resulting `SKILL.md` and
`playbook.json` can be imported into Claude as a reusable agent skill.

Parameters:
- `output_dir`: Target directory for the skill bundle.
- `title`: Optional override for the skill title.
- `description`: Optional override for the skill description.
