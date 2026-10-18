---
name: milestone
description: Work through one challenge milestone stage (extract, match, compare, agent, site, evaluate) with the team — agree a method, implement it, replace the unfinished-stage guard, and run its checks. Use when the team picks a stage to build next.
allowed-tools:
  - exec
  - read
  - grep
  - glob
  - edit
  - write
---

# Milestone Runner

Work one stage of `docs/milestones.md` with the team. Stages: `extract`,
`match`, `compare`, `agent`, `site`, `evaluate`. Entry points live in
`src/nemotron_challenge/tasks.py`.

## Steps

1. Ask which stage the team wants, unless they named one.
2. Read the stage section in `docs/milestones.md` and the matching function
   in `tasks.py`. Read `AGENTS.md` rules that apply.
3. For each method choice the stage requires, explain the tradeoff and ask
   the team's preference before implementing. Do not pick silently.
4. Implement the chosen approach with small changes the team can inspect.
   Use the supplied clients in `clients.py` for transport. Keep page IDs,
   revision IDs, checksums, and raw model output in the saved records.
5. Replace the matching unfinished-stage guard in `tasks.py`.
6. Add tests for the chosen behavior. Run `uv run pytest`.
7. Run the stage: `uv run nemotron-challenge run <stage>`.
   Check real model replies for the expected model ID, completion status,
   and usable output. Save the run under `artifacts/` or `runs/`.
8. Record failures with their error details. Do not replace a failed call
   with an invented result.

## Stop conditions

- A model or service call fails twice with the same error: report and wait.
- The team has not chosen a required method: ask, do not assume.
- Fixture tests pass but real output is unchecked: say so. Fixtures prove
  setup, not OCR accuracy or retrieval quality.
