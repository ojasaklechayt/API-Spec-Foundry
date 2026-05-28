from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import handle_draft_spec, handle_generate_backend
from server.tool_schemas import DraftSpecRequest, GenerateBackendRequest


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
                    {"name": "due_date", "type": "datetime", "required": False, "nullable": True},
                    {"name": "user_id", "type": "integer", "required": True},
                ],
                "endpoints": ["list", "create", "get", "update", "delete"],
            },
        ],
    )


def test_generate_backend_emits_importable_python_modules(tmp_path: Path) -> None:
    spec = handle_draft_spec(_task_manager_request()).spec_yaml

    response = handle_generate_backend(
        GenerateBackendRequest(spec=spec, output_dir=str(tmp_path)),
    )

    assert response.status == "ok"
    assert "app/routes/task.py" in response.files_written

    result = subprocess.run(
        [
            "uv",
            "run",
            "--project",
            str(tmp_path),
            "python",
            "-c",
            "import app.main; import app.routes.task; import app.routes.user",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
