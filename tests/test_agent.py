"""Unit tests for the Hermes agent runner and run verification."""
import json
import subprocess
from pathlib import Path

from nemotron_challenge import agent as agent_mod
from nemotron_challenge.agent import (
    parse_stream_json, run_agent_query, slugify, verify_run,
)

INIT_LINE = {"type": "system", "subtype": "init",
             "model": "nvidia/Nemotron-3.5-Super-VL", "session_id": "sess-1"}
TOOL_USE = {"type": "tool_use", "name": "challenge_compare",
            "input": {"entry_id": "entry-optics-1"}, "tool_call_id": "t1"}
TOOL_RESULT = {"type": "tool_result", "name": "challenge_compare",
               "output": '{"status": "ok"}', "duration_ms": 5, "is_error": False,
               "tool_call_id": "t1"}
RESULT_OK = {"type": "result", "exit_code": 0,
             "text": "The entry differs [cited p1, page 42 rev 100].", "usage": {"total": 50}}


def _stream(events) -> str:
    return "\n".join(json.dumps(e) for e in events)


def test_parse_stream_json_extracts_events():
    record = parse_stream_json(_stream([
        INIT_LINE, TOOL_USE, TOOL_RESULT, {"type": "text", "text": "partial "},
        {"type": "text", "text": "answer"}, RESULT_OK,
    ]))
    assert record["model"] == "nvidia/Nemotron-3.5-Super-VL"
    assert record["session_id"] == "sess-1"
    assert record["tool_uses"][0]["name"] == "challenge_compare"
    assert record["tool_uses"][0]["input"]["entry_id"] == "entry-optics-1"
    assert record["tool_results"][0]["is_error"] is False
    assert record["final_text"] == "The entry differs [cited p1, page 42 rev 100]."
    assert record["exit_code"] == 0


def test_verify_run_success():
    record = parse_stream_json(_stream([INIT_LINE, TOOL_USE, TOOL_RESULT, RESULT_OK]))
    verdict = verify_run(record, "nvidia/Nemotron-3.5-Super-VL")
    assert verdict["status"] == "success"
    assert all(c["passed"] for c in verdict["checks"])


def test_verify_run_flags_wrong_model_and_no_tools():
    record = parse_stream_json(_stream([
        {"type": "system", "subtype": "init", "model": "gpt-other", "session_id": "s"},
        RESULT_OK,
    ]))
    verdict = verify_run(record, "nvidia/Nemotron-3.5-Super-VL")
    assert verdict["status"] == "failure"
    failed = {c["name"] for c in verdict["checks"] if not c["passed"]}
    assert "model_id" in failed and "tool_use" in failed


def test_verify_run_missing_evidence_probe():
    good = parse_stream_json(_stream([
        INIT_LINE, TOOL_USE,
        {"type": "tool_result", "name": "challenge_compare",
         "output": '{"status": "no_evidence"}', "duration_ms": 3,
         "is_error": False, "tool_call_id": "t1"},
        {"type": "result", "exit_code": 0,
         "text": "No comparison evidence exists for this entry; it was excluded.", "usage": {}},
    ]))
    verdict = verify_run(good, "super-vl", expects_missing_evidence=True)
    assert verdict["status"] == "success"

    bad = parse_stream_json(_stream([
        INIT_LINE, TOOL_USE, TOOL_RESULT,
        {"type": "result", "exit_code": 0,
         "text": "The Britannica entry says X and Wikipedia says Y.", "usage": {}},
    ]))
    verdict = verify_run(bad, "super-vl", expects_missing_evidence=True)
    assert verdict["status"] == "failure"
    failed = {c["name"] for c in verdict["checks"] if not c["passed"]}
    assert "missing_evidence_acknowledged" in failed


def test_verify_run_spawn_error():
    record = {"query": "q", "spawn_error": "FileNotFoundError: hermes", "exit_code": -1}
    verdict = verify_run(record, "super-vl")
    assert verdict["status"] == "failure"
    assert verdict["checks"][0]["name"] == "spawned"


def test_run_agent_query_parses_subprocess(monkeypatch, tmp_path):
    class FakeProc:
        returncode = 0
        stderr = ""
        stdout = _stream([INIT_LINE, TOOL_USE, TOOL_RESULT, RESULT_OK])

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs.get("env", {})
        return FakeProc()

    monkeypatch.setattr(agent_mod.subprocess, "run", fake_run)

    class Settings:
        super_api_key = "key-1"
        super_model = "nvidia/Nemotron-3.5-Super-VL"

    record = run_agent_query("Compare optics", Settings(), tmp_path, tmp_path)
    assert record["model"] == "nvidia/Nemotron-3.5-Super-VL"
    assert record["tool_uses"][0]["name"] == "challenge_compare"
    assert captured["env"]["HERMES_HOME"] == str(tmp_path)
    assert captured["env"]["SUPER_API_KEY"] == "key-1"
    assert captured["command"][:3] == ["hermes", "chat", "-q"]
    assert "nemotron_challenge" in captured["command"]


def test_run_agent_query_records_spawn_failure(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        raise FileNotFoundError("hermes not found")

    monkeypatch.setattr(agent_mod.subprocess, "run", fake_run)

    class Settings:
        super_api_key = ""
        super_model = "nvidia/Nemotron-3.5-Super-VL"

    record = run_agent_query("q", Settings(), tmp_path, tmp_path)
    assert record["exit_code"] == -1
    assert "hermes" in record["spawn_error"]


def test_ensure_hermes_profile_copies_plugin(monkeypatch, tmp_path):
    monkeypatch.setattr(agent_mod.subprocess, "run",
                        lambda *a, **k: type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})())
    hermes_home = tmp_path / "hermes"
    plugin_dir = agent_mod.ensure_hermes_profile(hermes_home)
    assert (hermes_home / "config.yaml").is_file()
    assert (plugin_dir / "__init__.py").is_file()
    assert (plugin_dir / "plugin.yaml").is_file()
    # Second run refreshes plugin code without clobbering config.
    (hermes_home / "config.yaml").write_text("# custom", encoding="utf-8")
    agent_mod.ensure_hermes_profile(hermes_home)
    assert (hermes_home / "config.yaml").read_text() == "# custom"


def test_slugify():
    assert slugify("Compare the OPTICS entry!") == "compare-the-optics-entry"
