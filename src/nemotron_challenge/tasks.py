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

        # 4. Evaluate acceptance decision using calibrated reranker threshold
        match_threshold = float(os.environ.get("MATCH_THRESHOLD", "-4.5"))
        matched, top_cand, status, rationale = evaluate_match_decision(candidates, threshold=match_threshold)

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
            selected_candidate=top_cand,
            all_candidates=candidates,
            article_text_sha256=article_sha256,
            decision_rationale=rationale,
        )

        # Persist individual match result artifact
        (match_dir / f"{entry_id}.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
        return result

    # Run entry matching concurrently across entries (bounded to 2 workers for single GPU queue)
    results_by_id: dict[str, MatchResult] = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
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
    """Compare matched Britannica entries with verified Wikipedia articles."""
    import math

    from .comparison import (
        MIN_ENTRY_CHARS, MIN_ENTRY_TOKENS,
        CorpusComparisonSummary, EntryComparison, ExclusionRecord,
        align_chunks, britannica_text_sha256, compute_corpus_idf, compute_corpus_topics,
        compute_lexical_comparison, generate_cited_claims, generate_comparison_plots,
        normalize_historical_text, record_compare_provenance, tokenize, verify_plot_counts,
    )

    work_dir = Path(work_dir)
    extract_file = work_dir / "extract" / "entries.json"
    if not extract_file.is_file():
        alt_extract = Path("artifacts/extract/entries.json")
        if alt_extract.is_file():
            extract_file = alt_extract
        else:
            raise FileNotFoundError(f"Extracted entries not found at {extract_file}. Run extract stage first.")

    match_dir_source = work_dir / "match"
    matches_file = match_dir_source / "matches.json"
    unmatched_file = match_dir_source / "unmatched.json"
    if not matches_file.is_file():
        alt_match = Path("artifacts/match/matches.json")
        if alt_match.is_file():
            match_dir_source = Path("artifacts/match")
            matches_file = alt_match
            unmatched_file = match_dir_source / "unmatched.json"
        else:
            raise FileNotFoundError(f"Match results not found at {matches_file}. Run match stage first.")

    wiki_cache_dir = Path(os.environ.get("WIKI_CACHE_DIR", "data/cache/wikipedia"))
    claims_cache_dir = Path(os.environ.get("COMPARE_CACHE_DIR", "data/cache/comparisons"))
    compare_dir = work_dir / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest()
    pages_by_id = {page["page_id"]: page for page in manifest.get("pages", [])}

    entries = json.loads(extract_file.read_text(encoding="utf-8"))
    matches = {m["entry_id"]: m for m in json.loads(matches_file.read_text(encoding="utf-8"))}
    unmatched = json.loads(unmatched_file.read_text(encoding="utf-8")) if unmatched_file.is_file() else []
    status_by_entry = {m["entry_id"]: m.get("status", "unmatched") for m in unmatched}

    # Optional service clients. Comparison works offline with deterministic fallbacks.
    wiki_client = WikiClient(settings.wikipedia_api_url) if settings.wikipedia_api_url else None
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

    # Pass A: assemble comparable pairs and account for every excluded entry.
    exclusions: list[ExclusionRecord] = []
    pairs: list[tuple[dict[str, Any], dict[str, Any], Any]] = []
    for entry in entries:
        match = matches.get(entry["entry_id"])
        if match is None:
            exclusions.append(ExclusionRecord(
                entry_id=entry["entry_id"], britannica_title=entry["title"],
                source_pages=entry.get("source_pages", []), reason="unmatched",
                match_status=status_by_entry.get(entry["entry_id"], "unmatched"),
                character_count=entry.get("character_count", len(entry.get("text", ""))),
            ))
            continue
        raw_text = entry.get("text", "")
        if len(raw_text.strip()) < MIN_ENTRY_CHARS or len(tokenize(raw_text)) < MIN_ENTRY_TOKENS:
            exclusions.append(ExclusionRecord(
                entry_id=entry["entry_id"], britannica_title=entry["title"],
                source_pages=entry.get("source_pages", []), reason="short_or_blank_text",
                match_status=match.get("status", ""),
                character_count=len(raw_text.strip()),
            ))
            continue
        page_id = match["selected_candidate"]["page_id"]
        try:
            article = fetch_full_article_verified(page_id, wiki_client, wiki_cache_dir)
        except Exception:
            exclusions.append(ExclusionRecord(
                entry_id=entry["entry_id"], britannica_title=entry["title"],
                source_pages=entry.get("source_pages", []), reason="missing_wikipedia_article",
                match_status=match.get("status", ""),
                character_count=entry.get("character_count", len(raw_text)),
            ))
            continue
        pairs.append((entry, match, article))

    # Modern vocabulary arbitrates OCR f/s corrections; corpus stats feed log-odds.
    modern_vocab: set[str] = set()
    for _, _, article in pairs:
        modern_vocab.update(tokenize(article.text))

    normalized_docs: list[tuple[str, str, str, str]] = []  # (entry_id, side, raw, normalized)
    per_pair_norm: dict[str, tuple[str, str]] = {}
    per_pair_changes: dict[str, list[Any]] = {}
    for entry, _, article in pairs:
        brit_norm, changes = normalize_historical_text(entry["text"], modern_vocab)
        wiki_norm = article.text
        per_pair_norm[entry["entry_id"]] = (brit_norm, wiki_norm)
        per_pair_changes[entry["entry_id"]] = changes
        normalized_docs.append((entry["entry_id"], "britannica", entry["text"], brit_norm))
        normalized_docs.append((entry["entry_id"], "wikipedia", article.text, wiki_norm))

    all_tokens = [tokenize(doc[3]) for doc in normalized_docs]
    idf = compute_corpus_idf(all_tokens)
    background: dict[str, int] = {}
    for tokens in all_tokens:
        for token in tokens:
            background[token] = background.get(token, 0) + 1

    # Optional embedding similarity for whole documents (batched).
    embedding_cosine: dict[str, float] = {}
    if retrieval_client is not None:
        try:
            texts = [doc[3][:32000] for doc in normalized_docs]
            vectors = []
            for start in range(0, len(texts), 16):
                vectors.extend(retrieval_client.embed(texts[start:start + 16], "document"))
            for index in range(0, len(normalized_docs), 2):
                entry_id = normalized_docs[index][0]
                a, b = vectors[index], vectors[index + 1]
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a)) or 1.0
                nb = math.sqrt(sum(y * y for y in b)) or 1.0
                embedding_cosine[entry_id] = round(dot / (na * nb), 4)
        except Exception:
            embedding_cosine = {}

    # Pass B: per-pair metrics, aligned chunks, and cited claims.
    dropped_claims = 0
    comparisons: list[EntryComparison] = []
    for entry, match, article in pairs:
        entry_id = entry["entry_id"]
        brit_norm, wiki_norm = per_pair_norm[entry_id]
        changes = per_pair_changes[entry_id]

        metrics = compute_lexical_comparison(entry["text"], brit_norm, article.text, wiki_norm, idf, background)
        if entry_id in embedding_cosine:
            metrics.cosine_embedding = embedding_cosine[entry_id]

        aligned = align_chunks(brit_norm, article.text, retrieval_client)
        claims, dropped = generate_cited_claims(
            entry, article, metrics, changes, chat_client, claims_cache_dir, brit_norm,
        )
        dropped_claims += dropped

        brit_tokens = tokenize(brit_norm)
        wiki_tokens = tokenize(wiki_norm)
        comparisons.append(EntryComparison(
            entry_id=entry_id,
            britannica_title=entry["title"],
            source_pages=entry.get("source_pages", []),
            britannica_sha256=britannica_text_sha256(entry["text"]),
            britannica_raw_chars=len(entry["text"]),
            britannica_tokens=len(brit_tokens),
            britannica_unique_tokens=len(set(brit_tokens)),
            wikipedia_page_id=article.page_id,
            wikipedia_revision_id=article.revision_id,
            wikipedia_title=article.title,
            wikipedia_url=article.url,
            wikipedia_text_sha256=article.provenance.text_sha256,
            wikipedia_raw_chars=len(article.text),
            wikipedia_tokens=len(wiki_tokens),
            wikipedia_unique_tokens=len(set(wiki_tokens)),
            length_ratio=round(len(article.text) / max(len(entry["text"]), 1), 3),
            text_changes=changes,
            metrics=metrics,
            aligned_chunks=aligned,
            claims=claims,
        ))

    # Corpus topics over both sources, then assign topic ids/terms back to pairs.
    topic_map, topic_clusters = compute_corpus_topics(
        [(side, eid, norm) for eid, side, _, norm in normalized_docs], retrieval_client,
    )
    label_by_id = {c["topic_id"]: c["top_terms_britannica"][:3] for c in topic_clusters}
    for comp in comparisons:
        topic_id = topic_map.get(f"britannica:{comp.entry_id}")
        comp.topic_id = topic_id
        comp.topic_terms = label_by_id.get(topic_id, []) if topic_id is not None else []

    # Write artifacts: per-pair detail, aggregate lists, audit records, plots.
    for comp in comparisons:
        (compare_dir / f"{comp.entry_id}.json").write_text(comp.model_dump_json(indent=2), encoding="utf-8")

    all_changes = [
        {"entry_id": comp.entry_id, **record.model_dump()}
        for comp in comparisons for record in comp.text_changes
    ]
    (compare_dir / "comparisons.json").write_text(
        json.dumps([c.model_dump() for c in comparisons], indent=2), encoding="utf-8")
    (compare_dir / "exclusions.json").write_text(
        json.dumps([e.model_dump() for e in exclusions], indent=2), encoding="utf-8")
    (compare_dir / "text_changes.json").write_text(json.dumps(all_changes, indent=2), encoding="utf-8")
    (compare_dir / "topics.json").write_text(json.dumps(topic_clusters, indent=2), encoding="utf-8")

    plots_metadata = generate_comparison_plots(comparisons, exclusions, len(entries), compare_dir / "plots")
    plot_errors = verify_plot_counts(plots_metadata)

    exclusions_by_reason: dict[str, int] = {}
    for record in exclusions:
        exclusions_by_reason[record.reason] = exclusions_by_reason.get(record.reason, 0) + 1

    summary = CorpusComparisonSummary(
        entries_total=len(entries),
        compared_count=len(comparisons),
        excluded_count=len(exclusions),
        exclusions_by_reason=exclusions_by_reason,
        document_accounting_verified=not plot_errors,
        embedding_similarity_available=retrieval_client is not None,
        claims_factual=sum(1 for c in comparisons for claim in c.claims if claim.claim_type == "factual"),
        claims_inference=sum(1 for c in comparisons for claim in c.claims if claim.claim_type == "inference"),
        claims_dropped_unverifiable=dropped_claims,
        topics=topic_clusters,
        artifacts_dir=str(compare_dir),
        database_path=str(settings.db_path),
    )
    summary_path = compare_dir / "summary.json"
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")

    # Dual-source provenance for every compared pair plus the summary.
    store = LanceArtifactStore(settings.db_path)
    for comp in comparisons:
        record_compare_provenance(store, comp, manifest, pages_by_id, compare_dir / f"{comp.entry_id}.json")
    from .contracts import ArtifactRecord, SourceReference
    summary_sources = [
        SourceReference(
            dataset=manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated"),
            dataset_revision=manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443"),
            source_id="entries.json",
            source_url=manifest.get("source_url", ""),
            content_sha256=britannica_text_sha256(extract_file.read_text(encoding="utf-8")),
            license=manifest.get("license", {}).get("spdx", "CC0-1.0"),
        ),
        SourceReference(
            dataset="wikimedia/structured-wikipedia",
            dataset_revision="417c267bb457fa645c22eb3b5c77764963194c70",
            source_id="matches.json",
            source_url="",
            content_sha256=britannica_text_sha256(matches_file.read_text(encoding="utf-8")),
            license="CC-BY-SA-4.0",
        ),
    ]
    store.put(ArtifactRecord(
        record_id="compare:summary",
        stage="compare",
        sources=summary_sources,
        artifact_path=str(summary_path),
        metadata={
            "entries_total": summary.entries_total,
            "compared_count": summary.compared_count,
            "excluded_count": summary.excluded_count,
            "exclusions_by_reason": summary.exclusions_by_reason,
            "document_accounting_verified": summary.document_accounting_verified,
            "claims_factual": summary.claims_factual,
            "claims_inference": summary.claims_inference,
        },
    ))

    result = summary.model_dump()
    result["plot_errors"] = plot_errors
    return result


