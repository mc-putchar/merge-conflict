# Case study

Case ID: CS-SUCCESS-02
Classification: success
Run record: artifacts/agent/runs/01-how-many-of-the-extracted-britannica-ent.json
Code revision: e17a278a6a4033d22118d5d4910841f2e9f2d2eb

## Question

How many of the extracted Britannica entries could not be compared, and for what reasons? Use the coverage tool and report the recorded numbers.

## Evidence

- **Britannica Source Pages:** Corpus Accounting over all 100 scans
- **Wikipedia Page ID:** N/A (Revision: N/A)
- **Tools Called:** tool_describe, challenge_check_coverage
- **Source Excerpt / Raw Output Preview:**
> Total extracted entries: 95. Compared: 74. Excluded: 21. Exclusion breakdown: 5 entries excluded due to short_or_blank_text (illustration plates); 16 entries excluded due to unmatched (sub-threshold Wikipedia candidate similarity).

## Result

### What the agent did
Hermes queried challenge_check_coverage and faithfully reported the exact numbers from the comparison audit without guessing.

### Classification rationale (success)
The agent strictly preserved evidence accounting, accurately distinguishing between blank/plate scans and sub-threshold retrieval matches.

### Limitations and boundaries
Counts are deterministic and pinned to the 100-scan manifest and calibrated -4.5 reranker threshold.
