"""Teams implement these stages with their coding agents."""
from pathlib import Path
from typing import Any

from .config import Settings

STAGES = ("extract", "match", "compare", "agent", "site", "evaluate")


def _unfinished(stage: str) -> None:
    raise NotImplementedError(
        f"TODO: implement the {stage} milestone. Read docs/milestones.md#{stage}. "
        "The starter has no result for this stage."
    )


import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import sys

from .clients import ParseClient
from .data import load_manifest
from .extraction import parse_page, record_provenance, segment_entries
from .storage import LanceArtifactStore


def extract(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Extract entry text, segment headwords, and store provenance records."""
    raw_dir = Path("data/raw/britannica")
    cache_dir = Path(os.environ.get("PARSE_CACHE_DIR", "data/cache/parse"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    extract_dir = Path(work_dir) / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    pages_meta = manifest.get("pages", [])
    pages_by_id = {page["page_id"]: page for page in pages_meta}

    def process_one_scan(page_meta: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        filename = page_meta["filename"]
        cache_path = cache_dir / f"{filename}.json"
        if cache_path.is_file():
            try:
                raw_json = json.loads(cache_path.read_text(encoding="utf-8"))
                return page_meta, raw_json
            except (json.JSONDecodeError, OSError):
                pass

        scan_path = raw_dir / filename
        if not scan_path.is_file():
            raise FileNotFoundError(f"Scan file missing: {scan_path}")

        image_bytes = scan_path.read_bytes()
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:image/jpeg;base64,{encoded}"

        try:
            with ParseClient(settings.parse_base_url, settings.parse_api_key) as client:
                raw_json = client.parse(data_url)
        except Exception as exc:
            # Capture error details without inventing fake results
            raw_json = {
                "status": "failed",
                "error": str(exc),
                "choices": [],
            }

        temp_cache = cache_dir / f".tmp_{filename}.json"
        temp_cache.write_text(json.dumps(raw_json, indent=2), encoding="utf-8")
        temp_cache.replace(cache_path)
        return page_meta, raw_json

    # Fetch/load parse output concurrently (bounded to 3 workers for remote rate limits)
    results_map: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_one_scan, page): page["page_id"] for page in pages_meta}
        for future in as_completed(futures):
            page_meta, raw_json = future.result()
            results_map[page_meta["page_id"]] = raw_json

    # Parse and structure pages in deterministic manifest order
    parsed_pages = []
    failed_scans = []
    for page_meta in pages_meta:
        raw_json = results_map[page_meta["page_id"]]
        if raw_json.get("status") == "failed":
            failed_scans.append({
                "page_id": page_meta["page_id"],
                "filename": page_meta["filename"],
                "row_index": page_meta["row_index"],
                "error": raw_json.get("error", "unknown extraction error"),
            })
        else:
            parsed = parse_page(page_meta, raw_json)
            parsed_pages.append(parsed)

    # Segment entries and join multi-page continuations
    entries = segment_entries(parsed_pages)

    # Persist extracted entries and failed scans to artifacts
    entries_payload = [e.model_dump() for e in entries]
    entries_file = extract_dir / "entries.json"
    entries_file.write_text(json.dumps(entries_payload, indent=2), encoding="utf-8")

    for entry in entries:
        entry_file = extract_dir / f"{entry.entry_id}.json"
        entry_file.write_text(entry.model_dump_json(indent=2), encoding="utf-8")

    failed_file = extract_dir / "failed_scans.json"
    failed_file.write_text(json.dumps(failed_scans, indent=2), encoding="utf-8")

    # Persist provenance records to LanceDB
    store = LanceArtifactStore(settings.db_path)
    records_saved = record_provenance(store, entries, pages_by_id, manifest, extract_dir)

    # Persist failure artifact records into LanceDB for traceability
    from .contracts import ArtifactRecord, SourceReference
    dataset = manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated")
    revision = manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443")
    source_url = manifest.get("source_url", "")
    license_spdx = manifest.get("license", {}).get("spdx", "CC0-1.0")

    for failed in failed_scans:
        pmeta = pages_by_id[failed["page_id"]]
        store.put(ArtifactRecord(
            record_id=f"extract:failed:{failed['row_index']}",
            stage="extract",
            sources=[
                SourceReference(
                    dataset=dataset,
                    dataset_revision=revision,
                    source_id=failed["page_id"],
                    source_url=source_url,
                    content_sha256=pmeta.get("image_sha256", "0" * 64),
                    license=license_spdx,
                )
            ],
            artifact_path=str(failed_file),
            metadata={
                "status": "failed",
                "page_id": failed["page_id"],
                "row_index": failed["row_index"],
                "error": failed["error"],
            },
        ))
        records_saved += 1

    return {
        "stage": "extract",
        "status": "completed",
        "scans_total": len(pages_meta),
        "scans_successful": len(parsed_pages),
        "scans_failed": len(failed_scans),
        "failed_scans": failed_scans,
        "entries_extracted": len(entries),
        "continuations": sum(1 for e in entries if e.is_continuation),
        "total_characters": sum(e.character_count for e in entries),
        "provenance_records_saved": records_saved,
        "artifacts_dir": str(extract_dir),
        "database_path": str(settings.db_path),
    }


from .clients import ChatClient, RetrievalClient, WikiClient
from .matching import (
    MatchResult,
    evaluate_match_decision,
    fetch_full_article_verified,
    generate_search_queries,
    record_match_provenance,
    rerank_candidates_multimodal,
    rerank_candidates_text,
    retrieve_candidates,
)


def match(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Find and verify Wikipedia articles matching extracted Britannica entries."""
    work_dir = Path(work_dir)
    extract_file = work_dir / "extract" / "entries.json"
    if not extract_file.is_file():
        # Fall back to root artifacts if work_dir is different
        alt_extract = Path("artifacts/extract/entries.json")
        if alt_extract.is_file():
            extract_file = alt_extract
        else:
            raise FileNotFoundError(f"Extracted entries not found at {extract_file}. Run extract stage first.")

    raw_dir = Path("data/raw/britannica")
    query_cache_dir = Path(os.environ.get("QUERY_CACHE_DIR", "data/cache/queries"))
    wiki_cache_dir = Path(os.environ.get("WIKI_CACHE_DIR", "data/cache/wikipedia"))
    match_dir = work_dir / "match"
    match_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    pages_by_id = {page["page_id"]: page for page in manifest.get("pages", [])}

    entries = json.loads(extract_file.read_text(encoding="utf-8"))

    # Initialize clients
    wiki_client = WikiClient(settings.wikipedia_api_url)

    chat_client = None
    if settings.super_base_url and settings.super_api_key:
        try:
            chat_client = ChatClient(settings.super_base_url, settings.super_api_key, settings.super_model)
        except Exception:
            chat_client = None

    retrieval_client = None
    if settings.retrieval_base_url:
        try:
            rc = RetrievalClient(settings.retrieval_base_url, settings.retrieval_api_key)
            rc.verify_models()
            retrieval_client = rc
        except Exception:
            retrieval_client = None

    store = LanceArtifactStore(settings.db_path)

    def process_one_entry(entry: dict[str, Any]) -> MatchResult:
        entry_id = entry["entry_id"]
        title = entry["title"]
        text = entry.get("text", "")
        source_pages = entry.get("source_pages", [])

        # 1. Generate search queries
        queries = generate_search_queries(entry_id, title, text, chat_client, query_cache_dir)

        # 2. Retrieve lexical candidates from Wikipedia BM25 API
        candidates = retrieve_candidates(queries, wiki_client, top_k_per_query=8)

        # 3. Two-stage reranking (if retrieval service is online)
        if retrieval_client and candidates:
            candidates = rerank_candidates_text(title, text, candidates, retrieval_client)

            scan_paths = []
            for pid in source_pages:
                pmeta = pages_by_id.get(pid)
                if pmeta:
                    scan_paths.append(raw_dir / pmeta["filename"])
            candidates = rerank_candidates_multimodal(candidates, text, scan_paths, retrieval_client)

        # 4. Evaluate acceptance decision
        matched, top_cand, status, rationale = evaluate_match_decision(candidates, threshold=0.0)

        # 5. For accepted matches, fetch complete verified Wikipedia article
        article_sha256 = None
        if matched and top_cand:
            try:
                article = fetch_full_article_verified(top_cand.page_id, wiki_client, wiki_cache_dir)
                article_sha256 = article.provenance.text_sha256
            except Exception as exc:
                # If article retrieval fails, flag match reason
                status = "accepted_unverified_article"
                rationale += f" (Article fetch warning: {exc})"

        result = MatchResult(
            entry_id=entry_id,
            britannica_title=title,
            source_pages=source_pages,
            matched=matched,
            status=status,
            selected_candidate=top_cand if matched else None,
            all_candidates=candidates,
            article_text_sha256=article_sha256,
            decision_rationale=rationale,
        )

        # Persist individual match result artifact
        (match_dir / f"{entry_id}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    # Run entry matching concurrently across entries
    results_by_id: dict[str, MatchResult] = {}
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(process_one_entry, entry): entry["entry_id"] for entry in entries}
        for future in as_completed(futures):
            res = future.result()
            results_by_id[res.entry_id] = res

    # Restore deterministic order matching input entries
    results = [results_by_id[entry["entry_id"]] for entry in entries]

    # Persist dual-source provenance to LanceDB
    for result in results:
        record_match_provenance(store, result, manifest, pages_by_id, work_dir)

    # Save summary matches and unmatched lists
    matches_list = [r.model_dump() for r in results if r.matched]
    unmatched_list = [r.model_dump() for r in results if not r.matched]

    (match_dir / "matches.json").write_text(json.dumps(matches_list, indent=2), encoding="utf-8")
    (match_dir / "unmatched.json").write_text(json.dumps(unmatched_list, indent=2), encoding="utf-8")

    return {
        "stage": "match",
        "status": "completed",
        "entries_total": len(entries),
        "matches_accepted": len(matches_list),
        "matches_rejected": len(unmatched_list),
        "retrieval_service_active": retrieval_client is not None,
        "artifacts_dir": str(match_dir),
        "database_path": str(settings.db_path),
    }


def compare(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: define your vocabulary, frequency, or topic comparison."""
    _unfinished("compare")


def agent(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: implement your Hermes tools and evidence checks."""
    _unfinished("agent")


def site(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: build your LaTeX documents and static website."""
    _unfinished("site")


def evaluate(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: review your results and document successes and failures."""
    _unfinished("evaluate")
