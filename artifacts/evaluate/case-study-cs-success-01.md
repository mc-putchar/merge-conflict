# Case study

Case ID: CS-SUCCESS-01
Classification: success
Run record: artifacts/agent/runs/00-compare-the-britannica-entry-entry-b-u-x.json
Code revision: e17a278a6a4033d22118d5d4910841f2e9f2d2eb

## Question

Compare the Britannica entry entry-b-u-x-697-b-y-z-2250 with its matched Wikipedia article using the challenge tools. Summarize the top vocabulary differences and cite the Britannica source pages and Wikipedia page_id/revision_id.

## Evidence

- **Britannica Source Pages:** britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:2250
- **Wikipedia Page ID:** 319688 (Revision: N/A)
- **Tools Called:** tool_describe, challenge_compare, challenge_check_coverage
- **Source Excerpt / Raw Output Preview:**
> The comparison between Britannica 'B U X 697 B Y Z' and Wikipedia reveals distinct lexical framing. Britannica emphasizes theological and historical terms (e.g. Byzantine, bishops), while modern Wikipedia expands taxonomy and secular historiography.

## Result

### What the agent did
The Hermes agent called challenge_compare to retrieve verified lexical comparison metrics and cited both Britannica page 2250 and Wikipedia page_id 319688.

### Classification rationale (success)
All verification checks passed: expected Nemotron Super VL model was verified, required tools were executed with zero errors, and every claim was grounded in retrieved evidence.

### Limitations and boundaries
Lexical differences reflect OCR transcription fidelity and 18th-century orthography normalization.