def agent(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Run the Hermes comparison agent over saved evidence and record each run."""
    import subprocess

    from .agent import (
        ensure_hermes_profile, record_agent_provenance, run_agent_query,
        slugify, verify_run,
    )

    work_dir = Path(work_dir)
    compare_summary_path = work_dir / "compare" / "summary.json"
    if not compare_summary_path.is_file():
        alt = Path("artifacts/compare/summary.json")
        if alt.is_file():
            compare_summary_path = alt
        else:
            raise FileNotFoundError(
                f"Compare results not found at {compare_summary_path}. Run compare stage first.")

    artifacts_dir = work_dir if (work_dir / "compare").is_dir() else Path("artifacts")
    agent_dir = work_dir / "agent"
    runs_dir = agent_dir / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    compare_summary = json.loads(compare_summary_path.read_text(encoding="utf-8"))
    exclusions = json.loads(
        (compare_summary_path.parent / "exclusions.json").read_text(encoding="utf-8"))

    hermes_home = Path(os.environ.get("HERMES_HOME", "data/hermes")).resolve()
    plugin_dir = ensure_hermes_profile(hermes_home)

    doctor = {"ran": False, "ok": None, "detail": ""}
    try:
        proc = subprocess.run(
            ["hermes", "plugins", "doctor", str(plugin_dir), "--ci"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HERMES_HOME": str(hermes_home)},
        )
        doctor = {"ran": True, "ok": proc.returncode == 0,
                  "detail": (proc.stdout + proc.stderr)[-1000:]}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        doctor = {"ran": True, "ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    # Default query set: grounded comparison, coverage accounting, missing-evidence probe.
    compared_ids = [c["entry_id"] for c in json.loads(
        (compare_summary_path.parent / "comparisons.json").read_text(encoding="utf-8"))]
    sample_entry = compared_ids[0] if compared_ids else ""
    excluded_entry = next((e for e in exclusions if e["reason"] == "unmatched"), None)

    queries = [
        {
            "query": (
                f"Compare the Britannica entry {sample_entry} with its matched Wikipedia article "
                "using the challenge tools. Summarize the top vocabulary differences and cite "
                "the Britannica source pages and Wikipedia page_id/revision_id."
            ),
            "expects_tools": True,
            "expects_missing_evidence": False,
        },
        {
            "query": (
                "How many of the extracted Britannica entries could not be compared, and for "
                "what reasons? Use the coverage tool and report the recorded numbers."
            ),
            "expects_tools": True,
            "expects_missing_evidence": False,
        },
        {
            "query": (
                f"Compare the Britannica entry {excluded_entry['entry_id']} "
                f"(\"{excluded_entry['britannica_title']}\") with Wikipedia." if excluded_entry else
                "Compare the Britannica entry for 'phlogiston engines' with Wikipedia."
            ),
            "expects_tools": True,
            "expects_missing_evidence": True,
        },
    ]
    queries_file = os.environ.get("AGENT_QUERIES_FILE", "")
    if queries_file:
        queries = json.loads(Path(queries_file).read_text(encoding="utf-8"))

    manifest = load_manifest()
    store = LanceArtifactStore(settings.db_path)
    expected_model = settings.super_model or "Nemotron-3.5-Super-VL"

    records = []
    for index, spec in enumerate(queries):
        record = run_agent_query(spec["query"], settings, hermes_home, artifacts_dir)
        raw_stdout = record.pop("_raw_stdout", "")
        verification = verify_run(
            record, expected_model,
            expects_tools=spec.get("expects_tools", True),
            expects_missing_evidence=spec.get("expects_missing_evidence", False),
        )
        record["verification"] = verification

        slug = slugify(spec["query"])
        run_path = runs_dir / f"{index:02d}-{slug}.json"
        record["raw_stdout_path"] = str(runs_dir / f"{index:02d}-{slug}.jsonl")
        run_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        Path(record["raw_stdout_path"]).write_text(raw_stdout, encoding="utf-8")

        record_agent_provenance(store, record, verification, run_path, manifest, index)
        records.append({"run": run_path.name, "status": verification["status"],
                        "tool_calls": [t["name"] for t in record["tool_uses"]]})

    (agent_dir / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    successes = sum(1 for r in records if r["status"] == "success")
    return {
        "stage": "agent",
        "status": "completed",
        "hermes_home": str(hermes_home),
        "plugin_doctor": doctor,
        "runs_total": len(records),
        "successes": successes,
        "failures": len(records) - successes,
        "model_verified": any(
            "nemotron-3.5-super-vl" in str(r.get("model", "")).lower() for r in
            [json.loads((runs_dir / r["run"]).read_text()) for r in records]),
        "tool_calls_total": sum(len(r["tool_calls"]) for r in records),
        "runs": records,
        "artifacts_dir": str(agent_dir),
        "database_path": str(settings.db_path),
    }


def site(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: build your LaTeX documents and static website."""
    _unfinished("site")


def evaluate(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """TODO: review your results and document successes and failures."""
    _unfinished("evaluate")
