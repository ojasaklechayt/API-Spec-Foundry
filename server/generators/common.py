"""Shared helpers for generator modules."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from server.exceptions import GenerationError, UnsafeOutputPathError

TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "templates"


def build_template_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_ROOT)),
        autoescape=False,
        trim_blocks=False,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_output_root(output_dir: str) -> Path:
    root = Path(output_dir).expanduser().resolve()
    ensure_directory(root)
    return root


def resolve_project_root(output_dir: str, project_slug: str) -> Path:
    if not project_slug or project_slug in {".", ".."}:
        raise UnsafeOutputPathError("Project slug must be a non-empty safe path segment.")
    if "/" in project_slug or "\\" in project_slug:
        raise UnsafeOutputPathError("Project slug must not contain path separators.")

    output_root = resolve_output_root(output_dir)
    project_root = (output_root / project_slug).resolve()
    if output_root != project_root and output_root not in project_root.parents:
        raise UnsafeOutputPathError("Resolved project path escapes the requested output root.")

    ensure_directory(project_root)
    return project_root


def render_template(template_name: str, **context: Any) -> str:
    env = build_template_env()
    try:
        return env.get_template(template_name).render(**context)
    except Exception as exc:  # pragma: no cover - exact template exception is assertion detail
        raise GenerationError(f"Unable to render template {template_name}: {exc}") from exc


def write_text(path: Path, content: str) -> None:
    ensure_directory(path.parent)
    path.write_text(content, encoding="utf-8")


def write_template(path: Path, template_name: str, **context: Any) -> None:
    write_text(path, render_template(template_name, **context))


def relative_manifest_entry(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()
