from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import handle_draft_spec, handle_generate_db
from server.tool_schemas import DraftSpecRequest, GenerateDbRequest


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
                    {"name": "due_date", "type": "datetime", "nullable": True, "required": False},
                ],
                "endpoints": ["list", "create", "get", "update", "delete"],
            }
        ],
    )


def test_generate_db_returns_model_manifest_and_names(tmp_path: Path) -> None:
    spec = handle_draft_spec(_request()).spec_yaml

    response = handle_generate_db(
        GenerateDbRequest(spec=spec, output_dir=str(tmp_path), db_backend="sqlite"),
    )

    assert response.status == "ok"
    assert response.models == ["Task"]
    assert "app/db/models/task.py" in response.files_written


def test_generate_db_supports_postgres_manifest(tmp_path: Path) -> None:
    spec = handle_draft_spec(_request()).spec_yaml

    response = handle_generate_db(
        GenerateDbRequest(spec=spec, output_dir=str(tmp_path), db_backend="postgres"),
    )

    assert response.status == "ok"
    assert response.models == ["Task"]
