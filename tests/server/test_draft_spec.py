from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import handle_draft_spec
from server.tool_schemas import DraftSpecRequest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


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


def test_draft_spec_matches_task_manager_fixture() -> None:
    response = handle_draft_spec(_task_manager_request())
    expected = (FIXTURES / "task_manager_openapi.yaml").read_text()

    assert response.status == "ok"
    assert response.summary == "2 resources, 10 endpoints"
    assert response.resource_count == 2
    assert response.endpoint_count == 10
    assert response.warnings == []
    assert response.spec_yaml.strip() == expected.strip()


def test_draft_spec_returns_structured_invalid_response_for_duplicate_resource_names() -> None:
    request = DraftSpecRequest(
        project_name="Duplicate Resources",
        resources=[
            {"name": "Task", "fields": [], "endpoints": ["list"]},
            {"name": "Tasks", "fields": [], "endpoints": ["list"]},
        ],
    )

    response = handle_draft_spec(request)

    assert response.status == "invalid"
    assert response.spec_yaml == ""
    assert response.endpoint_count == 0
    assert response.summary == "Duplicate resource name 'Tasks'."
