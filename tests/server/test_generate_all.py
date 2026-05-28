from __future__ import annotations

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import handle_draft_spec, handle_generate_all
from server.tool_schemas import DraftSpecRequest, GenerateAllRequest


def _request() -> DraftSpecRequest:
    return DraftSpecRequest(
        project_name="Task Manager",
        auth="none",
        db_backend="sqlite",
        resources=[
            {
                "name": "Task",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": True},
                    {"name": "due_date", "type": "datetime", "nullable": True, "required": False},
                ],
                "endpoints": ["list", "create", "get", "update", "delete"],
            }
        ],
    )


def test_generate_all_writes_project_subdirectory(tmp_path: Path) -> None:
    spec = handle_draft_spec(_request()).spec_yaml

    response = handle_generate_all(
        GenerateAllRequest(spec=spec, project_name="Task Manager", output_dir=str(tmp_path)),
    )

    assert response.status == "ok"
    assert (tmp_path / "task-manager").is_dir()
    assert ".env.example" in response.files_written
    assert "docker-compose.yml" in response.files_written
    assert "openapi.yaml" in response.files_written
    assert "tests/test_task.py" in response.files_written
    env_text = (tmp_path / "task-manager" / ".env.example").read_text()
    assert "sqlite+aiosqlite:///./task-manager.db" in env_text
    _assert_generated_project_imports(tmp_path / "task-manager")


def test_generate_all_supports_postgres_container_branch(tmp_path: Path) -> None:
    spec = handle_draft_spec(_request()).spec_yaml

    response = handle_generate_all(
        GenerateAllRequest(
            spec=spec,
            project_name="Task Manager",
            output_dir=str(tmp_path),
            options={"db_backend": "postgres", "include_tests": True, "include_containers": True},
        ),
    )

    assert response.status == "ok"
    env_text = (tmp_path / "task-manager" / ".env.example").read_text()
    assert "postgresql+asyncpg://postgres:postgres@db:5432/task_manager" in env_text
    _assert_generated_project_imports(tmp_path / "task-manager")


def test_generate_all_rejects_invalid_spec(tmp_path: Path) -> None:
    response = handle_generate_all(
        GenerateAllRequest(
            spec="openapi: 3.1.0\ninfo: {}\npaths: {}",
            project_name="Broken",
            output_dir=str(tmp_path),
        )
    )

    assert response.status == "invalid"
    assert response.files_written == []


def _assert_generated_project_imports(project_root: Path) -> None:
    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(project_root),
            "python",
            "-c",
            "import app.main; import app.routes.task",
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
