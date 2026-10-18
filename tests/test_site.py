"""Site stage: LaTeX generation, asset bundling, manifest, and link verification."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from nemotron_challenge.site import (
    _dedupe_entries,
    build_site_manifest,
    bundle_site_data,
    compile_latex_documents,
    copy_site_assets,
    escape_latex,
    generate_latex_document,
    verify_site_links,
    write_entry_details,
)


def _entry(**overrides):
    entry = {
        "entry_id": "entry-test-1",
        "title": "TEST & ENTRY_1",
        "text": "Historical text with % special $ chars #here.",
        "source_pages": ["britannica:rev:train:1"],
        "source_row_indices": [1],
        "volume_id": "v1",
        "is_continuation": False,
        "block_count": 1,
        "character_count": 45,
        "metadata": {},
    }
    entry.update(overrides)
    return entry


def _manifest():
    return {
        "dataset": "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated",
        "revision": "rev123",
        "license": {"spdx": "CC0-1.0"},
        "pages": [
            {
                "page_id": "britannica:rev:train:1",
                "row_index": 1,
                "volume_id": "v1",
                "filename": "page-0001-abc.jpg",
                "image_sha256": "a" * 64,
                "image_bytes": 10,
            }
        ],
    }


def _pages_by_id():
    return {p["page_id"]: p for p in _manifest()["pages"]}


def test_escape_latex_specials():
    out = escape_latex("a & b % c $ d # e _ f {g} ~ ^ \\")
    assert "&" not in out.replace("\\&", "")
    assert "\\%" in out and "\\$" in out and "\\#" in out and "\\_" in out
    assert "\\textbackslash{}" in out


def test_latex_document_sections_and_scan_figure():
    doc = generate_latex_document(_entry(), _manifest(), _pages_by_id())
    assert "\\usepackage{graphicx}" in doc
    assert "\\section*{Historical source}" in doc
    assert "\\section*{Source record}" in doc
    assert "\\includegraphics[width=0.85\\textwidth]{../scans/page-0001-abc.jpg}" in doc
    assert "TEST \\& ENTRY\\_1" in doc


def test_latex_document_without_known_page_has_no_figure():
    entry = _entry(source_pages=["missing-page"])
    doc = generate_latex_document(entry, _manifest(), _pages_by_id())
    assert "\\includegraphics" not in doc


def test_dedupe_entries_drops_repeated_ids():
    unique, dupes = _dedupe_entries([
        _entry(entry_id="a"), _entry(entry_id="b"), _entry(entry_id="a", title="DUP"),
    ])
    assert [e["entry_id"] for e in unique] == ["a", "b"]
    assert dupes == ["a"]
    assert unique[0]["title"] == "TEST & ENTRY_1"


def test_bundle_index_is_slim(tmp_path, monkeypatch):
    artifacts = tmp_path / "artifacts"
    (artifacts / "extract").mkdir(parents=True)
    (artifacts / "extract" / "entries.json").write_text(
        json.dumps([_entry()]), encoding="utf-8")
    import nemotron_challenge.site as site_mod
    monkeypatch.setattr(site_mod, "load_manifest", _manifest)

    payload = bundle_site_data(artifacts)
    card = payload["entries"][0]
    assert card["entry_id"] == "entry-test-1"
    assert card["detail_file"] == "data/entries/entry-test-1.json"
    assert card["pdf_file"] == "latex/entry-test-1.pdf"
    assert "text" not in card and "claims" not in card and "comparison" not in card
    assert card["compared"] is False
    assert payload["stats"]["entries_total"] == 1


def test_write_entry_details_full_text_and_scans(tmp_path):
    wiki_cache = tmp_path / "wiki"
    wiki_cache.mkdir()
    (wiki_cache / "42.json").write_text(json.dumps({
        "page_id": "42", "revision_id": "9", "title": "T", "url": "u",
        "text": "Full article text.", "provenance": {"text_sha256": "b" * 64},
        "returned_chars": 18, "total_chars": 18,
    }), encoding="utf-8")
    matches = {"entry-test-1": {"entry_id": "entry-test-1", "matched": True,
                                "selected_candidate": {"page_id": "42"}}}
    out_dir = tmp_path / "site" / "data" / "entries"
    count = write_entry_details([_entry()], matches, {}, {}, [], _pages_by_id(), wiki_cache, out_dir)
    assert count == 1
    detail = json.loads((out_dir / "entry-test-1.json").read_text())
    assert detail["entry"]["text"].startswith("Historical text")
    assert detail["wikipedia"]["available"] is True
    assert detail["wikipedia"]["text"] == "Full article text."
    assert detail["scans"][0]["path"] == "scans/page-0001-abc.jpg"
    assert detail["documents"]["pdf"] == "latex/entry-test-1.pdf"


def test_write_entry_details_uncached_wikipedia(tmp_path):
    out_dir = tmp_path / "site" / "data" / "entries"
    write_entry_details([_entry()], {}, {}, {}, [], _pages_by_id(), tmp_path / "wiki", out_dir)
    detail = json.loads((out_dir / "entry-test-1.json").read_text())
    assert detail["wikipedia"]["available"] is False


def test_copy_site_assets_copies_scans(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "page-0001-abc.jpg").write_bytes(b"fakejpg")
    manifest = _manifest()
    manifest["pages"][0]["image_sha256"] = "5be835282beffbdde9d8f3b4d0f6a7b2b2cf60df4a1d1cf3f0cb4a9ce4b5e0ef"
    site_dir = tmp_path / "site"
    counts = copy_site_assets(site_dir, tmp_path / "art", manifest, raw_dir, None)
    assert counts["scans"] == 1
    assert (site_dir / "scans" / "page-0001-abc.jpg").read_bytes() == b"fakejpg"


def test_build_site_manifest_hashes_every_file(tmp_path):
    site_dir = tmp_path / "site"
    (site_dir / "data").mkdir(parents=True)
    (site_dir / "data" / "x.json").write_text("{}")
    (site_dir / "index.html").write_text("<html></html>")
    manifest = build_site_manifest(site_dir)
    assert manifest["index.html"] == manifest["index.html"]
    assert set(manifest) == {"index.html", "data/x.json"}
    assert (site_dir / "site_manifest.json").is_file()
    assert "site_manifest.json" not in manifest


def test_verify_site_links_reports_missing(tmp_path):
    site_dir = tmp_path / "site"
    (site_dir / "data").mkdir(parents=True)
    (site_dir / "index.html").write_text('<html><a href="latex/x.pdf">d</a></html>')
    (site_dir / "data" / "challenge_data.json").write_text("{}")
    payload = {"entries": [
        {"entry_id": "e1", "detail_file": "data/entries/e1.json",
         "latex_file": "latex/e1.tex", "pdf_file": "latex/e1.pdf"},
    ]}
    report = verify_site_links(site_dir, payload, compiled_pdf_ids={"e1"})
    broken = set(report["broken"])
    assert "data/entries/e1.json" in broken
    assert "latex/e1.tex" in broken
    assert "latex/e1.pdf" in broken
    assert "latex/x.pdf" in broken
    assert report["links_checked"] > report["links_broken"]


def test_verify_site_links_pdf_optional_when_not_compiled(tmp_path):
    site_dir = tmp_path / "site"
    (site_dir / "data").mkdir(parents=True)
    (site_dir / "data" / "entries").mkdir(parents=True)
    (site_dir / "latex").mkdir(parents=True)
    (site_dir / "index.html").write_text("<html></html>")
    (site_dir / "data" / "challenge_data.json").write_text("{}")
    (site_dir / "data" / "entries" / "e1.json").write_text("{}")
    (site_dir / "latex" / "e1.tex").write_text("x")
    payload = {"entries": [
        {"entry_id": "e1", "detail_file": "data/entries/e1.json",
         "latex_file": "latex/e1.tex", "pdf_file": "latex/e1.pdf"},
    ]}
    report = verify_site_links(site_dir, payload, compiled_pdf_ids=set())
    assert report["links_broken"] == 0


def test_compile_latex_without_tectonic_reports_honestly(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    report = compile_latex_documents(tmp_path)
    assert report["compiled"] == 0
    assert "not found" in report["error"]


def test_compile_latex_with_fake_tectonic(tmp_path, monkeypatch):
    (tmp_path / "doc.tex").write_text("\\documentclass{article}\\begin{document}x\\end{document}")

    def fake_run(cmd, **kwargs):
        (tmp_path / "doc.pdf").write_bytes(b"%PDF-fake")
        class Proc:
            returncode = 0
            stdout = ""
            stderr = ""
        return Proc()

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/tectonic" if name == "tectonic" else None)
    monkeypatch.setattr(subprocess, "run", fake_run)
    report = compile_latex_documents(tmp_path)
    assert report["compiled"] == 1
    assert report["failed"] == []
    assert json.loads((tmp_path / "compile_report.json").read_text())["compiled"] == 1


def test_compile_latex_records_failure(tmp_path, monkeypatch):
    (tmp_path / "bad.tex").write_text("\\documentclass{article}\\begin{document}\\bad")

    def fake_run(cmd, **kwargs):
        class Proc:
            returncode = 1
            stdout = ""
            stderr = "error: something failed"
        return Proc()

    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/tectonic" if name == "tectonic" else None)
    monkeypatch.setattr(subprocess, "run", fake_run)
    report = compile_latex_documents(tmp_path)
    assert report["compiled"] == 0
    assert report["failed"][0]["file"] == "bad.tex"
    assert "something failed" in report["failed"][0]["error"]
