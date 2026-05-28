from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import TOOL_NAMES, build_server, describe_tool_surface


def test_required_phase_1_scaffold_files_exist_and_are_wired() -> None:
    required_paths = (
        ROOT / ".claude-plugin" / "plugin.json",
        ROOT / "agents" / "foundry" / "AGENT.md",
        ROOT / ".mcp.json",
        ROOT / "settings.json",
        ROOT / "server" / "pyproject.toml",
        ROOT / "server" / "__init__.py",
        ROOT / "server" / "main.py",
        ROOT / "server" / "tool_schemas.py",
        ROOT / "server" / "exceptions.py",
        ROOT / "tests" / "server" / "test_runtime_scaffold.py",
    )

    missing = [str(path.relative_to(ROOT)) for path in required_paths if not path.exists()]
    assert missing == []

    plugin_manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin_manifest["agents"] == "./agents/foundry/AGENT.md"
    assert plugin_manifest["mcpServers"] == "./.mcp.json"

    settings = json.loads((ROOT / "settings.json").read_text())
    assert settings == {"agent": "foundry"}


def test_tool_surface_matches_phase_1_contract() -> None:
    assert [entry["name"] for entry in describe_tool_surface()] == list(TOOL_NAMES)
    assert describe_tool_surface()[0]["request_model"] == "DraftSpecRequest"
    assert describe_tool_surface()[0]["response_model"] == "DraftSpecResponse"


def test_build_server_marks_expected_registered_tools() -> None:
    server = build_server()
    assert server._foundry_registered_tools == TOOL_NAMES  # type: ignore[attr-defined]


def test_mcp_entrypoint_boots_from_configured_runtime() -> None:
    mcp_config = json.loads((ROOT / ".mcp.json").read_text())
    runtime = mcp_config["mcpServers"]["foundry"]

    command = [runtime["command"], *runtime["args"]]
    command = [part.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT)) for part in command]
    cwd = runtime["cwd"].replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))

    env = os.environ.copy()
    env.update(
        {
            key: value.replace("${CLAUDE_PLUGIN_ROOT}", str(ROOT))
            for key, value in runtime.get("env", {}).items()
        }
    )
    env["FOUNDRY_EXIT_AFTER_STARTUP"] = "1"

    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip())
    assert payload == {
        "status": "booted",
        "server": "api-spec-foundry",
        "version": "0.1.0",
        "tool_count": 7,
    }
