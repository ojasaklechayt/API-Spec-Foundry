from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from server.main import handle_generate_containers
from server.tool_schemas import GenerateContainersRequest


def test_generate_containers_writes_sqlite_assets(tmp_path: Path) -> None:
    response = handle_generate_containers(
        GenerateContainersRequest(
            project_name="Task Manager",
            output_dir=str(tmp_path),
            db_backend="sqlite",
            include_db=False,
        )
    )

    assert response.status == "ok"
    assert sorted(response.files_written) == [".env.example", "Dockerfile", "docker-compose.yml"]
    env_text = (tmp_path / ".env.example").read_text()
    assert "DEBUG=false" in env_text
    assert "DATABASE_URL=sqlite+aiosqlite:///./task-manager.db" in env_text
    assert "sqlite+aiosqlite" in env_text


def test_generate_containers_writes_postgres_assets(tmp_path: Path) -> None:
    response = handle_generate_containers(
        GenerateContainersRequest(
            project_name="Task Manager",
            output_dir=str(tmp_path),
            db_backend="postgres",
            include_db=True,
        )
    )

    assert response.status == "ok"
    compose = (tmp_path / "docker-compose.yml").read_text()
    env_text = (tmp_path / ".env.example").read_text()
    assert "postgres:16" in compose
    assert "DEBUG=false" in env_text
    assert "DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/task_manager" in env_text
    assert "postgresql+asyncpg" in env_text
