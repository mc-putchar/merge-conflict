"""Static website generation and LaTeX document compilation for challenge deliverables."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .config import Settings
from .contracts import ArtifactRecord, SourceReference
from .data import load_manifest
from .storage import LanceArtifactStore

SCANS_SUBDIR = "scans"
LATEX_SUBDIR = "latex"
ENTRIES_SUBDIR = "data/entries"
PLOTS_SUBDIR = "plots"
AGENT_SUBDIR = "agent"
EVALUATE_SUBDIR = "evaluate"


_LATEX_ESCAPES = {
    "\\": "\\textbackslash{}",
    "&": "\\&",
    "%": "\\%",
    "$": "\\$",
    "#": "\\#",
    "_": "\\_",
    "{": "\\{",
    "}": "\\}",
    "~": "\\textasciitilde{}",
    "^": "\\textasciicircum{}",
}


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters in historical and extracted text."""
    if not text:
        return ""
    # Single-pass map: inserted escapes are never re-escaped.
    return "".join(_LATEX_ESCAPES.get(char, char) for char in text)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_latex_document(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    pages_by_id: dict[str, dict[str, Any]],
    match_record: dict[str, Any] | None = None,
    scan_dir: str = "../scans",
) -> str:
    """Generate a valid standalone LaTeX document conforming to templates/page.tex."""
    title = entry.get("title", "Untitled Entry")
    escaped_title = escape_latex(title)
    text = entry.get("text", "")
    escaped_text = escape_latex(text) if text.strip() else "\\textit{(No textual content; illustration plate or empty scan.)}"

    source_pages = entry.get("source_pages", [])
    page_items = []
    scan_figures = []
    for pid in source_pages:
        pmeta = pages_by_id.get(pid, {})
        fn = pmeta.get("filename", "unknown")
        sha = pmeta.get("image_sha256", "unknown")
        row = pmeta.get("row_index", "unknown")
        page_items.append(
            f"\\item \\textbf{{Page ID:}} \\texttt{{{escape_latex(pid)}}} \\\\\n"
            f"  \\textbf{{Filename:}} \\texttt{{{escape_latex(fn)}}} \\\\\n"
            f"  \\textbf{{Row Index:}} {row} \\\\\n"
            f"  \\textbf{{SHA256:}} \\texttt{{{sha[:16]}...}}"
        )
        if fn != "unknown":
            scan_figures.append(
                "\\begin{figure}[h]\n\\centering\n"
                f"\\includegraphics[width=0.85\\textwidth]{{{scan_dir}/{fn}}}\n"
                f"\\caption*{{Source scan: \\texttt{{{escape_latex(fn)}}}}}\n"
                "\\end{figure}"
            )
    source_pages_tex = "\n".join(page_items) if page_items else "\\item None recorded"
    scans_tex = "\n".join(scan_figures)

    match_info_tex = ""
    if match_record and match_record.get("selected_candidate"):
        cand = match_record["selected_candidate"]
        wiki_title = escape_latex(cand.get("title", ""))
        wiki_pid = cand.get("page_id", "")
        wiki_rev = cand.get("revision_id", "")
        wiki_url = escape_latex(cand.get("url", ""))
        match_info_tex = (
            "\\subsection*{Matched Wikipedia Article}\n"
            f"\\textbf{{Title:}} {wiki_title} \\\\\n"
            f"\\textbf{{Page ID:}} {wiki_pid} \\\\\n"
            f"\\textbf{{Revision ID:}} {wiki_rev} \\\\\n"
            f"\\textbf{{URL:}} \\url{{{wiki_url}}}\n"
        )

    revision = manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443")
    dataset = manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated")

    return f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{graphicx}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\geometry{{margin=1in}}

\\title{{{escaped_title}}}
\\date{{Encyclopaedia Britannica (1771)}}

\\begin{{document}}
\\maketitle

\\section*{{Historical source}}
\\textbf{{Entry ID:}} \\texttt{{{escape_latex(entry.get("entry_id", ""))}}} \\\\
\\textbf{{Volume ID:}} {entry.get("volume_id", "N/A")} \\\\
\\textbf{{Character Count:}} {entry.get("character_count", len(text))}

\\subsection*{{Extracted Text}}
{escaped_text}

{match_info_tex}

\\section*{{Source record}}
\\begin{{itemize}}
\\item \\textbf{{Dataset:}} \\texttt{{{escape_latex(dataset)}}}
\\item \\textbf{{Dataset Revision:}} \\texttt{{{escape_latex(revision)}}}
{source_pages_tex}
\\end{{itemize}}

