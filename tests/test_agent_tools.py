"""Unit tests for the Hermes plugin evidence tool handlers."""
import importlib.util
import json
from pathlib import Path

import pytest

PLUGIN_PATH = (
    Path(__file__).resolve().parents[1]
    / "integrations" / "hermes" / "nemotron-challenge" / "__init__.py"
)


@pytest.fixture()
def plugin(monkeypatch, tmp_path):
    """Load the plugin module with a fixture artifacts directory."""
    artifacts = tmp_path / "artifacts"
    (artifacts / "extract").mkdir(parents=True)
    (artifacts / "match").mkdir(parents=True)
    (artifacts / "compare").mkdir(parents=True)

    (artifacts / "extract" / "entries.json").write_text(json.dumps([
        {"entry_id": "entry-optics-1", "title": "OPTICS", "text": "Optics treats of light.",
         "source_pages": ["p1"], "character_count": 500},
        {"entry_id": "entry-blank-2", "title": "BLANK PAGE", "text": "",
         "source_pages": ["p2"], "character_count": 0},
    ]), encoding="utf-8")
    (artifacts / "extract" / "entry-optics-1.json").write_text(json.dumps(
        {"entry_id": "entry-optics-1", "title": "OPTICS",
         "text": "Optics treats of light, vision, and refraction."},
    ), encoding="utf-8")
    (artifacts / "match" / "matches.json").write_text(json.dumps([
        {"entry_id": "entry-optics-1", "matched": True, "status": "accepted",
         "selected_candidate": {"page_id": "42", "title": "Optics",
                                "url": "https://en.wikipedia.org/wiki/Optics"}},
    ]), encoding="utf-8")
    (artifacts / "match" / "unmatched.json").write_text(json.dumps([
        {"entry_id": "entry-blank-2", "matched": False, "status": "no_candidates"},
    ]), encoding="utf-8")
    (artifacts / "compare" / "entry-optics-1.json").write_text(json.dumps({
        "entry_id": "entry-optics-1", "britannica_title": "OPTICS",
        "source_pages": ["p1"], "britannica_sha256": "a" * 64,
        "wikipedia_page_id": "42", "wikipedia_revision_id": "100",
        "wikipedia_title": "Optics", "wikipedia_url": "https://en.wikipedia.org/wiki/Optics",
        "wikipedia_text_sha256": "d" * 64, "length_ratio": 4.0,
        "metrics": {"jaccard_raw": 0.1, "jaccard_normalized": 0.25, "cosine_tfidf": 0.4,
                    "cosine_embedding": 0.5, "distinctive_britannica": ["optic"],
                    "distinctive_wikipedia": ["photon"], "shared_terms": ["light"]},
        "claims": [{"claim_text": "Both discuss light.", "claim_type": "factual",
                    "label": "[factual]", "britannica_pages": ["p1"],
                    "britannica_quote": "Optics treats of light",
                    "wikipedia_page_id": "42", "wikipedia_revision_id": "100",
                    "wikipedia_quote": "Optics is the branch of physics"}],
        "topic_terms": ["optic", "light"],
    }), encoding="utf-8")
    (artifacts / "compare" / "exclusions.json").write_text(json.dumps([
        {"entry_id": "entry-blank-2", "britannica_title": "BLANK PAGE",
         "source_pages": ["p2"], "reason": "short_or_blank_text",
         "match_status": "no_candidates", "character_count": 0},
    ]), encoding="utf-8")
    (artifacts / "compare" / "summary.json").write_text(json.dumps({
        "entries_total": 2, "compared_count": 1, "excluded_count": 1,
        "exclusions_by_reason": {"short_or_blank_text": 1},
        "document_accounting_verified": True,
    }), encoding="utf-8")

    monkeypatch.setenv("CHALLENGE_ARTIFACTS_DIR", str(artifacts))
    spec = importlib.util.spec_from_file_location("nemotron_challenge_plugin", PLUGIN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_find_entry_hit(plugin):
    result = json.loads(plugin.handle_find_entry({"query": "optics"}))
    assert result["status"] == "ok"
    assert result["results"][0]["entry_id"] == "entry-optics-1"
    assert result["results"][0]["wikipedia_page_id"] == "42"
    assert result["policy"]


def test_find_entry_miss_returns_no_evidence(plugin):
    result = json.loads(plugin.handle_find_entry({"query": "xyzzy"}))
    assert result["status"] == "no_evidence"
    assert result["results"] == []
    assert "xyzzy" in result["missing"][0]


def test_find_entry_requires_query(plugin):
    result = json.loads(plugin.handle_find_entry({"query": ""}))
    assert result["status"] == "error"


def test_compare_returns_evidence_bundle(plugin):
    result = json.loads(plugin.handle_compare({"entry_id": "entry-optics-1"}))
    assert result["status"] == "ok"
    assert result["wikipedia"]["page_id"] == "42"
    assert result["wikipedia"]["revision_id"] == "100"
    assert result["metrics"]["cosine_tfidf"] == 0.4
    assert result["claims"][0]["label"] == "[factual]"
    assert result["claims"][0]["britannica_quote"] in result["britannica"]["excerpt"]


def test_compare_excluded_entry_reports_reason(plugin):
    result = json.loads(plugin.handle_compare({"entry_id": "entry-blank-2"}))
    assert result["status"] == "no_evidence"
    assert result["exclusion"]["reason"] == "short_or_blank_text"


def test_compare_unknown_entry(plugin):
    result = json.loads(plugin.handle_compare({"entry_id": "entry-nope-9"}))
    assert result["status"] == "no_evidence"
    assert result["exclusion"] is None


def test_check_coverage_reports_accounting(plugin):
    result = json.loads(plugin.handle_check_coverage({}))
    assert result["status"] == "ok"
    assert result["entries_total"] == 2
    assert result["compared_count"] == 1
    assert result["exclusions_by_reason"] == {"short_or_blank_text": 1}
    assert result["sample_excluded"][0]["entry_id"] == "entry-blank-2"


def test_check_coverage_without_summary(plugin, monkeypatch, tmp_path):
    monkeypatch.setenv("CHALLENGE_ARTIFACTS_DIR", str(tmp_path / "empty"))
    result = json.loads(plugin.handle_check_coverage({}))
    assert result["status"] == "no_evidence"


def test_handlers_never_raise(plugin, monkeypatch):
    monkeypatch.setenv("CHALLENGE_ARTIFACTS_DIR", "/nonexistent/path")
    for handler, params in (
        (plugin.handle_find_entry, {"query": "x"}),
        (plugin.handle_compare, {"entry_id": "x"}),
        (plugin.handle_check_coverage, {}),
    ):
        result = json.loads(handler(params))
        assert result["status"] in {"ok", "no_evidence", "error"}
