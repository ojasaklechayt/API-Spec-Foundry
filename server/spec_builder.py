"""Deterministic OpenAPI draft builder for Foundry."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import yaml

from server.exceptions import DraftSpecError
from server.tool_schemas import DraftSpecRequest, ResourceFieldInput, ResourceInput

DEFAULT_ENDPOINTS = ("list", "create", "get", "update", "delete")
FIELD_TYPE_MAP: dict[str, tuple[str, str | None]] = {
    "string": ("string", None),
    "text": ("string", None),
    "integer": ("integer", None),
    "int": ("integer", None),
    "number": ("number", None),
    "float": ("number", "float"),
    "boolean": ("boolean", None),
    "bool": ("boolean", None),
    "date": ("string", "date"),
    "datetime": ("string", "date-time"),
    "timestamp": ("string", "date-time"),
    "uuid": ("string", "uuid"),
    "email": ("string", "email"),
}


class _NoAliasSafeDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def build_openapi_spec(request: DraftSpecRequest) -> tuple[str, int]:
    """Build a deterministic OpenAPI 3.1 document and return YAML plus op count."""
    if not request.resources:
        raise DraftSpecError("At least one resource is required to draft a spec.")

    seen_resources: set[str] = set()
    paths: dict[str, Any] = {}
    schemas: dict[str, Any] = {}
    tags: list[dict[str, str]] = []
    operation_count = 0

    for resource in request.resources:
        normalized_key = _singularize(_resource_key(resource.name))
        if normalized_key in seen_resources:
            raise DraftSpecError(f"Duplicate resource name '{resource.name}'.")
        seen_resources.add(normalized_key)

        resource_meta = _resource_metadata(resource.name)
        tags.append({"name": resource_meta["tag"], "description": f"{resource_meta['display_plural']} operations"})

        schemas.update(_build_resource_schemas(resource_meta["schema_name"], resource.fields))

        resource_paths, resource_operation_count = _build_resource_paths(
            resource,
            schema_name=resource_meta["schema_name"],
            tag_name=resource_meta["tag"],
            collection_path=resource_meta["collection_path"],
            detail_path=resource_meta["detail_path"],
            path_parameter=resource_meta["path_parameter"],
        )
        paths.update(resource_paths)
        operation_count += resource_operation_count

    spec: dict[str, Any] = {
        "openapi": "3.1.0",
        "info": {
            "title": f"{request.project_name} API",
            "version": "0.1.0",
        },
        "servers": [{"url": "http://localhost:8000"}],
        "tags": tags,
        "paths": paths,
        "components": {"schemas": schemas},
        "x-foundry": {
            "project_name": request.project_name,
            "db_backend": request.db_backend,
            "resource_count": len(request.resources),
        },
    }

    security_schemes, security = _build_security(request.auth)
    if security_schemes is not None:
        spec["components"]["securitySchemes"] = security_schemes
        spec["security"] = security

    spec_yaml = yaml.dump(
        spec,
        Dumper=_NoAliasSafeDumper,
        sort_keys=False,
        allow_unicode=False,
    )
    return spec_yaml, operation_count


def _build_security(
    auth_mode: str,
) -> tuple[dict[str, Any] | None, list[dict[str, list[str]]] | None]:
    if auth_mode == "none":
        return None, None
    if auth_mode == "bearer":
        return (
            {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                }
            },
            [{"bearerAuth": []}],
        )
    if auth_mode == "api_key":
        return (
            {
                "apiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                }
            },
            [{"apiKeyAuth": []}],
        )
    raise DraftSpecError(f"Unsupported auth mode '{auth_mode}'.")


def _build_resource_schemas(schema_name: str, fields: Iterable[ResourceFieldInput]) -> dict[str, Any]:
    field_properties: dict[str, Any] = {}
    create_required: list[str] = []

    for field in fields:
        if field.name == "id":
            raise DraftSpecError("Resource fields must not declare 'id'; it is generated automatically.")

        if field.name in field_properties:
            raise DraftSpecError(f"Duplicate field name '{field.name}' in resource '{schema_name}'.")

        field_properties[field.name] = _field_schema(field.type, field.nullable, field.description)
        if field.required:
            create_required.append(field.name)

    resource_properties = {
        "id": {"type": "integer", "readOnly": True},
        **field_properties,
    }

    resource_required = ["id", *create_required]
    create_schema: dict[str, Any] = {
        "type": "object",
        "properties": field_properties,
        "additionalProperties": False,
    }
    if create_required:
        create_schema["required"] = create_required

    return {
        schema_name: {
            "type": "object",
            "properties": resource_properties,
            "required": resource_required,
            "additionalProperties": False,
        },
        f"{schema_name}Create": create_schema,
        f"{schema_name}Update": {
            "type": "object",
            "properties": field_properties,
            "additionalProperties": False,
        },
        "Error": {
            "type": "object",
            "properties": {
                "detail": {"type": "string"},
            },
            "required": ["detail"],
            "additionalProperties": False,
        },
    }


def _build_resource_paths(
    resource: ResourceInput,
    *,
    schema_name: str,
    tag_name: str,
    collection_path: str,
    detail_path: str,
    path_parameter: str,
) -> tuple[dict[str, Any], int]:
    endpoints = list(resource.endpoints or DEFAULT_ENDPOINTS)
    if len(set(endpoints)) != len(endpoints):
        raise DraftSpecError(f"Duplicate endpoints configured for resource '{resource.name}'.")

    allowed_endpoints = set(DEFAULT_ENDPOINTS)
    unknown_endpoints = sorted(set(endpoints) - allowed_endpoints)
    if unknown_endpoints:
        rendered = ", ".join(unknown_endpoints)
        raise DraftSpecError(f"Unsupported endpoints for resource '{resource.name}': {rendered}.")

    collection_operations: dict[str, Any] = {}
    detail_operations: dict[str, Any] = {}
    operation_count = 0

    if "list" in endpoints:
        collection_operations["get"] = {
            "tags": [tag_name],
            "summary": f"List {tag_name.lower()}",
            "operationId": f"list{tag_name}",
            "responses": {
                "200": {
                    "description": f"List {tag_name.lower()} response",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "array",
                                "items": {"$ref": f"#/components/schemas/{schema_name}"},
                            }
                        }
                    },
                }
            },
        }
        operation_count += 1

    if "create" in endpoints:
        collection_operations["post"] = {
            "tags": [tag_name],
            "summary": f"Create {schema_name.lower()}",
            "operationId": f"create{schema_name}",
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema_name}Create"}
                    }
                },
            },
            "responses": {
                "201": {
                    "description": f"{schema_name} created",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                        }
                    },
                },
                "422": _error_response("Validation error"),
            },
        }
        operation_count += 1

    if "get" in endpoints:
        detail_operations["get"] = {
            "tags": [tag_name],
            "summary": f"Get {schema_name.lower()}",
            "operationId": f"get{schema_name}",
            "parameters": [_path_parameter(path_parameter)],
            "responses": {
                "200": {
                    "description": f"{schema_name} response",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                        }
                    },
                },
                "404": _error_response(f"{schema_name} not found"),
            },
        }
        operation_count += 1

    if "update" in endpoints:
        detail_operations["put"] = {
            "tags": [tag_name],
            "summary": f"Update {schema_name.lower()}",
            "operationId": f"update{schema_name}",
            "parameters": [_path_parameter(path_parameter)],
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": f"#/components/schemas/{schema_name}Update"}
                    }
                },
            },
            "responses": {
                "200": {
                    "description": f"{schema_name} updated",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": f"#/components/schemas/{schema_name}"}
                        }
                    },
                },
                "404": _error_response(f"{schema_name} not found"),
                "422": _error_response("Validation error"),
            },
        }
        operation_count += 1

    if "delete" in endpoints:
        detail_operations["delete"] = {
            "tags": [tag_name],
            "summary": f"Delete {schema_name.lower()}",
            "operationId": f"delete{schema_name}",
            "parameters": [_path_parameter(path_parameter)],
            "responses": {
                "204": {"description": f"{schema_name} deleted"},
                "404": _error_response(f"{schema_name} not found"),
            },
        }
        operation_count += 1

    paths: dict[str, Any] = {}
    if collection_operations:
        paths[collection_path] = collection_operations
    if detail_operations:
        paths[detail_path] = detail_operations
    return paths, operation_count


def _field_schema(field_type: str, nullable: bool, description: str | None) -> dict[str, Any]:
    normalized_type = field_type.strip().lower()
    if normalized_type not in FIELD_TYPE_MAP:
        supported_types = ", ".join(sorted(FIELD_TYPE_MAP))
        raise DraftSpecError(
            f"Unsupported field type '{field_type}'. Supported types: {supported_types}."
        )

    openapi_type, openapi_format = FIELD_TYPE_MAP[normalized_type]
    schema: dict[str, Any] = {
        "type": [openapi_type, "null"] if nullable else openapi_type,
    }
    if openapi_format is not None:
        schema["format"] = openapi_format
    if description:
        schema["description"] = description
    return schema


def _path_parameter(parameter_name: str) -> dict[str, Any]:
    return {
        "name": parameter_name,
        "in": "path",
        "required": True,
        "schema": {"type": "integer"},
    }


def _error_response(description: str) -> dict[str, Any]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Error"}
            }
        },
    }


def _resource_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _resource_metadata(name: str) -> dict[str, str]:
    slug = _resource_key(name)
    singular_slug = _singularize(slug)
    plural_slug = _pluralize(singular_slug)
    schema_name = "".join(part.capitalize() for part in singular_slug.split("-"))
    display_plural = plural_slug.replace("-", " ")
    tag_name = "".join(part.capitalize() for part in plural_slug.split("-"))

    return {
        "schema_name": schema_name,
        "collection_path": f"/{plural_slug}",
        "detail_path": f"/{plural_slug}/{{{singular_slug.replace('-', '_')}_id}}",
        "path_parameter": f"{singular_slug.replace('-', '_')}_id",
        "tag": tag_name,
        "display_plural": display_plural,
    }


def _singularize(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return f"{value[:-3]}y"
    if value.endswith("ses") and len(value) > 3:
        return value[:-2]
    if value.endswith("s") and not value.endswith("ss") and len(value) > 1:
        return value[:-1]
    return value


def _pluralize(value: str) -> str:
    if value.endswith("y") and len(value) > 1 and value[-2] not in "aeiou":
        return f"{value[:-1]}ies"
    if value.endswith(("s", "x", "z", "ch", "sh")):
        return f"{value}es"
    return f"{value}s"
