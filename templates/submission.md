# Submission

Team: TODO
Repository URL and commit: TODO
Video URL, 3 to 5 minutes: TODO
Static website URL: TODO
Compiled LaTeX documents: TODO

## Reproduce the run

Setup and run commands:

```sh
uv sync --locked
cp .env.example .env   # fill in SUPER_API_KEY and service URLs; never commit .env
uv run nemotron-challenge doctor --offline
uv run nemotron-challenge data show
uv run nemotron-challenge data fetch
uv run nemotron-challenge doctor --live
uv run nemotron-challenge run extract
uv run nemotron-challenge run match
uv run nemotron-challenge run compare
uv run nemotron-challenge run agent   # provisions data/hermes and runs the Hermes query set
uv run pytest
```

Tested versions:

- Python 3.12.12 (project venv, `uv` 0.9.26)
- Hermes Agent v0.22.2 (2026.9.24, local checkout d923a5eb487a, runs on Python 3.14.7)
- httpx 0.28.1, pydantic 2.14.1, python-dotenv 1.2.4, lancedb 0.40.0,
  pyarrow 21.0.0, huggingface-hub 2.2.0, numpy 2.5.4, pytest 9.1.1
- Tested code revision: git `ee7131e` plus the milestone 3–4 changes in the working tree

Model IDs, revisions, and serving settings:

| Role | Model | Revision / endpoint | Settings |
| --- | --- | --- | --- |
| Page extraction | `nvidia/nemotron-3.5-parse` | Shared organizer endpoint (`PARSE_BASE_URL`) | `temperature 0`, `skip_special_tokens false`, `add_special_tokens false`, `max_tokens 8744` |
| Embedding | `nvidia/llama-nemotron-embed-vl-1b-v2` | revision `582e3bf72aee355e3c59ed89de53543c5b0657ee`, team Nebius deployment (`RETRIEVAL_BASE_URL`) | 2048 dimensions, normalized vectors, `input_type` query/document |
| Reranking | `nvidia/llama-nemotron-rerank-vl-1b-v2` | revision `b8a9987b05b75db5ad949c825cbcbf6eb7c48b5a`, team Nebius deployment (`RETRIEVAL_BASE_URL`) | `score_type` logit/raw_logit |
| Agent reasoning | `nvidia/Nemotron-3.5-Super-VL` | Nebius Token Factory `https://api.tokenfactory.nebius.com/v1` via Hermes `chat_completions` transport | `extra_body.temperature: 0` |

Source data pins:

- Britannica manifest sha256: `adb0d9a4cf71aff85817878e3c993fd87bcaf2c45a2a65b1f173321f5f83d8b2`
  (`NationalLibraryOfScotland/encyclopaedia_britannica_illustrated`, revision
  `309f765b1ecc83e0a7f7762e44b4a927a7555443`, 100 pages)
- Wikipedia snapshot: `wikimedia/structured-wikipedia`, revision
  `417c267bb457fa645c22eb3b5c77764963194c70` (7,182,883 canonical articles, shared BM25 index)

## Results

TODO: Report scan coverage, extraction failures, entry count, and article associations.
TODO: Describe the comparison method and text exclusions.
TODO: Link the analysis, plots, and source records.

## Case studies

TODO: Link three success cases and three failure cases.
Use `case-study.md` for each case.
Retain failed attempts and describe any repairs in separate run records.

## Limits

TODO: Explain what was tested and what remains uncertain.
TODO: State known failure modes and possible next steps.
