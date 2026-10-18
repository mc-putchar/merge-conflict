# Case study

Case ID: CS-FAILURE-02
Classification: failure
Run record: artifacts/agent/runs/fail-02-ocr-f-s-ambiguity.json
Code revision: e17a278a6a4033d22118d5d4910841f2e9f2d2eb

## Question

Compare the 1771 entry for 'Efential Oil of Fuerin' with modern essential oils in Wikipedia.

## Evidence

- **Britannica Source Pages:** britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:1939
- **Wikipedia Page ID:** Unmatched (Revision: N/A)
- **Tools Called:** challenge_find_entry
- **Source Excerpt / Raw Output Preview:**
> Extracted title: '536 Efential oil of Fuerin leaves'. Historical long-s ('f' for 's') was misread in the headword, causing BM25 search on Wikipedia to retrieve zero relevant candidates.

## Result

### What the agent did
The extraction pipeline failed to normalize the OCR long-s error in the title, leading to an empty candidate list in Wikipedia BM25 retrieval.

### Classification rationale (failure)
Classified as retrieval failure: valid historical topic ('Essential oil of Rue') was rejected because OCR distortion degraded keyword query generation.

### Limitations and boundaries
Requires multimodal Super VL visual headword correction or phonetic historical spell-checking prior to BM25 query construction.
