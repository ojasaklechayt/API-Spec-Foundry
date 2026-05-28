"""Backend project file generation."""

from __future__ import annotations

from pathlib import Path

from server.generators.common import relative_manifest_entry, write_template, write_text
from server.parser import FieldIR, FoundryIR, ResourceIR


def generate_backend(ir: FoundryIR, output_root: Path) -> list[str]:
    """Generate the backend application scaffold."""
    files_written: list[str] = []

    for relative_dir in (
        "app",
        "app/core",
        "app/db",
        "app/db/models",
        "app/routes",
        "tests",
    ):
        init_target = output_root / relative_dir / "__init__.py"
        if not init_target.exists():
            write_text(init_target, "")
            files_written.append(relative_manifest_entry(output_root, init_target))

    health_path = output_root / "app" / "routes" / "health.py"
    write_text(
        health_path,
        "from fastapi import APIRouter\n\nrouter = APIRouter(tags=['Health'])\n\n\n@router.get('/healthz')\ndef healthcheck() -> dict[str, str]:\n    return {'status': 'ok'}\n",
    )
    files_written.append(relative_manifest_entry(output_root, health_path))

    main_path = output_root / "app" / "main.py"
    write_template(
        main_path,
        "backend/app/main.py.j2",
        ir=ir,
    )
    files_written.append(relative_manifest_entry(output_root, main_path))

    config_path = output_root / "app" / "core" / "config.py"
    write_template(
        config_path,
        "backend/app/core/config.py.j2",
        ir=ir,
    )
    files_written.append(relative_manifest_entry(output_root, config_path))

    base_path = output_root / "app" / "db" / "base.py"
    write_template(base_path, "backend/app/db/base.py.j2", ir=ir)
    files_written.append(relative_manifest_entry(output_root, base_path))

    session_path = output_root / "app" / "db" / "session.py"
    write_template(session_path, "backend/app/db/session.py.j2", ir=ir)
    files_written.append(relative_manifest_entry(output_root, session_path))

    models_init_path = output_root / "app" / "db" / "models" / "__init__.py"
    write_template(models_init_path, "backend/app/db/models/__init__.py.j2", ir=ir)
    files_written.append(relative_manifest_entry(output_root, models_init_path))

    for resource in ir.resources:
        route_path = output_root / "app" / "routes" / f"{resource.module_name}.py"
        write_template(
            route_path,
            "backend/app/routes/resource.py.j2",
            resource=_route_context(resource),
        )
        files_written.append(relative_manifest_entry(output_root, route_path))

        model_path = output_root / "app" / "db" / "models" / f"{resource.module_name}.py"
        write_template(
            model_path,
            "backend/app/db/models/resource.py.j2",
            resource=_model_context(resource),
        )
        files_written.append(relative_manifest_entry(output_root, model_path))

    pyproject_path = output_root / "pyproject.toml"
    write_text(pyproject_path, _render_pyproject(ir))
    files_written.append(relative_manifest_entry(output_root, pyproject_path))

    return sorted(dict.fromkeys(files_written))


def _route_context(resource: ResourceIR) -> dict[str, object]:
    imports = sorted(
        {
            import_name
            for field in resource.fields
            for import_name in _python_imports_for_field(field)
        }
    )
    return {
        "class_name": resource.class_name,
        "module_name": resource.module_name,
        "collection_path": resource.path,
        "detail_path": resource.detail_path,
        "path_parameter": resource.path_parameter,
        "import_block": _render_route_import_block(imports),
        "response_field_block": _render_field_block(
            [_response_field_line(field) for field in resource.fields]
        ),
        "create_field_block": _render_field_block(
            [_create_field_line(field) for field in resource.fields]
        ),
        "update_field_block": _render_field_block(
            [_update_field_line(field) for field in resource.fields]
        ),
        "field_names": [field.name for field in resource.fields],
    }


def _model_context(resource: ResourceIR) -> dict[str, object]:
    imports = sorted(
        {
            import_name
            for field in resource.fields
            for import_name in _model_imports_for_field(field)
        }
    )
    return {
        "class_name": resource.class_name,
        "table_name": resource.path.strip("/"),
        "imports": imports,
        "columns": [_column_line(field) for field in resource.fields],
    }


def _python_imports_for_field(field: FieldIR) -> list[str]:
    mapping = {
        "datetime": ["datetime"],
        "date": ["date"],
        "UUID": ["UUID"],
    }
    return mapping.get(field.python_type, [])


def _model_imports_for_field(field: FieldIR) -> list[str]:
    mapping = {
        "DateTime(timezone=True)": ["datetime"],
        "Date": ["date"],
    }
    return mapping.get(field.sqlalchemy_type, [])


def _annotation(field: FieldIR, *, update: bool = False) -> str:
    base = field.python_type
    if update or field.nullable:
        return f"{base} | None"
    return base


def _response_field_line(field: FieldIR) -> str:
    if field.nullable:
        return f"    {field.name}: {_annotation(field)} = None"
    return f"    {field.name}: {_annotation(field)}"


def _create_field_line(field: FieldIR) -> str:
    if field.required and not field.nullable:
        return f"    {field.name}: {field.python_type}"
    return f"    {field.name}: {_annotation(field)} = None"


def _update_field_line(field: FieldIR) -> str:
    return f"    {field.name}: {_annotation(field, update=True)} = None"


def _column_line(field: FieldIR) -> str:
    nullable = "True" if field.nullable or not field.required else "False"
    return (
        f"    {field.name}: Mapped[{field.python_type}] = mapped_column("
        f"{field.sqlalchemy_type}, nullable={nullable})"
    )


def _render_pyproject(ir: FoundryIR) -> str:
    return f"""[project]
name = "{ir.project_slug}"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "pydantic-settings>=2.2",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "asyncpg>=0.29",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hatch.build.targets.wheel]
packages = ["app"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
"""


def _render_route_import_block(imports: list[str]) -> str:
    lines: list[str] = []
    datetime_imports = [name for name in imports if name in {"date", "datetime"}]
    if datetime_imports:
        lines.append(f"from datetime import {', '.join(datetime_imports)}")
    if "UUID" in imports:
        lines.append("from uuid import UUID")
    return "\n".join(lines)


def _render_field_block(lines: list[str]) -> str:
    return "\n".join(lines)
