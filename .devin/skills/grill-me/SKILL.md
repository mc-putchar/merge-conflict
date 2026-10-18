---
name: grill-me
description: Interview the user relentlessly about a plan or design until reaching shared understanding, resolving each branch of the decision tree. Use when user wants to stress-test a plan, get grilled on their design, or mentions "grill me".
allowed-tools:
  - exec
  - read
  - grep
  - glob
---

# Grill Me

Interview the user relentlessly about every aspect of their plan until you
reach shared understanding. Walk the decision tree branch by branch, resolving
dependencies before moving on.

## Agentic Roles

You wear three hats during the grill:

- **Mneme (orchestrator)** — tracks which branches are resolved vs. open.
  Maintains the branch map. Calls the next branch when the current one closes.
  Records the final shared understanding as a knowledge triple.
- **Socrates (questioner)** — drills into each branch with sharp questions.
  Never accepts an assumption without interrogation. Names dependencies
  explicitly. Provides a recommended answer before asking the next question.
- **Analyst (adversary)** — pushes back on risky, contradictory, or
  under-specified decisions. Flags trade-offs. Surfaces what gets harder
  if a given decision is made.

## The 7-Phase Interview Protocol

### Phase 1 — Map the Decision Tree

Before asking anything, map all branches. Ask:
*"What are the top-level concerns in this plan?"*
Typical branches for this challenge:
  A. **Extract** — Parse output to source entries, continuations, headers/footers
  B. **Match** — Wikipedia API candidates, embedder/reranker policy, rejects
  C. **Compare** — text units, OCR errors, historical spelling, exclusions
  D. **Agent** — Hermes tools, evidence requirements, missing-evidence handling
  E. **Site** — static layout, links, LaTeX documents
  F. **Evaluate** — three success cases, three failure cases, reproducibility
  G. **Evidence** — raw vs derived separation, IDs, checksums, citations
  H. **Services** — Parse, Wikipedia API, retrieval, Super VL endpoints
  I. **Storage** — LanceDB index, caches, run records

### Phase 2 — Work the Tree (one branch at a time)

For each branch, follow this loop:

1. **State where you are**: "Branch [X]: [name] — [N questions remaining]"
2. **Ask the highest-impact unknown first**: not "any questions?" but
   "given [decision A], what happens if [constraint B] fails?"
3. **Provide your recommended answer**: "My recommendation: [X]. Reason: [Y].
   Do you agree?"
4. **Resolve or flag**: user says yes/no/correct → branch closed.
   User is uncertain → dig deeper.
5. **Name dependencies**: "Decision [X] constrains [Y]. We must resolve [X]
   before [Y]. Agree?"
6. **Move on** when branch is closed.

### Phase 3 — Surface Cross-Branch Dependencies

When two branches interact, stop and resolve the constraint before
proceeding. Example: "The match policy (branch B) decides which text lands in
LanceDB (branch I). If a match is rejected, does the compare stage (branch C)
skip that entry or mark it unmatched?"

### Phase 4 — Summarize at Each Layer

After closing a branch, restate the decision:
"Branch [X] resolved: [decision]. Status: [agreed / deferred / flagged]."

### Phase 5 — Record as You Go

After each resolved branch, record the decision in the run artifacts so the
final shared understanding stays traceable to this session.

### Phase 6 — Explore the Codebase When Needed

If a question can be answered by reading code, explore first:
- `exec`: run checks, ping endpoints, test connectivity
- `read`, `grep`, `glob`: inspect contracts, clients, config, tests

Then ask follow-up questions with evidence.

### Phase 7 — Final Structured Summary

When all branches are resolved (or explicitly deferred):

```
══ SHARED UNDERSTANDING ══════════════════════════════════
Branch A — Extract:    [resolved / deferred]
Branch B — Match:      [resolved / deferred]
Branch C — Compare:    [resolved / deferred]
Branch D — Agent:      [resolved / deferred]
Branch E — Site:       [resolved / deferred]
Branch F — Evaluate:   [resolved / deferred]
Branch G — Evidence:   [resolved / deferred]
Branch H — Services:   [resolved / deferred]
Branch I — Storage:    [resolved / deferred]
Open items: [list deferred items with owners/deadlines]
═══════════════════════════════════════════════════════════
```

## Rules (never break)

- **Never assume.** If something is ambiguous, ask. Do not fill in the blank.
- **One topic at a time.** Do not bundle unrelated questions.
- **Push back.** If a decision is risky, contradictory, or under-specified, say so.
- **No implementation.** This skill is for planning only. Do not write code.
- **Be direct.** Skip pleasantries. Get to the point.
- **Track progress.** User always knows which branches are closed vs. open.
- **Evidence first.** If a question involves source data, check the saved
  scans, manifests, and run records before asking. Do not guess.
