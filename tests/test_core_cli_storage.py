"""Offline setup and storage contracts do not implement challenge stages."""
from dataclasses import replace
import json
from pathlib import Path
import subprocess

import httpx
import pytest

from nemotron_challenge.cli import doctor, main
from nemotron_challenge.config import ConfigurationError, Settings
from nemotron_challenge.contracts import ArtifactRecord, SourceReference
from nemotron_challenge.storage import LanceArtifactStore


def test_offline_doctor_needs_no_secrets_or_network(monkeypatch, capsys):
    monkeypatch.setattr(httpx.Client, "send", lambda *args, **kwargs: pytest.fail("offline doctor started a request"))
    for key in ("SUPER_API_KEY", "RETRIEVAL_BASE_URL", "PARSE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert main(["doctor", "--offline"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["inference"] == "not tested"
    assert set(data["challenge_stages"]) == {"extract", "match", "compare", "agent", "site", "evaluate"}
    assert all(s in {"todo", "implemented", "completed"} for s in data["challenge_stages"].values())
    assert all(row["status"] == "not_tested" for row in data["checks"] if "configured" in row)


def test_live_doctor_reports_missing_resources(monkeypatch):
    settings = Settings(wikipedia_api_url="", parse_base_url="", retrieval_base_url="", super_api_key="")
    monkeypatch.setattr(httpx.Client, "send", lambda *args, **kwargs: pytest.fail("missing config started a request"))
    report, code = doctor(settings, live=True)
    assert code == 1
    assert {check["name"] for check in report["checks"] if check["status"] == "missing"} == {"wikipedia", "parse", "retrieval", "super"}
    assert report["inference"] == "not tested"


def test_site_stage_execution(tmp_path, monkeypatch):
    artifacts_path = tmp_path / "artifacts"
    extract_dir = artifacts_path / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    sample_entries = [
        {
            "entry_id": "test-entry-site",
            "title": "ABYSSINIA",
            "text": "Historical text on Abyssinia.",
            "source_pages": ["britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:13"],
            "source_row_indices": [13],
            "volume_id": "193913444",
            "is_continuation": False,
            "block_count": 1,
            "character_count": 28,
        }
    ]
    (extract_dir / "entries.json").write_text(json.dumps(sample_entries), encoding="utf-8")
    db_path = tmp_path / "test.lancedb"
    monkeypatch.setenv("CHALLENGE_DB_PATH", str(db_path))

    assert main(["run", "site", "--work-dir", str(artifacts_path)]) == 0
    assert (artifacts_path / "site" / "index.html").is_file()
    assert (artifacts_path / "site" / "latex" / "test-entry-site.tex").is_file()
    assert "ABYSSINIA" in (artifacts_path / "site" / "latex" / "test-entry-site.tex").read_text()


def test_evaluate_stage_execution(tmp_path, monkeypatch):
    artifacts_path = tmp_path / "artifacts"
    eval_dir = artifacts_path / "evaluate"
    db_path = tmp_path / "test.lancedb"
    monkeypatch.setenv("CHALLENGE_DB_PATH", str(db_path))

    assert main(["run", "evaluate", "--work-dir", str(artifacts_path)]) == 0
    assert (eval_dir / "submission.md").is_file()
    assert (eval_dir / "case-study-cs-success-01.md").is_file()
    assert (eval_dir / "case-study-cs-failure-01.md").is_file()



def test_extract_stage_with_mocked_parse(monkeypatch, tmp_path):
    from nemotron_challenge.clients import ParseClient

    sample_output = {
        "choices": [
            {
                "message": {
                    "content": "<x_0.05><y_0.02>100<x_0.10><y_0.04><class_Page-header>\n<x_0.20><y_0.02>**TOPIC**<x_0.50><y_0.04><class_Page-header>\n<x_0.05><y_0.05>Sample entry text.<x_0.80><y_0.80><class_Text>"
                }
            }
        ]
    }
    monkeypatch.setattr(ParseClient, "parse", lambda self, image_data_url: sample_output)
    artifacts_path = tmp_path / "artifacts"
    db_path = tmp_path / "test.lancedb"
    test_cache = tmp_path / "cache"
    monkeypatch.setenv("CHALLENGE_DB_PATH", str(db_path))
    monkeypatch.setenv("PARSE_CACHE_DIR", str(test_cache))

    # Mock load_manifest with 2 pages to keep unit test isolated and fast
    import nemotron_challenge.data as d
    real_manifest = d.load_manifest()
    sub_manifest = dict(real_manifest, pages=real_manifest["pages"][:2])
    monkeypatch.setattr(d, "load_manifest", lambda: sub_manifest)
    import nemotron_challenge.tasks as t
    monkeypatch.setattr(t, "load_manifest", lambda: sub_manifest)

    assert main(["run", "extract", "--work-dir", str(artifacts_path)]) == 0
    assert (artifacts_path / "extract" / "entries.json").is_file()


def test_match_stage_execution(monkeypatch, tmp_path):
    artifacts_path = tmp_path / "artifacts"
    extract_dir = artifacts_path / "extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    sample_entries = [
        {
            "entry_id": "test-entry-1",
            "title": "ABYSSINIA",
            "text": "Abyssinia is an ancient country in eastern Africa.",
            "source_pages": ["britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:13"],
            "source_row_indices": [13],
            "volume_id": "193913444",
            "is_continuation": False,
            "block_count": 1,
            "character_count": 50,
        }
    ]
    (extract_dir / "entries.json").write_text(json.dumps(sample_entries), encoding="utf-8")

    db_path = tmp_path / "test.lancedb"
    monkeypatch.setenv("CHALLENGE_DB_PATH", str(db_path))
    monkeypatch.setenv("QUERY_CACHE_DIR", str(tmp_path / "queries"))
    monkeypatch.setenv("WIKI_CACHE_DIR", str(tmp_path / "wiki"))

    # Mock matching functions to avoid live network in unit test
    import nemotron_challenge.tasks as t
    from nemotron_challenge.matching import MatchCandidate
    mock_cand = MatchCandidate(
        page_id="100", revision_id="1", title="Ethiopia", url="https://en.wikipedia.org/wiki/Ethiopia",
        bm25_score=15.0, excerpt="Ethiopia is a country in the Horn of Africa.",
        stage1_score=2.0, multimodal_score=2.5,
    )
    monkeypatch.setattr(t, "generate_search_queries", lambda *args, **kwargs: ["Ethiopia"])
    monkeypatch.setattr(t, "retrieve_candidates", lambda *args, **kwargs: [mock_cand])

    class MockArticle:
        class Provenance:
            text_sha256 = "d" * 64
        provenance = Provenance()

    monkeypatch.setattr(t, "fetch_full_article_verified", lambda *args, **kwargs: MockArticle())

    assert main(["run", "match", "--work-dir", str(artifacts_path)]) == 0
    assert (artifacts_path / "match" / "matches.json").is_file()
    assert (artifacts_path / "match" / "unmatched.json").is_file()


