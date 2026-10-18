---
name: evidence-check
description: Audit run artifacts and derived records against the project's evidence rules — raw vs derived separation, page IDs, revision IDs, checksums, citations, and inference labels. Use before committing results, after a pipeline run, or when preparing the evaluate stage.
allowed-tools:
  - exec
  - read
  - grep
  - glob
---

# Evidence Check

Audit the team's artifacts against the evidence rules in `AGENTS.md`.

## What to check

1. **Separation.** Raw source scans, model output, and derived text are in
   separate files or fields. Confirm derived records never overwrite raw data.
2. **Identifiers.** Each derived record keeps its page ID, article revision ID,
   and source checksum. Flag records that lack them.
3. **Failures.** Failed runs are recorded with error details, not silently
   dropped or replaced with invented output.
4. **Citations.** Each factual comparison cites its source (page ID or article
   revision). Flag unsupported claims.
5. **Inference labels.** Anything the agent inferred is labeled as an
   inference, not presented as source fact.
6. **Traceability.** The three success cases and three failure cases each map
   to a saved run. A planned test does not count as a completed test.
7. **Secrets.** No API keys, caches, or private cloud settings appear in
   tracked files.

## Where to look

- `data/raw/` and `data/cache/` for source scans and checksums
- `artifacts/`, `runs/`, `reports/` for run output and derived records
- `src/nemotron_challenge/contracts.py` for the record fields

## Report

List each rule as pass, fail, or not applicable. For each fail, name the file
and the missing or broken field. Do not fix the data. Report first.
