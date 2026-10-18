# Case study

Case ID: CS-FAILURE-03
Classification: failure
Run record: artifacts/agent/runs/fail-03-illustration-plate-exclusion.json
Code revision: e17a278a6a4033d22118d5d4910841f2e9f2d2eb

## Question

Compare the anatomical or machinery engravings on scan row 2077 with modern Wikipedia diagrams.

## Evidence

- **Britannica Source Pages:** britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:2077
- **Wikipedia Page ID:** None (Revision: N/A)
- **Tools Called:** challenge_compare
- **Source Excerpt / Raw Output Preview:**
> Entry: 'entry-britannica-volume-149983206-row-2077-2077', character_count: 0. Excluded from comparison with reason: 'short_or_blank_text'.

## Result

### What the agent did
The baseline pipeline treated the copperplate illustration scan as an empty text page, completely omitting visual content from comparison.

### Classification rationale (failure)
Classified as pipeline coverage failure: the baseline pipeline cannot compare visual plates without multimodal vision enrichment.

### Limitations and boundaries
Motivates the post-baseline Phase 2 extension: using Nemotron Super VL to inspect and caption plates directly.