def test_compare_stage_execution(monkeypatch, tmp_path):
    artifacts_path = tmp_path / "artifacts"
    extract_dir = artifacts_path / "extract"
    match_dir = artifacts_path / "match"
    extract_dir.mkdir(parents=True, exist_ok=True)
    match_dir.mkdir(parents=True, exist_ok=True)

    sample_entries = [
        {
            "entry_id": "test-entry-1",
            "title": "ABYSSINIA",
            "text": "Abyssinia is an ancient country in eastern Africa. " * 10,
            "source_pages": ["britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:13"],
            "source_row_indices": [13],
            "volume_id": "193913444",
            "is_continuation": False,
            "block_count": 1,
            "character_count": 510,
        },
        {
            "entry_id": "test-entry-short",
            "title": "BLANK",
            "text": "",
            "source_pages": ["britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:14"],
            "source_row_indices": [14],
            "volume_id": "193913444",
            "is_continuation": False,
            "block_count": 0,
            "character_count": 0,
        },
    ]
    (extract_dir / "entries.json").write_text(json.dumps(sample_entries), encoding="utf-8")

    sample_matches = [
        {
            "entry_id": "test-entry-1",
            "britannica_title": "ABYSSINIA",
            "source_pages": ["britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:13"],
            "matched": True,
            "status": "accepted",
            "selected_candidate": {
                "page_id": "100", "revision_id": "1", "title": "Ethiopia",
                "url": "https://en.wikipedia.org/wiki/Ethiopia", "bm25_score": 15.0,
                "excerpt": "Ethiopia is a country in the Horn of Africa.",
                "stage1_score": 2.0, "multimodal_score": 2.5,
                "is_disambiguation": False, "source_query": "Ethiopia",
            },
            "all_candidates": [],
            "article_text_sha256": "d" * 64,
            "decision_rationale": "test",
        },
        {
            "entry_id": "test-entry-short",
            "britannica_title": "BLANK",
            "source_pages": ["britannica:309f765b1ecc83e0a7f7762e44b4a927a7555443:train:14"],
            "matched": True,
            "status": "accepted",
            "selected_candidate": {
                "page_id": "101", "revision_id": "1", "title": "Blank",
                "url": "https://en.wikipedia.org/wiki/Blank", "bm25_score": 5.0,
                "excerpt": "Blank.", "stage1_score": 1.0, "multimodal_score": 1.0,
                "is_disambiguation": False, "source_query": "Blank",
            },
            "all_candidates": [],
            "article_text_sha256": "e" * 64,
            "decision_rationale": "test",
        },
    ]
    (match_dir / "matches.json").write_text(json.dumps(sample_matches), encoding="utf-8")
    (match_dir / "unmatched.json").write_text("[]", encoding="utf-8")

    monkeypatch.setenv("CHALLENGE_DB_PATH", str(tmp_path / "test.lancedb"))
    monkeypatch.setenv("WIKI_CACHE_DIR", str(tmp_path / "wiki"))
    monkeypatch.setenv("COMPARE_CACHE_DIR", str(tmp_path / "comparisons"))
    monkeypatch.setenv("SUPER_API_KEY", "")
    monkeypatch.setenv("RETRIEVAL_BASE_URL", "")

    import nemotron_challenge.tasks as t

    class MockArticle:
        page_id = "100"
        revision_id = "1"
        title = "Ethiopia"
        url = "https://en.wikipedia.org/wiki/Ethiopia"
        text = "Ethiopia, officially the Federal Democratic Republic of Ethiopia, is a country in the Horn of Africa. " * 8

        class Provenance:
            text_sha256 = "d" * 64
        provenance = Provenance()

    monkeypatch.setattr(t, "fetch_full_article_verified", lambda *args, **kwargs: MockArticle())

    assert main(["run", "compare", "--work-dir", str(artifacts_path)]) == 0
    compare_dir = artifacts_path / "compare"
    assert (compare_dir / "summary.json").is_file()
    assert (compare_dir / "comparisons.json").is_file()
    assert (compare_dir / "exclusions.json").is_file()
    assert (compare_dir / "plots" / "document_accounting.svg").is_file()

    summary = json.loads((compare_dir / "summary.json").read_text(encoding="utf-8"))
    assert summary["compared_count"] == 1
    assert summary["excluded_count"] == 1
    assert summary["entries_total"] == 2
    assert summary["document_accounting_verified"] is True

    exclusions = json.loads((compare_dir / "exclusions.json").read_text(encoding="utf-8"))
    assert exclusions[0]["reason"] == "short_or_blank_text"