{scans_tex}

\\end{{document}}
"""


def _first_heading(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            return line.lstrip("#").strip()
    return path.stem


def bundle_site_data(
    artifacts_dir: Path,
    agent_runs_dir: Path | None = None,
    evaluate_dir: Path | None = None,
) -> dict[str, Any]:
    """Gather stage outputs into a slim index payload; per-entry detail is separate."""
    manifest = load_manifest()

    extract_file = artifacts_dir / "extract" / "entries.json"
    entries = json.loads(extract_file.read_text(encoding="utf-8")) if extract_file.is_file() else []

    matches_file = artifacts_dir / "match" / "matches.json"
    matches = {m["entry_id"]: m for m in json.loads(matches_file.read_text(encoding="utf-8"))} if matches_file.is_file() else {}

    unmatched_file = artifacts_dir / "match" / "unmatched.json"
    unmatched = {u["entry_id"]: u for u in json.loads(unmatched_file.read_text(encoding="utf-8"))} if unmatched_file.is_file() else {}

    compare_summary_file = artifacts_dir / "compare" / "summary.json"
    compare_summary = json.loads(compare_summary_file.read_text(encoding="utf-8")) if compare_summary_file.is_file() else {}

    comparisons_file = artifacts_dir / "compare" / "comparisons.json"
    comparisons = {c["entry_id"]: c for c in json.loads(comparisons_file.read_text(encoding="utf-8"))} if comparisons_file.is_file() else {}

    exclusions_file = artifacts_dir / "compare" / "exclusions.json"
    exclusions = json.loads(exclusions_file.read_text(encoding="utf-8")) if exclusions_file.is_file() else []

    topics_file = artifacts_dir / "compare" / "topics.json"
    topics = json.loads(topics_file.read_text(encoding="utf-8")) if topics_file.is_file() else []

    plots_manifest_file = artifacts_dir / "compare" / "plots" / "plots_manifest.json"
    plots_meta = json.loads(plots_manifest_file.read_text(encoding="utf-8")) if plots_manifest_file.is_file() else {}
    plots = [
        {"file": f"{PLOTS_SUBDIR}/{name}", **{k: v for k, v in info.items() if k != "file"}}
        for name, info in plots_meta.items()
    ] if isinstance(plots_meta, dict) else []

    # Enrich agent run rows with the saved run records
    agent_runs = []
    records_file = artifacts_dir / "agent" / "records.json"
    summary_rows = json.loads(records_file.read_text(encoding="utf-8")) if records_file.is_file() else []
    for row in summary_rows:
        run_file = row.get("run", "")
        detail = {}
        if agent_runs_dir is not None and run_file:
            run_path = agent_runs_dir / run_file
            if run_path.is_file():
                detail = json.loads(run_path.read_text(encoding="utf-8"))
        agent_runs.append({
            "run": run_file,
            "status": row.get("status", "unknown"),
            "tool_calls": row.get("tool_calls", []),
            "query": detail.get("query", ""),
            "model": detail.get("model", ""),
            "final_text": detail.get("final_text", ""),
            "exit_code": detail.get("exit_code"),
            "verification": detail.get("verification", {}),
            "file": f"{AGENT_SUBDIR}/{run_file}" if run_file else "",
        })

    # Case studies and submission document from the evaluate stage
    case_studies = []
    submission_doc = ""
    if evaluate_dir is not None and evaluate_dir.is_dir():
        for md in sorted(evaluate_dir.glob("*.md")):
            target = f"{EVALUATE_SUBDIR}/{md.name}"
            if md.name == "submission.md":
                submission_doc = target
            else:
                case_studies.append({"file": target, "title": _first_heading(md)})

    # Slim entry cards; full text/claims/chunks live in data/entries/<id>.json
    entry_cards = []
    for entry in entries:
        eid = entry["entry_id"]
        match_info = matches.get(eid)
        comp_info = comparisons.get(eid)
        unmatch_info = unmatched.get(eid)
        cand = (match_info or {}).get("selected_candidate") or {}
        meta = entry.get("metadata") or {}
        entry_cards.append({
            "entry_id": eid,
            "title": entry["title"],
            "character_count": entry.get("character_count", 0),
            "volume_id": entry.get("volume_id", ""),
            "is_continuation": entry.get("is_continuation", False),
            "is_plate": bool(meta.get("is_illustration_plate")),
            "matched": match_info is not None,
            "compared": comp_info is not None,
            "match_status": (match_info or unmatch_info or {}).get("status", "unmatched"),
            "wikipedia_title": cand.get("title", ""),
            "wikipedia_url": cand.get("url", ""),
            "length_ratio": comp_info.get("length_ratio") if comp_info else None,
            "topic_id": comp_info.get("topic_id") if comp_info else None,
            "topic_terms": comp_info.get("topic_terms", []) if comp_info else [],
            "claims_count": len(comp_info.get("claims", [])) if comp_info else 0,
            "detail_file": f"{ENTRIES_SUBDIR}/{eid}.json",
            "latex_file": f"{LATEX_SUBDIR}/{eid}.tex",
            "pdf_file": f"{LATEX_SUBDIR}/{eid}.pdf",
        })

    return {
        "dataset_manifest": {
            "dataset": manifest.get("dataset"),
            "revision": manifest.get("revision"),
            "scans_total": len(manifest.get("pages", [])),
        },
        "stats": {
            "entries_total": len(entries),
            "matches_accepted": len(matches),
            "matches_rejected": len(unmatched),
            "compared_count": len(comparisons),
            "excluded_count": len(exclusions),
            "plates_recovered": sum(1 for e in entries if (e.get("metadata") or {}).get("is_illustration_plate")),
        },
        "compare_summary": compare_summary,
        "topics": topics,
        "exclusions": exclusions,
        "entries": entry_cards,
        "plots": plots,
        "agent_runs": agent_runs,
        "case_studies": case_studies,
        "submission_doc": submission_doc,
    }


def write_entry_details(
    entries: list[dict[str, Any]],
    matches: dict[str, Any],
    unmatched: dict[str, Any],
    comparisons: dict[str, Any],
    exclusions: list[dict[str, Any]],
    pages_by_id: dict[str, dict[str, Any]],
    wiki_cache_dir: Path,
    entries_out_dir: Path,
) -> int:
    """Emit per-entry detail JSON with full text, evidence, and asset paths."""
    exclusions_by_id = {e["entry_id"]: e for e in exclusions}
    entries_out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for entry in entries:
        eid = entry["entry_id"]
        match_info = matches.get(eid)
        comp_info = comparisons.get(eid)
        cand = (match_info or {}).get("selected_candidate") or {}

        # Cached verified Wikipedia article text (offline read; never fetched here)
        wiki_text = {"available": False}
        page_id = cand.get("page_id") or (comp_info or {}).get("wikipedia_page_id")
        if page_id:
            cache_path = wiki_cache_dir / f"{page_id}.json"
            if cache_path.is_file():
                article = json.loads(cache_path.read_text(encoding="utf-8"))
                wiki_text = {
                    "available": True,
                    "text": article.get("text", ""),
                    "title": article.get("title", ""),
                    "url": article.get("url", ""),
                    "page_id": article.get("page_id", page_id),
                    "revision_id": article.get("revision_id", ""),
                    "text_sha256": (article.get("provenance") or {}).get("text_sha256", ""),
                    "truncated": article.get("returned_chars", 0) < article.get("total_chars", 0),
                }

        scans = []
        for pid in entry.get("source_pages", []):
            pmeta = pages_by_id.get(pid, {})
            scans.append({
                "page_id": pid,
                "filename": pmeta.get("filename", ""),
                "image_sha256": pmeta.get("image_sha256", ""),
                "row_index": pmeta.get("row_index"),
                "path": f"{SCANS_SUBDIR}/{pmeta.get('filename', '')}" if pmeta.get("filename") else "",
            })

        detail = {
            "entry": entry,
            "match": match_info or unmatched.get(eid),
            "comparison": comp_info,
            "exclusion": exclusions_by_id.get(eid),
            "wikipedia": wiki_text,
            "scans": scans,
            "documents": {
                "tex": f"{LATEX_SUBDIR}/{eid}.tex",
                "pdf": f"{LATEX_SUBDIR}/{eid}.pdf",
            },
        }
        (entries_out_dir / f"{eid}.json").write_text(
            json.dumps(detail, indent=2), encoding="utf-8")
        count += 1
    return count


def copy_site_assets(
    site_dir: Path,
    artifacts_dir: Path,
    manifest: dict[str, Any],
    raw_dir: Path,
    evaluate_src: Path | None,
) -> dict[str, int]:
    """Copy scans, plots, agent run records, and evaluate docs into the site."""
    counts = {"scans": 0, "plots": 0, "agent_runs": 0, "evaluate_docs": 0}

    scans_dir = site_dir / SCANS_SUBDIR
    scans_dir.mkdir(parents=True, exist_ok=True)
    for page in manifest.get("pages", []):
        src = raw_dir / page["filename"]
        if src.is_file():
            dst = scans_dir / page["filename"]
            if not dst.exists() or _sha256_file(dst) != page.get("image_sha256"):
                shutil.copy2(src, dst)
            counts["scans"] += 1

    plots_src = artifacts_dir / "compare" / "plots"
    if plots_src.is_dir():
        plots_dir = site_dir / PLOTS_SUBDIR
        plots_dir.mkdir(parents=True, exist_ok=True)
        for f in plots_src.iterdir():
            if f.is_file():
                shutil.copy2(f, plots_dir / f.name)
                counts["plots"] += 1

    agent_src = artifacts_dir / "agent"
    if agent_src.is_dir():
        agent_dir = site_dir / AGENT_SUBDIR
        agent_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(agent_src.glob("*.json")) + sorted((agent_src / "runs").glob("*.json")):
            shutil.copy2(f, agent_dir / f.name)
            counts["agent_runs"] += 1

    if evaluate_src is not None and evaluate_src.is_dir():
        eval_dir = site_dir / EVALUATE_SUBDIR
        eval_dir.mkdir(parents=True, exist_ok=True)
        for f in evaluate_src.glob("*.md"):
            shutil.copy2(f, eval_dir / f.name)
            counts["evaluate_docs"] += 1

    return counts


def compile_latex_documents(latex_dir: Path) -> dict[str, Any]:
    """Compile every .tex to .pdf with tectonic; failures are reported, not hidden."""
    tectonic = shutil.which("tectonic")
    report: dict[str, Any] = {
        "tectonic": tectonic or "",
        "compiled": 0,
        "failed": [],
    }
    if not tectonic:
        report["error"] = "tectonic not found on PATH; .tex sources were generated but not compiled"
        return report

    for tex_file in sorted(latex_dir.glob("*.tex")):
        try:
            proc = subprocess.run(
                [tectonic, "--outdir", ".", tex_file.name],
                cwd=str(latex_dir), capture_output=True, text=True, timeout=180,
            )
            if proc.returncode == 0 and tex_file.with_suffix(".pdf").is_file():
                report["compiled"] += 1
            else:
                report["failed"].append({
                    "file": tex_file.name,
                    "error": (proc.stdout + proc.stderr)[-2000:],
                })
        except (subprocess.TimeoutExpired, OSError) as exc:
            report["failed"].append({"file": tex_file.name, "error": f"{type(exc).__name__}: {exc}"})

    (latex_dir / "compile_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_site_manifest(site_dir: Path) -> dict[str, str]:
    """SHA-256 every emitted file; the manifest itself is excluded."""
    manifest: dict[str, str] = {}
    for path in sorted(site_dir.rglob("*")):
        if path.is_file() and path.name != "site_manifest.json":
            manifest[str(path.relative_to(site_dir))] = _sha256_file(path)
    (site_dir / "site_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_site_links(
    site_dir: Path,
    payload: dict[str, Any],
    compiled_pdf_ids: set[str],
) -> dict[str, Any]:
    """Check every declared site asset exists; report broken references."""
    expected: list[str] = ["index.html", "data/challenge_data.json"]
    for card in payload.get("entries", []):
        expected.append(card["detail_file"])
        expected.append(card["latex_file"])
        if card["entry_id"] in compiled_pdf_ids:
            expected.append(card["pdf_file"])
    expected += [p["file"] for p in payload.get("plots", [])]
    expected += [r["file"] for r in payload.get("agent_runs", []) if r.get("file")]
    expected += [c["file"] for c in payload.get("case_studies", [])]
    if payload.get("submission_doc"):
        expected.append(payload["submission_doc"])

    # Scan images referenced by entry detail files
    entries_dir = site_dir / ENTRIES_SUBDIR
    if entries_dir.is_dir():
        for detail_file in entries_dir.glob("*.json"):
            detail = json.loads(detail_file.read_text(encoding="utf-8"))
            expected += [s["path"] for s in detail.get("scans", []) if s.get("path")]

    # Internal href/src targets in index.html (skip absolute URLs and _app assets)
    index_file = site_dir / "index.html"
    if index_file.is_file():
        html = index_file.read_text(encoding="utf-8")
        for ref in re.findall(r'(?:href|src)="([^"#]+)"', html):
            if ref.startswith(("http://", "https://", "data:", "mailto:")):
                continue
            ref = ref.lstrip("./")
            if ref and not ref.startswith("_app"):
                expected.append(ref)

    broken = [p for p in sorted(set(expected)) if not (site_dir / p).is_file()]
    report = {
        "links_checked": len(set(expected)),
        "links_broken": len(broken),
        "broken": broken,
    }
    (site_dir / "site_verify.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def build_site(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Compile LaTeX documents and build the SvelteKit static website."""
    work_dir = Path(work_dir)
    site_dir = work_dir / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    latex_dir = site_dir / LATEX_SUBDIR

    artifacts_dir = work_dir if (work_dir / "extract").is_dir() else Path("artifacts")
    manifest = load_manifest()
    pages_by_id = {page["page_id"]: page for page in manifest.get("pages", [])}
    raw_dir = Path("data/raw/britannica")
    wiki_cache_dir = Path(os.environ.get("WIKI_CACHE_DIR", "data/cache/wikipedia"))

    extract_file = artifacts_dir / "extract" / "entries.json"
    if not extract_file.is_file():
        raise FileNotFoundError(f"Extract entries not found at {extract_file}. Run extract stage first.")
    entries = json.loads(extract_file.read_text(encoding="utf-8"))

    matches_file = artifacts_dir / "match" / "matches.json"
    matches = {m["entry_id"]: m for m in json.loads(matches_file.read_text(encoding="utf-8"))} if matches_file.is_file() else {}
    unmatched_file = artifacts_dir / "match" / "unmatched.json"
    unmatched = {u["entry_id"]: u for u in json.loads(unmatched_file.read_text(encoding="utf-8"))} if unmatched_file.is_file() else {}
    comparisons_file = artifacts_dir / "compare" / "comparisons.json"
    comparisons = {c["entry_id"]: c for c in json.loads(comparisons_file.read_text(encoding="utf-8"))} if comparisons_file.is_file() else {}
    exclusions_file = artifacts_dir / "compare" / "exclusions.json"
    exclusions = json.loads(exclusions_file.read_text(encoding="utf-8")) if exclusions_file.is_file() else []

    agent_runs_dir = artifacts_dir / "agent" / "runs"
    evaluate_src = artifacts_dir / "evaluate"

    # 1. Bundle slim index data for frontend
    data_payload = bundle_site_data(artifacts_dir, agent_runs_dir, evaluate_src)

    # 2. Write data to frontend static directory and lib directory
    frontend_dir = Path("frontend")
    static_data_dir = frontend_dir / "static" / "data"
    static_data_dir.mkdir(parents=True, exist_ok=True)
    (static_data_dir / "challenge_data.json").write_text(
        json.dumps(data_payload, indent=2), encoding="utf-8"
    )

    src_lib_dir = frontend_dir / "src" / "lib"
    src_lib_dir.mkdir(parents=True, exist_ok=True)
    (src_lib_dir / "challenge_data.json").write_text(
        json.dumps(data_payload, indent=2), encoding="utf-8"
    )

    # 3. Run SvelteKit build if frontend directory exists and node/pnpm is available
    svelte_built = False
    build_error = ""
    pnpm_path = shutil.which("pnpm") or shutil.which("npm")
    if frontend_dir.is_dir() and pnpm_path:
        env = {
            **os.environ,
            "BUILD_OUT_DIR": str(site_dir.resolve()),
        }
        cmd = [pnpm_path, "run", "build"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(frontend_dir),
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if proc.returncode == 0:
                svelte_built = True
            else:
                build_error = f"pnpm build exited {proc.returncode}: {proc.stderr[:1000]}"
        except Exception as exc:
            build_error = f"pnpm build failed: {exc}"

    # 4. Emit site data: index JSON + per-entry detail JSONs
    (site_dir / "data").mkdir(parents=True, exist_ok=True)
    (site_dir / "data" / "challenge_data.json").write_text(
        json.dumps(data_payload, indent=2), encoding="utf-8"
    )
    entry_details = write_entry_details(
        entries, matches, unmatched, comparisons, exclusions,
        pages_by_id, wiki_cache_dir, site_dir / ENTRIES_SUBDIR,
    )

    # 5. Copy scans, plots, agent run records, and evaluate documents
    asset_counts = copy_site_assets(site_dir, artifacts_dir, manifest, raw_dir, evaluate_src)

    # 6. Generate LaTeX documents for every extracted entry, then compile to PDF.
    # The SvelteKit build above may wipe site_dir; create dirs only after it.
    latex_dir.mkdir(parents=True, exist_ok=True)
    latex_count = 0
    for entry in entries:
        eid = entry["entry_id"]
        tex_content = generate_latex_document(entry, manifest, pages_by_id, matches.get(eid))
        (latex_dir / f"{eid}.tex").write_text(tex_content, encoding="utf-8")
        latex_count += 1
    compile_report = compile_latex_documents(latex_dir)
    compiled_pdf_ids = {
        entry["entry_id"] for entry in entries
        if (latex_dir / f"{entry['entry_id']}.pdf").is_file()
    }

    # Ensure index.html exists even if SvelteKit build fails or node isn't available
    index_file = site_dir / "index.html"
    if not index_file.is_file():
        # Fallback clean self-contained HTML
        index_file.write_text(
            f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Britannica vs Wikipedia</title></head>
<body>
<h1>Nemotron Agentic AI Challenge — Deliverables</h1>
<p>Entries: {len(entries)}, Compared: {data_payload['stats']['compared_count']}</p>
<p>LaTeX documents generated: {latex_count}, PDFs compiled: {compile_report['compiled']}</p>
</body>
</html>""",
            encoding="utf-8",
        )

    # 7. Manifest of emitted files + link/asset verification
    file_manifest = build_site_manifest(site_dir)
    verify_report = verify_site_links(site_dir, data_payload, compiled_pdf_ids)

    # 8. Record artifact provenance to LanceDB with real checksums
    upstream = [
        ("extract/entries.json", manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated"),
         manifest.get("revision", ""), manifest.get("license", {}).get("spdx", "CC0-1.0")),
        ("match/matches.json", "wikimedia/structured-wikipedia", "417c267bb457fa645c22eb3b5c77764963194c70", "CC-BY-SA-4.0"),
        ("compare/comparisons.json", "wikimedia/structured-wikipedia", "417c267bb457fa645c22eb3b5c77764963194c70", "CC-BY-SA-4.0"),
        ("compare/summary.json", "wikimedia/structured-wikipedia", "417c267bb457fa645c22eb3b5c77764963194c70", "CC-BY-SA-4.0"),
        ("agent/records.json", manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated"),
         manifest.get("revision", ""), manifest.get("license", {}).get("spdx", "CC0-1.0")),
    ]
    sources = [
        SourceReference(
            dataset=dataset,
            dataset_revision=revision,
            source_id=rel_path,
            source_url="",
            content_sha256=_sha256_file(artifacts_dir / rel_path) if (artifacts_dir / rel_path).is_file() else "0" * 64,
            license=license_spdx,
        )
        for rel_path, dataset, revision, license_spdx in upstream
    ]
    store = LanceArtifactStore(settings.db_path)
    store.put(ArtifactRecord(
        record_id="site:static",
        stage="site",
        sources=sources,
        artifact_path=str(site_dir),
        metadata={
            "latex_count": latex_count,
            "pdfs_compiled": compile_report["compiled"],
            "latex_failures": len(compile_report["failed"]),
            "svelte_built": svelte_built,
            "entries_total": len(entries),
            "compared_count": data_payload["stats"]["compared_count"],
            "site_manifest_sha256": _sha256_file(site_dir / "site_manifest.json"),
            "files_in_manifest": len(file_manifest),
            "links_checked": verify_report["links_checked"],
            "links_broken": verify_report["links_broken"],
        },
    ))

    return {
        "stage": "site",
        "status": "completed" if not verify_report["broken"] else "degraded",
        "latex_documents_generated": latex_count,
        "pdfs_compiled": compile_report["compiled"],
        "latex_failures": len(compile_report["failed"]),
        "latex_compile_error": compile_report.get("error", ""),
        "svelte_built": svelte_built,
        "build_error": build_error,
        "entry_details_written": entry_details,
        "assets_copied": asset_counts,
        "files_in_manifest": len(file_manifest),
        "links_checked": verify_report["links_checked"],
        "links_broken": verify_report["links_broken"],
        "broken_links": verify_report["broken"],
        "site_dir": str(site_dir),
        "latex_dir": str(latex_dir),
        "database_path": str(settings.db_path),
    }
