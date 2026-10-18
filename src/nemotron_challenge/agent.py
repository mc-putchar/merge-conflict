"""Drive the Hermes comparison agent and record verifiable runs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .contracts import ArtifactRecord, SourceReference
from .storage import LanceArtifactStore

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_SOURCE = REPO_ROOT / "integrations" / "hermes" / "nemotron-challenge"
CONFIG_EXAMPLE = REPO_ROOT / "integrations" / "hermes" / "config.example.yaml"
HERMES_TIMEOUT_SECONDS = 300
STREAM_MAX_BYTES = 32 * 1024 * 1024


def ensure_hermes_profile(hermes_home: Path) -> Path:
    """Provision the challenge profile: config.yaml plus the current plugin code."""
    plugins_dir = hermes_home / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    config_path = hermes_home / "config.yaml"
    if not config_path.exists():
        shutil.copy(CONFIG_EXAMPLE, config_path)

    target = plugins_dir / "nemotron-challenge"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(PLUGIN_SOURCE, target)

    # Plugins are opt-in: enable it so its toolset reaches the model.
    try:
        subprocess.run(
            ["hermes", "plugins", "enable", "nemotron-challenge"],
            capture_output=True, text=True, timeout=120,
            env={**os.environ, "HERMES_HOME": str(hermes_home)},
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return plugins_dir / "nemotron-challenge"


def parse_stream_json(stdout: str) -> dict[str, Any]:
    """Parse hermes --format stream-json output into a structured run record."""
    record: dict[str, Any] = {
        "model": "", "session_id": "", "tool_uses": [], "tool_results": [],
        "final_text": "", "exit_code": None, "usage": {}, "events": 0,
    }
    text_parts: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        record["events"] += 1
        etype = event.get("type")
        if etype == "system" and event.get("subtype") == "init":
            record["model"] = event.get("model", "")
            record["session_id"] = event.get("session_id", "")
        elif etype == "tool_use":
            record["tool_uses"].append({
                "name": event.get("name", ""),
                "input": event.get("input", {}),
                "tool_call_id": event.get("tool_call_id", ""),
            })
        elif etype == "tool_result":
            record["tool_results"].append({
                "name": event.get("name", ""),
                "is_error": bool(event.get("is_error")),
                "output_preview": str(event.get("output", ""))[:500],
                "duration_ms": event.get("duration_ms", 0),
            })
        elif etype == "text":
            text_parts.append(str(event.get("text", "")))
        elif etype == "result":
            record["exit_code"] = event.get("exit_code", event.get("code"))
            record["usage"] = event.get("usage", event.get("tokens", {}))
            if event.get("text"):
                record["final_text"] = str(event["text"])
    if not record["final_text"]:
        record["final_text"] = "".join(text_parts)
    return record


def run_agent_query(
    query: str,
    settings: Any,
    hermes_home: Path,
    artifacts_dir: Path,
) -> dict[str, Any]:
    """Run one headless Hermes query and return its parsed run record."""
    env = dict(os.environ)
    env["HERMES_HOME"] = str(hermes_home)
    env["CHALLENGE_ARTIFACTS_DIR"] = str(artifacts_dir)
    if getattr(settings, "super_api_key", ""):
        env["SUPER_API_KEY"] = settings.super_api_key

    command = [
        "hermes", "chat", "-q", query, "--oneshot",
        "-t", "nemotron_challenge", "--format", "stream-json",
    ]
    record: dict[str, Any] = {"query": query, "command": " ".join(command[:5] + ["..."]),
                              "model": "", "session_id": "", "tool_uses": [], "tool_results": [],
                              "final_text": "", "exit_code": None, "usage": {}, "events": 0,
                              "spawn_error": ""}
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=HERMES_TIMEOUT_SECONDS,
            env=env, cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        record["spawn_error"] = f"{type(exc).__name__}: {exc}"
        record["exit_code"] = -1
        return record

    record["exit_code"] = proc.returncode
    record["stderr_tail"] = proc.stderr[-2000:]
    if len(proc.stdout) > STREAM_MAX_BYTES:
        record["spawn_error"] = "stream-json output exceeded the 32 MiB cap"
        return record
    record.update({k: v for k, v in parse_stream_json(proc.stdout).items() if k != "exit_code"})
    record["raw_stdout_path"] = ""
    record["_raw_stdout"] = proc.stdout
    return record


def verify_run(record: dict[str, Any], expected_model_fragment: str, *, expects_tools: bool = True,
               expects_missing_evidence: bool = False) -> dict[str, Any]:
    """Score a parsed run record. Never invents a pass — failures stay recorded."""
    checks: list[dict[str, Any]] = []
    notes: list[str] = []

    def check(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    if record.get("spawn_error"):
        check("spawned", False, record["spawn_error"])
        return {"status": "failure", "checks": checks, "notes": notes}

    model = record.get("model", "")
    check("model_id", expected_model_fragment.split("/")[-1].lower() in model.lower() or
          expected_model_fragment.lower() in model.lower(),
          f"model reported: {model or 'none'}")

    tool_names = [t.get("name", "") for t in record.get("tool_uses", [])]
    challenge_tools = [n for n in tool_names if n.startswith("challenge_")]
    if expects_tools:
        check("tool_use", bool(challenge_tools), f"tools called: {tool_names or 'none'}")
    else:
        check("tool_use", True, f"tools called: {tool_names or 'none'}")

    results = record.get("tool_results", [])
    error_results = [r for r in results if r.get("is_error")]
    check("tool_results_ok", not error_results or len(error_results) < len(results),
          f"{len(error_results)}/{len(results)} tool results errored")

    final = record.get("final_text", "")
    check("final_answer", bool(final.strip()), f"final answer {len(final)} chars")

    if expects_missing_evidence and final.strip():
        honest = any(word in final.lower() for word in
                     ("no evidence", "missing", "not matched", "no comparison", "unavailable",
                      "excluded", "could not", "cannot", "no matching"))
        check("missing_evidence_acknowledged", honest,
              "answer does not acknowledge missing evidence" if not honest else "")
        invented = re.findall(r"page[_ ]?id[:# ]*[0-9]{3,}", final.lower())
        if honest and invented:
            notes.append("answer acknowledges missing evidence but still cites page ids; inspect manually")
    return {
        "status": "success" if all(c["passed"] for c in checks) else "failure",
        "checks": checks, "notes": notes,
    }


def record_agent_provenance(
    store: LanceArtifactStore,
    record: dict[str, Any],
    verification: dict[str, Any],
    artifact_path: Path,
    manifest: dict[str, Any],
    index: int,
) -> None:
    """Persist a run record pointer. The transcript file carries the citations."""
    store.put(ArtifactRecord(
        record_id=f"agent:run:{index}",
        stage="agent",
        sources=[SourceReference(
            dataset=manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated"),
            dataset_revision=manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443"),
            source_id="compare-summary",
            source_url=manifest.get("source_url", ""),
            content_sha256=hashlib.sha256(
                json.dumps(record.get("tool_results", []), sort_keys=True).encode()
            ).hexdigest(),
            license=manifest.get("license", {}).get("spdx", "CC0-1.0"),
        )],
        artifact_path=str(artifact_path),
        metadata={
            "query": record.get("query", ""),
            "model": record.get("model", ""),
            "session_id": record.get("session_id", ""),
            "tool_calls": [t.get("name") for t in record.get("tool_uses", [])],
            "tool_errors": sum(1 for r in record.get("tool_results", []) if r.get("is_error")),
            "status": verification.get("status", "failure"),
            "checks": verification.get("checks", []),
            "notes": verification.get("notes", []),
        },
    ))


def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:limit] or "run"
