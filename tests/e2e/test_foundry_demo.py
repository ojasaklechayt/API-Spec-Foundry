from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import TOOL_SURFACE, handle_draft_spec, handle_validate_spec
from server.tool_schemas import DraftSpecRequest, GenerateAllRequest, ValidateSpecRequest


def _task_manager_request() -> DraftSpecRequest:
    return DraftSpecRequest(
        project_name="Task Manager",
        auth="none",
        db_backend="sqlite",
        resources=[
            {
                "name": "User",
                "fields": [
                    {"name": "email", "type": "email", "required": True},
                    {"name": "name", "type": "string", "required": True},
                    {"name": "is_active", "type": "boolean", "required": True},
                ],
                "endpoints": ["list", "create", "get", "update", "delete"],
            },
            {
                "name": "Task",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": True},
                    {
                        "name": "due_date",
                        "type": "datetime",
                        "required": False,
                        "nullable": True,
                    },
                    {"name": "user_id", "type": "integer", "required": True},
                ],
                "endpoints": ["list", "create", "get", "update", "delete"],
            },
        ],
    )


def _generate_all_handler():
    for entry in TOOL_SURFACE:
        if entry["name"] == "generate_all":
            return entry["handler"]
    raise AssertionError("generate_all handler is not registered")


def test_task_manager_demo_generation_passes_generated_pytest(tmp_path: Path) -> None:
    draft_request = _task_manager_request()

    draft_response = handle_draft_spec(draft_request)
    assert draft_response.status == "ok"

    validate_response = handle_validate_spec(ValidateSpecRequest(spec=draft_response.spec_yaml))
    assert validate_response.status == "ok"
    assert validate_response.valid is True

    output_root = tmp_path / "generated-output"
    generate_request = GenerateAllRequest(
        spec=draft_response.spec_yaml,
        project_name=draft_request.project_name,
        output_dir=str(output_root),
    )
    generate_response = _generate_all_handler()(generate_request)

    if generate_response.status == "stub":
        pytest.xfail(
            "Story 17 dependency unresolved: generate_all is still scaffold-only in this branch."
        )

    assert generate_response.status == "ok"
    assert generate_response.files_written

    project_slug = "task-manager"
    generated_project = output_root / project_slug
    assert generated_project.exists(), (
        f"Expected generated project at {generated_project}, "
        f"files_written={generate_response.files_written}"
    )
    assert (generated_project / "pyproject.toml").exists()
    assert any(path.startswith("tests/") for path in generate_response.files_written)

    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(generated_project),
            "pytest",
        ],
        cwd=generated_project,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, (
        f"Generated pytest failed for {generated_project}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
