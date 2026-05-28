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
x-foundry:
  project_name: broken
  db_backend: sqlite
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
    error_paths = [issue.path for issue in response.errors]
    error_messages = [issue.message for issue in response.errors]
    assert "paths./tasks.get.operationId" in error_paths
    assert "paths./tasks.get.responses.200.content.application/json.schema.$ref" in error_paths
    assert "operationId is required." in error_messages
    assert "Unknown component schema 'MissingTask'." in error_messages


def test_validate_spec_warns_for_generator_unsupported_compositions() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Composite API
  version: 0.1.0
x-foundry:
  project_name: composite
  db_backend: sqlite
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
      properties:
        id:
          type: integer
        title:
          type: string
      required:
      - id
    TaskCreate:
      type: object
      properties:
        title:
          type: string
    TaskUpdate:
      type: object
      properties:
        title:
          type: string
    User:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
      required:
      - id
    UserCreate:
      type: object
      properties:
        name:
          type: string
    UserUpdate:
      type: object
      properties:
        name:
          type: string
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "ok"
    assert response.valid is True
    assert response.errors == []
    assert response.operation_count == 1
    warning_paths = [issue.path for issue in response.warnings]
    assert "paths./composite.post.requestBody.content.application/json.schema.oneOf" in warning_paths


def test_validate_spec_rejects_undeclared_path_parameters() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Broken API
  version: 0.1.0
x-foundry:
  project_name: broken
  db_backend: sqlite
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


def test_validate_spec_rejects_missing_foundry_extension() -> None:
    """A structurally valid OAS spec without x-foundry must be rejected."""
    spec = """
openapi: 3.1.0
info:
  title: No Foundry API
  version: 0.1.0
paths:
  /tasks:
    get:
      operationId: listTasks
      responses:
        '200':
          description: ok
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "invalid"
    assert response.valid is False
    error_paths = [issue.path for issue in response.errors]
    assert "x-foundry" in error_paths
    assert any("x-foundry" in issue.message for issue in response.errors)


def test_validate_spec_rejects_missing_create_update_schemas() -> None:
    """A spec with x-foundry and a resource schema missing Create/Update variants must be rejected."""
    spec = """
openapi: 3.1.0
info:
  title: Missing Variants API
  version: 0.1.0
x-foundry:
  project_name: test-project
  db_backend: sqlite
paths:
  /tasks:
    get:
      operationId: listTasks
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Task'
components:
  schemas:
    Task:
      type: object
      properties:
        id:
          type: integer
        title:
          type: string
      required:
      - id
      - title
      additionalProperties: false
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "invalid"
    assert response.valid is False
    error_paths = [issue.path for issue in response.errors]
    assert "components.schemas.TaskCreate" in error_paths
    assert "components.schemas.TaskUpdate" in error_paths


def test_validate_spec_rejects_invalid_db_backend_in_foundry_extension() -> None:
    """x-foundry.db_backend must be one of the supported values."""
    spec = """
openapi: 3.1.0
info:
  title: Bad DB API
  version: 0.1.0
x-foundry:
  project_name: test-project
  db_backend: mysql
paths:
  /tasks:
    get:
      operationId: listTasks
      responses:
        '200':
          description: ok
"""

    response = handle_validate_spec(ValidateSpecRequest(spec=spec))

    assert response.status == "invalid"
    assert response.valid is False
    error_paths = [issue.path for issue in response.errors]
    assert "x-foundry.db_backend" in error_paths


def test_validate_spec_rejects_non_required_path_parameters() -> None:
    spec = """
openapi: 3.1.0
info:
  title: Broken API
  version: 0.1.0
x-foundry:
  project_name: broken
  db_backend: sqlite
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
