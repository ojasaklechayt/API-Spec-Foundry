"""Container asset generation."""

from __future__ import annotations

from pathlib import Path

from server.generators.common import relative_manifest_entry, write_template
from server.parser import slugify


def generate_containers(
    project_name: str,
    output_root: Path,
    *,
    db_backend: str,
    include_db: bool,
) -> list[str]:
    """Generate Docker and environment assets."""
    files_written: list[str] = []
    project_slug = slugify(project_name)

    dockerfile_path = output_root / "Dockerfile"
    write_template(dockerfile_path, "containers/Dockerfile.j2")
    files_written.append(relative_manifest_entry(output_root, dockerfile_path))

    compose_path = output_root / "docker-compose.yml"
    write_template(
        compose_path,
        "containers/docker-compose.yml.j2",
        project_slug=project_slug,
        db_backend=db_backend,
        include_db=include_db and db_backend == "postgres",
    )
    files_written.append(relative_manifest_entry(output_root, compose_path))

    env_path = output_root / ".env.example"
    write_template(
        env_path,
        "containers/.env.example.j2",
        project_slug=project_slug,
        db_backend=db_backend,
    )
    files_written.append(relative_manifest_entry(output_root, env_path))

    return sorted(dict.fromkeys(files_written))
