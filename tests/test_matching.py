"""Unit tests for the matching pipeline components."""
import hashlib
import json
from pathlib import Path
import pytest

from nemotron_challenge.contracts import ArtifactRecord
from nemotron_challenge.matching import (
    MatchCandidate,
    MatchResult,
    evaluate_match_decision,
    extract_fallback_queries,
    fetch_full_article_verified,
    generate_search_queries,
    is_disambiguation_title,
    record_match_provenance,
    rerank_candidates_multimodal,
    rerank_candidates_text,
    retrieve_candidates,
)
from nemotron_challenge.storage import LanceArtifactStore


def test_is_disambiguation_title():
    assert is_disambiguation_title("Hindustan (disambiguation)") is True
    assert is_disambiguation_title("Paris (disambiguation)") is True
    assert is_disambiguation_title("List of African countries") is True
    assert is_disambiguation_title("Index of articles") is True
    assert is_disambiguation_title("Hindustan") is False
    assert is_disambiguation_title("Ethiopia") is False


def test_extract_fallback_queries():
    queries = extract_fallback_queries("ABY S SINIA 57", "Abyssinia her affairs entirely to Frumentius.")
    assert len(queries) >= 1
    assert "ABY S SINIA" in queries[0]


def test_generate_search_queries_with_cache(tmp_path):
    cache_dir = tmp_path / "queries"
    entry_id = "test-entry-1"

    # Pre-write cache
    cached_queries = ["History of Ethiopia", "Kingdom of Aksum"]
    cache_path = cache_dir / f"{entry_id}.json"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cached_queries), encoding="utf-8")

    result = generate_search_queries(entry_id, "Abyssinia", "Some text", client=None, cache_dir=cache_dir)
    assert result == cached_queries


def test_retrieve_candidates_deduplication():
    class MockHit:
        def __init__(self, page_id, title, bm25_score):
            self.page_id = page_id
            self.revision_id = "12345"
            self.title = title
            self.url = f"https://en.wikipedia.org/wiki/{title}"
            self.bm25_score = bm25_score
            self.excerpt = f"Excerpt for {title}"

    class MockSearch:
        def __init__(self, hits):
            self.hits = hits

    class MockWikiClient:
        def search(self, query, top_k, excerpt_chars):
            if query == "query1":
                return MockSearch([
                    MockHit("101", "Article One", 15.0),
                    MockHit("102", "Article Two", 12.0),
                ])
            else:
                return MockSearch([
                    MockHit("101", "Article One", 18.0),  # Duplicate with higher score
                    MockHit("103", "Article Three", 10.0),
                ])

    candidates = retrieve_candidates(["query1", "query2"], MockWikiClient())
    assert len(candidates) == 3
    cand_101 = next(c for c in candidates if c.page_id == "101")
    assert cand_101.bm25_score == 18.0


def test_evaluate_match_decision_threshold():
    # Candidate below threshold
    cand_low = MatchCandidate(
        page_id="1", revision_id="1", title="Low Match", url="https://example.com/1",
        bm25_score=10.0, excerpt="Low", stage1_score=-1.5, multimodal_score=-1.2
    )
    matched, cand, status, rationale = evaluate_match_decision([cand_low], threshold=0.0)
    assert matched is False
    assert status == "rejected_threshold"

    # Candidate above threshold
    cand_high = MatchCandidate(
        page_id="2", revision_id="1", title="High Match", url="https://example.com/2",
        bm25_score=15.0, excerpt="High", stage1_score=2.5, multimodal_score=3.1
    )
    matched, cand, status, rationale = evaluate_match_decision([cand_high], threshold=0.0)
    assert matched is True
    assert status == "accepted"

    # Disambiguation candidate alone
    cand_disam = MatchCandidate(
        page_id="3", revision_id="1", title="High (disambiguation)", url="https://example.com/3",
        bm25_score=20.0, excerpt="Disam", stage1_score=5.0, multimodal_score=5.0, is_disambiguation=True
    )
    matched, cand, status, rationale = evaluate_match_decision([cand_disam], threshold=0.0)
    assert matched is False
    assert status == "rejected_disambiguation"

    # Disambiguation first followed by valid candidate
    matched, cand, status, rationale = evaluate_match_decision([cand_disam, cand_high], threshold=0.0)
    assert matched is True
    assert cand.page_id == "2"
    assert status == "accepted"


