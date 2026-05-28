"""OpenAPI to internal representation conversion for Foundry generators."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from server.exceptions import GenerationError

_PATH_ID_PATTERN = re.compile(r"/(?P<collection>[^/]+)/\{(?P<parameter>[^}]+)\}$")


@dataclass(frozen=True)
class FieldIR:
    name: str
    python_type: str
    sqlalchemy_type: str
    required: bool
    nullable: bool
    sample_value: Any


@dataclass(frozen=True)
class ResourceIR:
    name: str
    module_name: str
    class_name: str
    plural_name: str
    path: str
    detail_path: str
    path_parameter: str
    fields: tuple[FieldIR, ...]
    endpoints: tuple[str, ...]


@dataclass(frozen=True)
class FoundryIR:
    project_name: str
    project_slug: str
    db_backend: str
    resources: tuple[ResourceIR, ...]


def build_ir(spec_text: str) -> FoundryIR:
    """Parse a validated spec into the IR used by all generators."""
    try:
        spec = yaml.safe_load(spec_text)
    except yaml.YAMLError as exc:
        raise GenerationError(f"Unable to parse OpenAPI spec: {exc}") from exc

    if not isinstance(spec, dict):
        raise GenerationError("OpenAPI spec root must be an object.")

    x_foundry = spec.get("x-foundry")
    if not isinstance(x_foundry, dict):
        raise GenerationError("OpenAPI spec is missing the x-foundry metadata block.")

    project_name = _string_value(x_foundry, "project_name")
    project_slug = slugify(project_name)
    db_backend = _string_value(x_foundry, "db_backend")

    components = spec.get("components")
    if not isinstance(components, dict):
        raise GenerationError("OpenAPI spec is missing components.")

    schemas = components.get("schemas")
    if not isinstance(schemas, dict) or not schemas:
        raise GenerationError("OpenAPI spec is missing components.schemas.")

    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise GenerationError("OpenAPI spec is missing paths.")

    endpoints_by_schema = _extract_endpoints_by_schema(paths)

    resources: list[ResourceIR] = []
    for schema_name, schema_body in schemas.items():
        if not _is_resource_schema(schema_name, schema_body):
            continue

        create_schema = schemas.get(f"{schema_name}Create")
        update_schema = schemas.get(f"{schema_name}Update")
        if not isinstance(create_schema, dict) or not isinstance(update_schema, dict):
            raise GenerationError(f"OpenAPI spec is missing create/update schemas for {schema_name}.")

        fields = _extract_fields(schema_name, schema_body, create_schema)
        endpoint_meta = endpoints_by_schema.get(schema_name)
        if endpoint_meta is None:
            raise GenerationError(f"OpenAPI paths do not describe routes for {schema_name}.")

        module_name = slugify(schema_name).replace("-", "_")
        resources.append(
            ResourceIR(
                name=schema_name,
                module_name=module_name,
                class_name=schema_name,
                plural_name=_pluralize(schema_name),
                path=endpoint_meta["collection_path"],
                detail_path=endpoint_meta["detail_path"],
                path_parameter=endpoint_meta["path_parameter"],
                fields=tuple(fields),
                endpoints=tuple(endpoint_meta["endpoints"]),
            )
        )

    if not resources:
        raise GenerationError("OpenAPI spec did not contain any generator-compatible resource schemas.")

    return FoundryIR(
        project_name=project_name,
        project_slug=project_slug,
        db_backend=db_backend,
        resources=tuple(resources),
    )


def slugify(value: str) -> str:
    """Return a filesystem-safe slug."""
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return normalized or "project"


def _extract_endpoints_by_schema(paths: dict[str, Any]) -> dict[str, dict[str, Any]]:
    resource_meta: dict[str, dict[str, Any]] = {}

    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        if _PATH_ID_PATTERN.search(path_name):
            continue

        for method_name, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            schema_name = _extract_primary_schema_name(operation)
            entry = resource_meta.setdefault(
                schema_name,
                {
                    "collection_path": path_name,
                    "detail_path": f"{path_name}/{{{_singularize(Path(path_name).name)}_id}}",
                    "path_parameter": f"{_singularize(Path(path_name).name)}_id",
                    "endpoints": [],
                },
            )
            entry["endpoints"].append(_endpoint_name(method_name))

    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        detail_match = _PATH_ID_PATTERN.search(path_name)
        if not detail_match:
            continue

        collection_path = f"/{detail_match.group('collection')}"
        schema_name = next(
            (
                name
                for name, entry in resource_meta.items()
                if entry["collection_path"] == collection_path
            ),
            None,
        )
        if schema_name is None:
            # Fall back to response inspection when the collection route is absent.
            schema_name = _first_detail_schema(path_item)

        entry = resource_meta.setdefault(
            schema_name,
            {
                "collection_path": collection_path,
                "detail_path": path_name,
                "path_parameter": detail_match.group("parameter"),
                "endpoints": [],
            },
        )
        entry["detail_path"] = path_name
        entry["path_parameter"] = detail_match.group("parameter")

        for method_name, operation in path_item.items():
            if method_name == "parameters" or not isinstance(operation, dict):
                continue
            entry["endpoints"].append(_endpoint_name(method_name))

    for entry in resource_meta.values():
        entry["endpoints"] = tuple(dict.fromkeys(entry["endpoints"]))

    return resource_meta


def _first_detail_schema(path_item: dict[str, Any]) -> str:
    for operation in path_item.values():
        if not isinstance(operation, dict):
            continue
        try:
            return _extract_primary_schema_name(operation)
        except GenerationError:
            continue
    raise GenerationError("Unable to determine resource schema from OpenAPI detail route.")


def _extract_primary_schema_name(operation: dict[str, Any]) -> str:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        raise GenerationError("OpenAPI operation is missing responses.")

    for status_code in ("200", "201"):
        response = responses.get(status_code)
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        app_json = content.get("application/json")
        if not isinstance(app_json, dict):
            continue
        schema = app_json.get("schema")
        if not isinstance(schema, dict):
            continue
        if "$ref" in schema:
            return _schema_name_from_ref(schema["$ref"])
        items = schema.get("items")
        if isinstance(items, dict) and "$ref" in items:
            return _schema_name_from_ref(items["$ref"])

    raise GenerationError("Unable to determine resource schema from OpenAPI operation.")


def _endpoint_name(method_name: str) -> str:
    mapping = {
        "get": "list",
        "post": "create",
        "put": "update",
        "patch": "update",
        "delete": "delete",
    }
    return mapping.get(method_name, method_name)


def _is_resource_schema(schema_name: str, schema_body: Any) -> bool:
    if not isinstance(schema_body, dict):
        return False
    if schema_name.endswith("Create") or schema_name.endswith("Update") or schema_name == "Error":
        return False
    properties = schema_body.get("properties")
    return isinstance(properties, dict) and "id" in properties


def _extract_fields(
    schema_name: str,
    schema_body: dict[str, Any],
    create_schema: dict[str, Any],
) -> list[FieldIR]:
    properties = schema_body.get("properties")
    if not isinstance(properties, dict):
        raise GenerationError(f"Schema {schema_name} must declare properties.")

    create_required = set(create_schema.get("required", []))
    fields: list[FieldIR] = []
    for field_name, field_schema in properties.items():
        if field_name == "id":
            continue
        if not isinstance(field_schema, dict):
            raise GenerationError(f"Field {schema_name}.{field_name} must be an object.")
        python_type, sqlalchemy_type, nullable, sample_value = _field_types(field_name, field_schema)
        fields.append(
            FieldIR(
                name=field_name,
                python_type=python_type,
                sqlalchemy_type=sqlalchemy_type,
                required=field_name in create_required,
                nullable=nullable,
                sample_value=sample_value,
            )
        )
    return fields


def _field_types(field_name: str, field_schema: dict[str, Any]) -> tuple[str, str, bool, Any]:
    schema_type = field_schema.get("type")
    nullable = False
    base_type: str
    if isinstance(schema_type, list):
        nullable = "null" in schema_type
        allowed = [item for item in schema_type if item != "null"]
        if len(allowed) != 1 or not isinstance(allowed[0], str):
            raise GenerationError(f"Unsupported multi-type field definition for {field_name}.")
        base_type = allowed[0]
    elif isinstance(schema_type, str):
        base_type = schema_type
    else:
        raise GenerationError(f"Field {field_name} is missing a valid type.")

    schema_format = field_schema.get("format")
    if base_type == "integer":
        return "int", "Integer", nullable, 1
    if base_type == "number":
        return "float", "Float", nullable, 1.5
    if base_type == "boolean":
        return "bool", "Boolean", nullable, True
    if base_type == "string" and schema_format == "date-time":
        return "datetime", "DateTime(timezone=True)", nullable, "2026-05-27T12:00:00Z"
    if base_type == "string" and schema_format == "date":
        return "date", "Date", nullable, "2026-05-27"
    if base_type == "string" and schema_format == "uuid":
        return "UUID", "String(36)", nullable, str(UUID(int=1))
    if base_type == "string":
        return "str", "String", nullable, f"example-{field_name}"
    raise GenerationError(f"Unsupported field type for {field_name}: {base_type}/{schema_format}.")


def _schema_name_from_ref(ref: Any) -> str:
    if not isinstance(ref, str) or not ref.startswith("#/components/schemas/"):
        raise GenerationError(f"Unsupported schema reference: {ref!r}")
    return ref.rsplit("/", 1)[-1]


def _pluralize(name: str) -> str:
    if name.endswith("s"):
        return f"{name}es"
    if name.endswith("y") and len(name) > 1 and name[-2].lower() not in "aeiou":
        return f"{name[:-1]}ies"
    return f"{name}s"


def _singularize(value: str) -> str:
    if value.endswith("ies"):
        return value[:-3] + "y"
    if value.endswith("ses"):
        return value[:-2]
    if value.endswith("s"):
        return value[:-1]
    return value


def _string_value(container: dict[str, Any], key: str) -> str:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GenerationError(f"x-foundry.{key} must be a non-empty string.")
    return value
