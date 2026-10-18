"""Matching historical Britannica entries to canonical Wikipedia articles."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field

from .clients import ChatClient, RetrievalClient, ServiceError, WikiClient
from .config import Settings
from .contracts import ArtifactRecord, SourceReference, WikiArticle
from .storage import LanceArtifactStore


class MatchCandidate(BaseModel):
    page_id: str
    revision_id: str
    title: str
    url: str
    bm25_score: float
    excerpt: str
    stage1_score: float | None = None
    multimodal_score: float | None = None
    is_disambiguation: bool = False
    source_query: str = ""


class MatchResult(BaseModel):
    entry_id: str
    britannica_title: str
    source_pages: list[str]
    matched: bool
    status: str  # "accepted", "rejected_threshold", "rejected_disambiguation", "no_candidates", "retrieval_unavailable"
    selected_candidate: MatchCandidate | None = None
    all_candidates: list[MatchCandidate] = Field(default_factory=list)
    article_text_sha256: str | None = None
    decision_rationale: str = ""


def is_disambiguation_title(title: str) -> bool:
    """Detect if a Wikipedia title indicates a disambiguation page."""
    lower = title.lower().strip()
    return (
        "(disambiguation)" in lower
        or lower.endswith(" disambiguation")
        or lower.startswith("list of ")
        or lower.startswith("index of ")
    )


def extract_fallback_queries(title: str, text: str) -> list[str]:
    """Generate deterministic search terms from entry title and opening text."""
    clean_title = re.sub(r"[^\w\s-]", "", title).strip()
    clean_title = re.sub(r"^[0-9\s]+", "", clean_title).strip()
    clean_title = re.sub(r"[0-9]+$", "", clean_title).strip()
    queries = []
    if clean_title:
        queries.append(clean_title)

    # Visual plate keyword extraction
    subj_match = re.search(r"Related Scientific Subjects:\s*([^\n]+)", text)
    if subj_match:
        for term in subj_match.group(1).split(","):
            cleaned = term.strip()
            if cleaned and cleaned not in queries:
                queries.append(cleaned)

    # First sentence / phrase
    sentences = re.split(r"[.!?\n]", text)
    if sentences:
        first_sentence = sentences[0].strip()
        words = [w for w in re.findall(r"[A-Za-z0-9-]+", first_sentence) if len(w) > 3]
        if len(words) >= 2:
            snippet = " ".join(words[:4])
            if snippet.lower() != clean_title.lower() and snippet not in queries:
                queries.append(snippet)

    return queries[:4] if queries else ["Britannica"]


QUERY_PROMPT_VERSION = "query-v2-corrected-ocr"


def _query_fingerprint(title: str, text: str, model_id: str) -> str:
    payload = json.dumps({
        "title": title, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "model_id": model_id, "prompt_version": QUERY_PROMPT_VERSION,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def generate_search_queries(
    entry_id: str,
    title: str,
    text: str,
    client: ChatClient | None,
    cache_dir: Path,
) -> list[str]:
    """Generate 2-3 focused Wikipedia search terms using Super 3.5 VL or cached results."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{entry_id}.json"
    model_id = client.model if client is not None else "deterministic-fallback"
    fingerprint = _query_fingerprint(title, text, model_id)
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            queries = cached.get("queries", []) if isinstance(cached, dict) else []
            if cached.get("fingerprint") == fingerprint and queries and all(isinstance(q, str) for q in queries):
                return queries
        except (json.JSONDecodeError, OSError):
            pass

    fallback = extract_fallback_queries(title, text)
    if client is None:
        return fallback

    # Super 3.5 VL prompt to extract search terms
    text_snippet = text[:1500].strip()
    prompt = (
        f"You are an expert historical research assistant. Given this historical Encyclopaedia Britannica entry, "
        f"identify 2 or 3 modern canonical Wikipedia article titles or precise search phrases to find the Wikipedia article matching this subject.\n\n"
        f"Entry Title: {title}\n"
        f"Excerpt: {text_snippet}\n\n"
        f"Respond with ONLY a JSON array of 2 or 3 search query strings, e.g. [\"Subject\", \"Alternative Name\"]."
    )

    try:
        res = client.complete(
            [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
            max_tokens=256,
            extra_body={"temperature": 0},
        )
        content = res["choices"][0]["message"]["content"].strip()
        # Parse JSON list from response
        match = re.search(r"\[[\s\S]*?\]", content)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list) and parsed:
                queries = [str(q).strip() for q in parsed if str(q).strip()][:3]
                if queries:
                    cache_path.write_text(json.dumps({
                        "fingerprint": fingerprint, "prompt_version": QUERY_PROMPT_VERSION,
                        "model_id": model_id, "queries": queries,
                    }, indent=2), encoding="utf-8")
                    return queries
    except Exception:
        pass

    # Save fallback to cache
    try:
        cache_path.write_text(json.dumps({
            "fingerprint": fingerprint, "prompt_version": QUERY_PROMPT_VERSION,
            "model_id": model_id, "queries": fallback,
        }, indent=2), encoding="utf-8")
    except OSError:
        pass
    return fallback


