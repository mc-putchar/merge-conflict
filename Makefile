.PHONY: help install doctor doctor-live data-show data-fetch extract match compare agent site evaluate pipeline test serve frontend-dev frontend-build

# Default target displays available commands
help:
	@echo "Nemotron Agentic AI Challenge Commands:"
	@echo "  make install        - Install pinned Python dependencies using uv"
	@echo "  make doctor         - Run offline setup check"
	@echo "  make doctor-live    - Run live check for remote models and endpoints"
	@echo "  make data-show      - Display pinned Britannica manifest metadata"
	@echo "  make data-fetch     - Fetch the 100 pinned Britannica scans"
	@echo "  make extract        - Run extraction and copperplate recovery stage"
	@echo "  make match          - Run candidate retrieval and reranking stage"
	@echo "  make compare        - Run lexical and topic comparison stage"
	@echo "  make agent          - Run Hermes comparison agent queries"
	@echo "  make site           - Build compiled LaTeX files and SvelteKit site"
	@echo "  make evaluate       - Generate 6 case studies and submission report"
	@echo "  make pipeline       - Execute all stages sequentially"
	@echo "  make test           - Run full pytest test suite"
	@echo "  make serve          - Serve the static website locally on port 8088"
	@echo "  make frontend-dev   - Start SvelteKit development server"
	@echo "  make frontend-build - Build SvelteKit static application"

install:
	uv sync --locked

doctor:
	uv run nemotron-challenge doctor --offline

doctor-live:
	uv run nemotron-challenge doctor --live

data-show:
	uv run nemotron-challenge data show

data-fetch:
	uv run nemotron-challenge data fetch

extract:
	uv run nemotron-challenge run extract

match:
	uv run nemotron-challenge run match

compare:
	uv run nemotron-challenge run compare

agent:
	uv run nemotron-challenge run agent

site:
	uv run nemotron-challenge run site

evaluate:
	uv run nemotron-challenge run evaluate

pipeline: extract match compare agent site evaluate

test:
	uv run pytest

serve:
	@echo "Serving static deliverables at http://localhost:8088"
	python3 -m http.server 8088 --bind 0.0.0.0 --directory artifacts/site

frontend-dev:
	cd frontend && pnpm run dev

frontend-build:
	cd frontend && pnpm run build