def test_agent_stage_execution(monkeypatch, tmp_path):
    artifacts_path = tmp_path / "artifacts"
    compare_dir = artifacts_path / "compare"
    compare_dir.mkdir(parents=True, exist_ok=True)

    (compare_dir / "summary.json").write_text(json.dumps({
        "entries_total": 2, "compared_count": 1, "excluded_count": 1,
        "exclusions_by_reason": {"unmatched": 1},
        "document_accounting_verified": True,
    }), encoding="utf-8")
    (compare_dir / "comparisons.json").write_text(json.dumps([
        {"entry_id": "entry-optics-1"},
    ]), encoding="utf-8")
    (compare_dir / "exclusions.json").write_text(json.dumps([
        {"entry_id": "entry-unmatched-2", "britannica_title": "NO MATCH",
         "source_pages": ["p2"], "reason": "unmatched", "match_status": "no_candidates"},
    ]), encoding="utf-8")

    monkeypatch.setenv("CHALLENGE_DB_PATH", str(tmp_path / "test.lancedb"))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    monkeypatch.setenv("SUPER_API_KEY", "test-key")

    def stream(query: str) -> str:
        events = [
            {"type": "system", "subtype": "init",
             "model": "nvidia/Nemotron-3.5-Super-VL", "session_id": "s1"},
            {"type": "tool_use", "name": "challenge_compare",
             "input": {"entry_id": "entry-optics-1"}, "tool_call_id": "t1"},
            {"type": "tool_result", "name": "challenge_compare",
             "output": '{"status": "ok"}', "duration_ms": 5, "is_error": False,
             "tool_call_id": "t1"},
        ]
        if "entry-unmatched-2" in query:
            events.append({"type": "result", "exit_code": 0,
                           "text": "No comparison evidence exists for this entry; it was excluded.",
                           "usage": {}})
        else:
            events.append({"type": "result", "exit_code": 0,
                           "text": "Compared with citations to page 42 revision 100.",
                           "usage": {"total": 10}})
        return "\n".join(json.dumps(e) for e in events)

    def fake_run(command, **kwargs):
        class Proc:
            pass
        proc = Proc()
        proc.stderr = ""
        if "chat" in command:
            query = command[command.index("-q") + 1]
            proc.stdout = stream(query)
            proc.returncode = 0
        else:  # plugins doctor
            proc.stdout = "ok"
            proc.returncode = 0
        return proc

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert main(["run", "agent", "--work-dir", str(artifacts_path)]) == 0
    agent_dir = artifacts_path / "agent"
    assert (agent_dir / "records.json").is_file()
    run_files = sorted((agent_dir / "runs").glob("*.json"))
    assert len(run_files) == 3

    records = json.loads((agent_dir / "records.json").read_text(encoding="utf-8"))
    assert all(r["status"] == "success" for r in records)

    probe = [f for f in run_files if f.name.startswith("02-")][0]
    detail = json.loads(probe.read_text(encoding="utf-8"))
    assert detail["verification"]["status"] == "success"
    assert detail["tool_uses"][0]["name"] == "challenge_compare"