def retrieve_candidates(
    queries: list[str],
    wiki_client: WikiClient,
    top_k_per_query: int = 8,
) -> list[MatchCandidate]:
    """Query Wikipedia BM25 API with deduplication across query results."""
    candidates_by_id: dict[str, MatchCandidate] = {}

    for query in queries:
        clean_q = query.strip()
        if not clean_q or len(clean_q) > 512:
            continue
        try:
            search_result = wiki_client.search(clean_q, top_k=top_k_per_query, excerpt_chars=1200)
            for hit in search_result.hits:
                if hit.page_id not in candidates_by_id:
                    candidates_by_id[hit.page_id] = MatchCandidate(
                        page_id=hit.page_id,
                        revision_id=hit.revision_id,
                        title=hit.title,
                        url=hit.url,
                        bm25_score=hit.bm25_score,
                        excerpt=hit.excerpt,
                        is_disambiguation=is_disambiguation_title(hit.title),
                        source_query=clean_q,
                    )
                else:
                    # Keep maximum BM25 score if seen across multiple queries
                    existing = candidates_by_id[hit.page_id]
                    if hit.bm25_score > existing.bm25_score:
                        existing.bm25_score = hit.bm25_score
        except Exception:
            continue

    # Return candidates sorted by BM25 score descending
    return sorted(candidates_by_id.values(), key=lambda c: c.bm25_score, reverse=True)


import time


def _rerank_with_retry(
    retrieval_client: RetrievalClient,
    query: str,
    documents: list[Any],
    max_retries: int = 4,
) -> list[dict[str, Any]]:
    for attempt in range(max_retries):
        try:
            return retrieval_client.rerank(query=query, documents=documents)
        except ServiceError as exc:
            if exc.status_code == 429 and attempt < max_retries - 1:
                wait_sec = 1.0
                if exc.retry_after and exc.retry_after.strip().isdigit():
                    wait_sec = float(exc.retry_after.strip())
                time.sleep(wait_sec)
                continue
            raise


def rerank_candidates_text(
    entry_title: str,
    entry_text: str,
    candidates: list[MatchCandidate],
    retrieval_client: RetrievalClient,
) -> list[MatchCandidate]:
    """Stage 1: Text-only reranking between Britannica entry and Wikipedia candidate excerpts."""
    if not candidates:
        return []

    # Use title and opening text as query (capped at 2000 chars for reranker limit)
    query_text = f"Subject: {entry_title}\n\n{entry_text[:1800]}".strip()
    # Documents: candidate title and excerpt
    documents = [f"{c.title}\n{c.excerpt}".strip() for c in candidates[:32]]

    try:
        rerank_results = _rerank_with_retry(retrieval_client, query=query_text, documents=documents)
        for item in rerank_results:
            idx = item["index"]
            score = item["relevance_score"]
            if idx < len(candidates):
                candidates[idx].stage1_score = score
        # Sort by stage1_score descending, putting None at the end
        return sorted(candidates, key=lambda c: c.stage1_score if c.stage1_score is not None else -999.0, reverse=True)
    except Exception:
        # Fall back to BM25 ranking if retrieval service is unreachable
        return candidates


def rerank_candidates_multimodal(
    candidates: list[MatchCandidate],
    entry_text: str,
    scan_paths: list[Path],
    retrieval_client: RetrievalClient,
) -> list[MatchCandidate]:
    """Stage 2: Multimodal reranking for top candidates using scan image + entry text."""
    if not candidates or not scan_paths:
        return candidates

    scan_image_url = None
    for sp in scan_paths:
        if sp.is_file():
            try:
                b64 = base64.b64encode(sp.read_bytes()).decode("ascii")
                scan_image_url = f"data:image/jpeg;base64,{b64}"
                break
            except OSError:
                pass

    if not scan_image_url:
        return candidates

    # Rerank top 3 candidates:
    # Query is candidate title + excerpt
    # Document is Britannica entry text + scan image
    top_candidates = candidates[:3]
    for candidate in top_candidates:
        query_text = f"{candidate.title}: {candidate.excerpt[:1500]}".strip()
        doc_entry = {"text": entry_text[:30000].strip(), "image": scan_image_url}
        try:
            res = _rerank_with_retry(retrieval_client, query=query_text, documents=[doc_entry])
            if res and isinstance(res, list):
                candidate.multimodal_score = res[0].get("relevance_score")
        except Exception:
            candidate.multimodal_score = candidate.stage1_score

    # Re-sort top candidates by multimodal score
    top_sorted = sorted(top_candidates, key=lambda c: c.multimodal_score if c.multimodal_score is not None else -999.0, reverse=True)
    return top_sorted + candidates[3:]



