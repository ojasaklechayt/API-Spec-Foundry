from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import handle_validate_spec
from server.tool_schemas import ValidateSpecRequest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def test_validate_spec_accepts_task_manager_fixture() -> None:
    spec = (FIXTURES / "task_manager_openapi.yaml").read_text()

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "ok"
    assert response.valid is True
    assert response.summary == "Spec is valid with 10 operations"
    assert response.operation_count == 10
    assert response.errors == []
    assert response.warnings == []


def test_validate_spec_reports_missing_operation_ids_and_unknown_refs() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Broken API
  version: 0.1.0
paths:
  /tasks:
    get:
      responses:
        "200":
          description: ok
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/MissingTask'
components:
  schemas:
    Error:
      type: object
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "invalid"
    assert response.valid is False
    assert response.operation_count == 1
    assert [issue.path for issue in response.errors] == [
        "paths./tasks.get.operationId",
        "paths./tasks.get.responses.200.content.application/json.schema.$ref",
    ]
    assert [issue.message for issue in response.errors] == [
        "operationId is required.",
        "Unknown component schema 'MissingTask'.",
    ]


def test_validate_spec_warns_for_generator_unsupported_compositions() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Composite API
  version: 0.1.0
paths:
  /composite:
    post:
      operationId: createComposite
      requestBody:
        required: true
        content:
          application/json:
            schema:
              oneOf:
              - $ref: '#/components/schemas/Task'
              - $ref: '#/components/schemas/User'
      responses:
        "201":
          description: created
components:
  schemas:
    Task:
      type: object
    User:
      type: object
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "ok"
    assert response.valid is True
    assert response.errors == []
    assert response.operation_count == 1
    assert [issue.path for issue in response.warnings] == [
        "paths./composite.post.requestBody.content.application/json.schema.oneOf",
    ]


def test_validate_spec_rejects_undeclared_path_parameters() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Broken API
  version: 0.1.0
paths:
  /tasks/{task_id}:
    get:
      operationId: getTask
      responses:
        "200":
          description: ok
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "invalid"
    assert response.valid is False
    assert response.operation_count == 1
    assert [issue.path for issue in response.errors] == [
        "paths./tasks/{task_id}.get.parameters",
    ]
    assert [issue.message for issue in response.errors] == [
        "Path parameter 'task_id' is used in '/tasks/{task_id}' but is not declared.",
    ]


def test_validate_spec_rejects_non_required_path_parameters() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Broken API
  version: 0.1.0
paths:
  /tasks/{task_id}:
    get:
      operationId: getTask
      parameters:
      - name: task_id
        in: path
        required: false
        schema:
          type: integer
      responses:
        "200":
          description: ok
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "invalid"
    assert response.valid is False
    assert response.operation_count == 1
    assert [issue.path for issue in response.errors] == [
        "paths./tasks/{task_id}.get.parameters[0].required",
    ]
    assert [issue.message for issue in response.errors] == [
        "Path parameters must set required=true.",
    ]
