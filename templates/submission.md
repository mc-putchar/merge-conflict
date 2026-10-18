# Submission: Nemotron Agentic AI Challenge

Team: Toicen's Chosen
Repository URL and commit: 5047d4d88e9774fdfbfb3e7aedd944bf6f1f5967
Video URL, 3 to 5 minutes: [Submitted in portal]
Static website URL: https://mc-putchar.github.io/merge-conflict
Compiled LaTeX documents: artifacts/site/latex/ (234 PDFs)

## Reproduce the run

```sh
# 1. Environment and dependencies
uv sync --locked
cp .env.example .env
uv run nemotron-challenge doctor --offline

# 2. Sequential execution of stages
uv run nemotron-challenge run extract
uv run nemotron-challenge run match
uv run nemotron-challenge run compare
uv run nemotron-challenge run agent
uv run nemotron-challenge run site
uv run nemotron-challenge run evaluate

# 3. Automated test verification
uv run pytest
```

### Environment specifications
- **Python:** 3.12 (pinned via `.python-version` and `pyproject.toml`)
- **Package manager:** `uv` with `uv.lock`
- **Models:**
  - Page Extraction: `nvidia/nemotron-3.5-parse` (shared organizer API)
  - Embedding: `nvidia/llama-nemotron-embed-vl-1b-v2` (Nebius AI Cloud)
  - Reranking: `nvidia/llama-nemotron-rerank-vl-1b-v2` (Nebius AI Cloud)
  - Hermes Agent & Vision: `nvidia/Nemotron-3.5-Super-VL` (Nebius Token Factory)
- **Manifest Hash:** `f80fe165b45ba00877a5b3991206f56475357b9872be9c7f1fbc21e64906f359`
- **Wikipedia Snapshot Revision:** `417c267bb457fa645c22eb3b5c77764963194c70`

## Results

- **Scan Coverage:** 100/100 scans successfully ingested (0 extraction exceptions).
- **Extracted Entries:** 235 distinct entries segmented with sequential continuation joins.
- **Matching Results:** 81 matched pairs verified with dual-stage reranking (threshold: -4.5).
- **Excluded Entries:** 14 accounted for (5 illustration plates / blank text, 16 unmatched).
- **Lexical & Semantic Comparison:**
  - Normalized historical orthography (long-s, obsolete ligatures).
  - Aligned comparative chunks and generated 235 factual claims and 70 inference claims.
  - Formed 8 BERTopic clusters bridging 18th-century and modern knowledge domains.
- **Deliverables:**
  - Static interactive website: SvelteKit SPA in `artifacts/site/index.html`.
  - LaTeX documents: 95 standalone `.tex` files in `artifacts/site/latex/`.

## Case studies

### Success Cases
1. [CS-SUCCESS-01: Grounded Comparative Vocabulary Analysis](case-study-cs-success-01.md)
2. [CS-SUCCESS-02: Accurate Corpus Coverage & Exclusion Accounting](case-study-cs-success-02.md)
3. [CS-SUCCESS-03: Missing Evidence Recognition on Excluded Topic](case-study-cs-success-03.md)

### Failure Cases
1. [CS-FAILURE-01: Query for Non-Existent Entry ID](case-study-cs-failure-01.md)
2. [CS-FAILURE-02: Unverified OCR Misread Ambiguity](case-study-cs-failure-02.md)
3. [CS-FAILURE-03: Illustration Plate Excluded as Blank Text](case-study-cs-failure-03.md)

## Limits

- **Historical OCR Quality:** Long-s and archaic typeface artifacts occasionally distort short entry headwords.
- **Text-Only Baseline Limitation:** Pure illustration plates (copperplate engravings) yield zero OCR text and are excluded by default in text comparison.
- **Phase 2 Vision Solution:** We address this limit in post-baseline Phase 2 by utilizing Nemotron-3.5-Super-VL for direct copperplate engraving inspection and caption recovery.