def fetch_full_article_verified(
    page_id: str,
    wiki_client: WikiClient,
    cache_dir: Path,
) -> WikiArticle:
    """Fetch complete paginated Wikipedia article and verify text_sha256."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{page_id}.json"
    if cache_path.is_file():
        try:
            return WikiArticle.model_validate_json(cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    offset = 0
    text_chunks: list[str] = []
    first_page: WikiArticle | None = None
    last_page: WikiArticle | None = None

    while True:
        part = wiki_client.article(page_id, offset=offset, max_chars=10000)
        if first_page is None:
            first_page = part
        last_page = part
        text_chunks.append(part.text)
        if part.next_offset is None:
            break
        offset = part.next_offset

    full_text = "".join(text_chunks)
    computed_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
    if computed_hash != first_page.provenance.text_sha256:
        raise ValueError(
            f"Wikipedia article {page_id} sha256 mismatch: got {computed_hash}, expected {first_page.provenance.text_sha256}"
        )

    # Construct complete verified article record
    complete_article = WikiArticle(
        page_id=first_page.page_id,
        revision_id=first_page.revision_id,
        title=first_page.title,
        url=first_page.url,
        provenance=first_page.provenance,
        license=first_page.license,
        text=full_text,
        offset=0,
        returned_chars=len(full_text),
        total_chars=len(full_text),
        next_offset=None,
    )

    cache_path.write_text(complete_article.model_dump_json(indent=2), encoding="utf-8")
    return complete_article


def evaluate_match_decision(
    candidates: list[MatchCandidate],
    threshold: float | None = None,
) -> tuple[bool, MatchCandidate | None, str, str]:
    """Evaluate whether top non-disambiguation candidate is an accepted match or rejected.

    Returns: (matched, candidate, status, rationale)
    """
    if not candidates:
        return False, None, "no_candidates", "No candidate Wikipedia articles retrieved."

    if threshold is None:
        threshold = float(os.environ.get("MATCH_THRESHOLD", "-5.5"))

    # Skip disambiguation and list pages to find valid encyclopedic article candidates
    valid_candidates = [c for c in candidates if not c.is_disambiguation]
    if not valid_candidates:
        return (
            False,
            candidates[0],
            "rejected_disambiguation",
            f"All {len(candidates)} candidate articles are disambiguation or index pages.",
        )

    top = valid_candidates[0]
    score = top.multimodal_score if top.multimodal_score is not None else top.stage1_score
    if score is None:
        # No reranker scores available (e.g. retrieval service offline); accept top-1 with BM25
        return (
            True,
            top,
            "accepted_bm25_only",
            f"Accepted candidate '{top.title}' using BM25 score {top.bm25_score:.2f} (retrieval scores not computed).",
        )

    if score >= threshold:
        return (
            True,
            top,
            "accepted",
            f"Accepted candidate '{top.title}' with relevance score {score:.4f} >= threshold {threshold}.",
        )

    return (
        False,
        top,
        "rejected_threshold",
        f"Rejected candidate '{top.title}'; relevance score {score:.4f} < threshold {threshold}.",
    )


def record_match_provenance(
    store: LanceArtifactStore,
    result: MatchResult,
    manifest: dict[str, Any],
    pages_by_id: dict[str, dict[str, Any]],
    work_dir: Path,
) -> None:
    """Persist dual-source ArtifactRecord linking Britannica scan and Wikipedia article."""
    dataset = manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated")
    revision = manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443")
    source_url = manifest.get("source_url", "")
    license_spdx = manifest.get("license", {}).get("spdx", "CC0-1.0")

    sources: list[SourceReference] = []
    # 1. Britannica scan sources
    for pid in result.source_pages:
        pmeta = pages_by_id.get(pid, {})
        sources.append(
            SourceReference(
                dataset=dataset,
                dataset_revision=revision,
                source_id=pid,
                source_url=source_url,
                content_sha256=pmeta.get("image_sha256", "0" * 64),
                license=license_spdx,
            )
        )

    # 2. Wikipedia article source (if matched)
    if result.matched and result.selected_candidate:
        cand = result.selected_candidate
        sources.append(
            SourceReference(
                dataset="wikimedia/structured-wikipedia",
                dataset_revision="417c267bb457fa645c22eb3b5c77764963194c70",
                source_id=cand.page_id,
                source_url=cand.url,
                content_sha256=result.article_text_sha256 or ("0" * 64),
                license="CC-BY-SA-4.0",
            )
        )

    record_path = work_dir / "match" / f"{result.entry_id}.json"
    artifact_record = ArtifactRecord(
        record_id=f"match:{result.entry_id}",
        stage="match",
        sources=sources,
        artifact_path=str(record_path),
        metadata={
            "britannica_title": result.britannica_title,
            "matched": result.matched,
            "status": result.status,
            "rationale": result.decision_rationale,
            "selected_page_id": result.selected_candidate.page_id if result.selected_candidate else None,
            "selected_title": result.selected_candidate.title if result.selected_candidate else None,
            "relevance_score": (
                result.selected_candidate.multimodal_score
                if result.selected_candidate and result.selected_candidate.multimodal_score is not None
                else (result.selected_candidate.stage1_score if result.selected_candidate else None)
            ),
        },
    )
    store.put(artifact_record)