def test_fetch_full_article_verified(tmp_path):
    text_p1 = "First part of the article text. "
    text_p2 = "Second part of the article text."
    full_text = text_p1 + text_p2
    expected_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()

    from nemotron_challenge.contracts import WikiArticle, WikiProvenance

    prov = WikiProvenance(
        dataset="wikimedia/structured-wikipedia",
        dataset_revision="417c267bb457fa645c22eb3b5c77764963194c70",
        dataset_url="https://example.com",
        source_key="key",
        source_row_idx=0,
        source_shard=None,
        text_sha256=expected_hash,
        extraction="text",
        revision_url="https://example.com/rev",
    )

    p1 = WikiArticle(
        page_id="999", revision_id="1", title="Test Article", url="https://example.com",
        provenance=prov, license={"spdx": "CC-BY-SA-4.0"},
        text=text_p1, offset=0, returned_chars=len(text_p1), total_chars=len(full_text),
        next_offset=len(text_p1),
    )
    p2 = WikiArticle(
        page_id="999", revision_id="1", title="Test Article", url="https://example.com",
        provenance=prov, license={"spdx": "CC-BY-SA-4.0"},
        text=text_p2, offset=len(text_p1), returned_chars=len(text_p2), total_chars=len(full_text),
        next_offset=None,
    )

    class MockWiki:
        def article(self, page_id, offset, max_chars):
            return p1 if offset == 0 else p2

    cache_dir = tmp_path / "wiki_cache"
    complete = fetch_full_article_verified("999", MockWiki(), cache_dir)
    assert complete.text == full_text
    assert complete.returned_chars == len(full_text)
    assert complete.next_offset is None
    assert (cache_dir / "999.json").is_file()


def test_record_match_provenance_store(tmp_path):
    cand = MatchCandidate(
        page_id="42", revision_id="100", title="Test Match", url="https://en.wikipedia.org/wiki/Test",
        bm25_score=15.0, excerpt="Excerpt", stage1_score=2.0, multimodal_score=2.5
    )
    result = MatchResult(
        entry_id="test-entry-1",
        britannica_title="Test Topic",
        source_pages=["britannica:rev:train:1"],
        matched=True,
        status="accepted",
        selected_candidate=cand,
        all_candidates=[cand],
        article_text_sha256="c" * 64,
        decision_rationale="High score",
    )
    manifest = {
        "dataset": "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated",
        "revision": "309f765b1ecc83e0a7f7762e44b4a927a7555443",
        "source_url": "https://example.com",
        "license": {"spdx": "CC0-1.0"},
    }
    pages_by_id = {
        "britannica:rev:train:1": {"image_sha256": "b" * 64, "row_index": 1}
    }

    db_path = tmp_path / "test.lancedb"
    store = LanceArtifactStore(db_path)
    record_match_provenance(store, result, manifest, pages_by_id, tmp_path)

    rec = store.get("match:test-entry-1")
    assert rec is not None
    assert rec.stage == "match"
    # Should contain 2 sources: Britannica scan + Wikipedia article
    assert len(rec.sources) == 2
    brit_src = rec.sources[0]
    wiki_src = rec.sources[1]
    assert brit_src.source_id == "britannica:rev:train:1"
    assert brit_src.content_sha256 == "b" * 64
    assert wiki_src.source_id == "42"
    assert wiki_src.content_sha256 == "c" * 64
    assert wiki_src.dataset == "wikimedia/structured-wikipedia"
