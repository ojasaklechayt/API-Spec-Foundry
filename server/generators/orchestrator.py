"""High-level project generation orchestration."""

from __future__ import annotations

from pathlib import Path

from server.generators.backend import generate_backend
from server.generators.common import relative_manifest_entry, resolve_project_root, write_text
from server.generators.containers import generate_containers
from server.generators.db import generate_db
from server.generators.tests import generate_tests
from server.parser import FoundryIR


def generate_all(
    ir: FoundryIR,
    *,
    spec_text: str,
    output_dir: str,
    include_tests: bool,
    include_containers: bool,
    db_backend: str,
) -> tuple[Path, list[str], list[str], int]:
    """Generate the full project tree into a dedicated project subdirectory."""
    project_root = resolve_project_root(output_dir, ir.project_slug)
    files_written: list[str] = []

    openapi_path = project_root / "openapi.yaml"
    write_text(openapi_path, spec_text)
    files_written.append(relative_manifest_entry(project_root, openapi_path))

    files_written.extend(generate_backend(ir, project_root))
    db_files, models = generate_db(ir, project_root, db_backend=db_backend)
    files_written.extend(db_files)

    test_count = 0
    if include_tests:
        test_files, test_count = generate_tests(ir, project_root)
        files_written.extend(test_files)

    if include_containers:
        files_written.extend(
            generate_containers(
                ir.project_name,
                project_root,
                db_backend=db_backend,
                include_db=db_backend == "postgres",
            )
        )

    return project_root, sorted(dict.fromkeys(files_written)), models, test_count
