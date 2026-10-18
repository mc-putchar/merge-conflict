---
name: doctor
description: Run the challenge setup checks, list unfinished stages, and report failures without inventing results. Use when checking environment health, after editing .env, or before starting a milestone stage.
allowed-tools:
  - exec
  - read
---

# Doctor

Run the scaffold's checks and report results verbatim.

1. Run `uv run nemotron-challenge doctor --offline`.
   This checks installed packages and configured settings without network access.
2. If the team has filled in `.env`, run `uv run nemotron-challenge doctor --live`.
   This checks service catalogs and readiness. It does not run inference.
3. Run `uv run nemotron-challenge stages` to list unfinished milestones.
4. Run `uv run pytest` to run the test suite.

## Report

- State each check's status (`ok`, `missing`, `failed`, `not_tested`) and detail.
- For `missing` settings, name the `.env` variable that needs a value.
- For `failed` service checks, quote the error detail.
- Do not replace a failed model or service call with an invented result.
  Record the error and stop.
