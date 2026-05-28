"""Database model generation."""

from __future__ import annotations

from pathlib import Path

from server.generators.common import relative_manifest_entry
from server.generators.backend import generate_backend
from server.parser import FoundryIR


def generate_db(ir: FoundryIR, output_root: Path, *, db_backend: str) -> tuple[list[str], list[str]]:
    """Ensure DB-related files exist and return generated model names."""
    files_written = generate_backend(ir, output_root)
    model_files = [
        path for path in files_written if path.startswith("app/db/models/") and path.endswith(".py")
    ]
    return sorted(set(model_files)), [resource.class_name for resource in ir.resources]