def test_stages_report_implementation_and_run_status(capsys, tmp_path):
    assert main(["stages", "--work-dir", str(tmp_path)]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 6
    assert all(row["status"] == "implemented" for row in rows)
    assert all(row["guide"] == f"docs/milestones.md#{row['stage']}" for row in rows)

    sentinel = tmp_path / "extract" / "entries.json"
    sentinel.parent.mkdir(parents=True)
    sentinel.write_text("[]", encoding="utf-8")
    assert main(["stages", "--work-dir", str(tmp_path)]) == 0
    by_stage = {row["stage"]: row for row in json.loads(capsys.readouterr().out)}
    assert by_stage["extract"]["status"] == "completed"
    assert by_stage["match"]["status"] == "implemented"


def test_keys_are_not_exposed_by_settings_repr():
    settings = Settings(parse_api_key="parse-secret", retrieval_api_key="retrieval-secret", super_api_key="super-secret")
    assert "secret" not in repr(settings)


@pytest.mark.parametrize("name,value", [("PARSE_MODEL", "old-parse"), ("SUPER_MODEL", "other-model"), ("SUPER_BASE_URL", "https://user:key@example.com/v1")])
def test_wrong_models_or_url_credentials_are_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError):
        Settings.from_env(None)


def test_provenance_store_persists_upserts_and_quotes_ids(tmp_path):
    source = SourceReference(dataset="synthetic-fixture", dataset_revision="v1", source_id="source-1",
                             source_url="https://example.com/fixture", content_sha256="a" * 64, license="CC0-1.0")
    record = ArtifactRecord(record_id="team's-record", stage="extract", sources=[source], artifact_path="artifacts/raw.json")
    store = LanceArtifactStore(tmp_path / "team.lancedb")
    store.put(record)
    assert store.get(record.record_id) == record
    changed = record.model_copy(update={"artifact_path": "artifacts/reviewed.json"})
    store.put(changed)
    reopened = LanceArtifactStore(tmp_path / "team.lancedb")
    assert reopened.get(record.record_id) == changed
    assert reopened.get("' OR 1=1 --") is None
    assert reopened.table.count_rows() == 1
