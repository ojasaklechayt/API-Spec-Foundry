"""Validation helpers for OpenAPI drafts produced by Foundry."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

import yaml
from openapi_spec_validator import OpenAPIV31SpecValidator

from server.tool_schemas import ValidateSpecResponse, ValidationIssue

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
PATH_PARAMETER_RE = re.compile(r"{([^{}]+)}")


def validate_openapi_spec(raw_spec: str) -> ValidateSpecResponse:
    """Validate a raw YAML or JSON OpenAPI document."""
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []

    try:
        spec = yaml.safe_load(raw_spec)
    except yaml.YAMLError as exc:
        errors.append(ValidationIssue(path="$", message=f"Spec is not valid YAML: {exc}"))
        return _response(errors=errors, warnings=warnings, operation_count=0)

    if not isinstance(spec, dict):
        errors.append(ValidationIssue(path="$", message="Spec root must be an object."))
        return _response(errors=errors, warnings=warnings, operation_count=0)

    _require_string(spec, "openapi", errors)
    if spec.get("openapi") != "3.1.0":
        errors.append(
            ValidationIssue(
                path="openapi",
                message="OpenAPI version must be '3.1.0'.",
            )
        )

    info = spec.get("info")
    if not isinstance(info, dict):
        errors.append(ValidationIssue(path="info", message="info must be an object."))
    else:
        _require_string(info, "title", errors, parent="info")
        _require_string(info, "version", errors, parent="info")

    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        errors.append(ValidationIssue(path="paths", message="paths must be a non-empty object."))
        return _response(errors=errors, warnings=warnings, operation_count=0)

    components = spec.get("components")
    schemas = {}
    if not isinstance(components, dict):
        warnings.append(
            ValidationIssue(
                path="components",
                message="components is missing; shared schemas cannot be validated.",
            )
        )
    else:
        schemas = components.get("schemas", {})
        if not isinstance(schemas, dict) or not schemas:
            warnings.append(
                ValidationIssue(
                    path="components.schemas",
                    message="components.schemas is missing or empty.",
                )
            )

    operation_ids: set[str] = set()
    operation_count = 0

    for path_name, path_item in paths.items():
        if not isinstance(path_item, dict):
            errors.append(
                ValidationIssue(path=f"paths.{path_name}", message="Path item must be an object.")
            )
            continue

        template_parameters = set(PATH_PARAMETER_RE.findall(path_name))
        path_level_parameters = _collect_path_parameter_names(
            path_item.get("parameters"),
            errors,
            parent=f"paths.{path_name}.parameters",
        )
        has_operation = False
        for method_name, operation in path_item.items():
            if method_name == "parameters":
                continue

            if method_name not in HTTP_METHODS:
                continue

            has_operation = True
            operation_count += 1
            operation_path = f"paths.{path_name}.{method_name}"

            if not isinstance(operation, dict):
                errors.append(
                    ValidationIssue(path=operation_path, message="Operation must be an object.")
                )
                continue

            operation_parameters = _collect_path_parameter_names(
                operation.get("parameters"),
                errors,
                parent=f"{operation_path}.parameters",
            )
            _validate_path_parameter_resolution(
                path_name,
                template_parameters=template_parameters,
                declared_parameters=path_level_parameters | operation_parameters,
                errors=errors,
                parent=f"{operation_path}.parameters",
            )

            operation_id = operation.get("operationId")
            if not isinstance(operation_id, str) or not operation_id.strip():
                errors.append(
                    ValidationIssue(
                        path=f"{operation_path}.operationId",
                        message="operationId is required.",
                    )
                )
            elif operation_id in operation_ids:
                errors.append(
                    ValidationIssue(
                        path=f"{operation_path}.operationId",
                        message=f"Duplicate operationId '{operation_id}'.",
                    )
                )
            else:
                operation_ids.add(operation_id)

            responses = operation.get("responses")
            if not isinstance(responses, dict) or not responses:
                errors.append(
                    ValidationIssue(
                        path=f"{operation_path}.responses",
                        message="responses must be a non-empty object.",
                    )
                )

            if method_name in {"post", "put", "patch"} and "requestBody" not in operation:
                warnings.append(
                    ValidationIssue(
                        path=f"{operation_path}.requestBody",
                        message="Mutation operations should declare a requestBody.",
                    )
                )

            _collect_refs(operation, schemas, errors, path=operation_path)
            _collect_unsupported_keywords(operation, warnings, path=operation_path)

        if not has_operation:
            warnings.append(
                ValidationIssue(
                    path=f"paths.{path_name}",
                    message="Path item has no supported HTTP operations.",
                )
            )

    if not errors:
        _collect_standards_validation_errors(spec, errors)

    return _response(errors=errors, warnings=warnings, operation_count=operation_count)


def _response(
    *,
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
    operation_count: int,
) -> ValidateSpecResponse:
    valid = not errors
    if valid:
        summary = (
            f"Spec is valid with {operation_count} operations"
            if not warnings
            else f"Spec is valid with {operation_count} operations and {len(warnings)} warnings"
        )
    else:
        summary = (
            f"Spec is invalid with {len(errors)} errors"
            if not warnings
            else f"Spec is invalid with {len(errors)} errors and {len(warnings)} warnings"
        )

    return ValidateSpecResponse(
        status="ok" if valid else "invalid",
        valid=valid,
        errors=errors,
        warnings=warnings,
        summary=summary,
        operation_count=operation_count,
    )


def _require_string(
    container: dict[str, Any],
    key: str,
    errors: list[ValidationIssue],
    *,
    parent: str = "$",
) -> None:
    value = container.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(
            ValidationIssue(
                path=f"{parent}.{key}" if parent != "$" else key,
                message="Value must be a non-empty string.",
            )
        )


def _collect_path_parameter_names(
    node: Any,
    errors: list[ValidationIssue],
    *,
    parent: str,
) -> set[str]:
    if node is None:
        return set()

    if not isinstance(node, list):
        errors.append(ValidationIssue(path=parent, message="parameters must be an array."))
        return set()

    names: set[str] = set()
    for index, parameter in enumerate(node):
        parameter_path = f"{parent}[{index}]"
        if not isinstance(parameter, dict):
            errors.append(
                ValidationIssue(path=parameter_path, message="Parameter must be an object.")
            )
            continue

        if parameter.get("in") != "path":
            continue

        name = parameter.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(
                ValidationIssue(
                    path=f"{parameter_path}.name",
                    message="Path parameter name must be a non-empty string.",
                )
            )
            continue

        if parameter.get("required") is not True:
            errors.append(
                ValidationIssue(
                    path=f"{parameter_path}.required",
                    message="Path parameters must set required=true.",
                )
            )

        names.add(name)

    return names


def _validate_path_parameter_resolution(
    path_name: str,
    *,
    template_parameters: set[str],
    declared_parameters: set[str],
    errors: list[ValidationIssue],
    parent: str,
) -> None:
    for parameter_name in sorted(template_parameters - declared_parameters):
        errors.append(
            ValidationIssue(
                path=parent,
                message=(
                    f"Path parameter '{parameter_name}' is used in '{path_name}' "
                    "but is not declared."
                ),
            )
        )

    for parameter_name in sorted(declared_parameters - template_parameters):
        errors.append(
            ValidationIssue(
                path=parent,
                message=(
                    f"Path parameter '{parameter_name}' is declared in '{path_name}' "
                    "but not used in the path template."
                ),
            )
        )


def _collect_refs(
    node: Any,
    schemas: dict[str, Any],
    errors: list[ValidationIssue],
    *,
    path: str,
) -> None:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            schema_name = ref.rsplit("/", 1)[-1]
            if schema_name not in schemas:
                errors.append(
                    ValidationIssue(
                        path=f"{path}.$ref",
                        message=f"Unknown component schema '{schema_name}'.",
                    )
                )

        for key, value in node.items():
            child_path = f"{path}.{key}"
            _collect_refs(value, schemas, errors, path=child_path)
        return

    if isinstance(node, list):
        for index, value in enumerate(node):
            _collect_refs(value, schemas, errors, path=f"{path}[{index}]")


def _collect_unsupported_keywords(
    node: Any,
    warnings: list[ValidationIssue],
    *,
    path: str,
) -> None:
    if isinstance(node, dict):
        for keyword in ("oneOf", "anyOf", "allOf"):
            if keyword in node:
                warnings.append(
                    ValidationIssue(
                        path=f"{path}.{keyword}",
                        message=f"{keyword} is not supported by the Phase 2 generator contract.",
                    )
                )
        for key, value in node.items():
            _collect_unsupported_keywords(value, warnings, path=f"{path}.{key}")
        return

    if isinstance(node, list):
        for index, value in enumerate(node):
            _collect_unsupported_keywords(value, warnings, path=f"{path}[{index}]")


def _collect_standards_validation_errors(
    spec: dict[str, Any],
    errors: list[ValidationIssue],
) -> None:
    validator = OpenAPIV31SpecValidator(spec)

    try:
        validation_errors = list(validator.iter_errors())
    except Exception as exc:
        errors.append(
            ValidationIssue(path="$", message=f"OpenAPI validation failed: {exc}")
        )
        return

    existing_issues = {(issue.path, issue.message) for issue in errors}
    for error in validation_errors:
        issue = ValidationIssue(
            path=_format_validation_path(error.path),
            message=error.message,
        )
        if (issue.path, issue.message) not in existing_issues:
            errors.append(issue)
            existing_issues.add((issue.path, issue.message))


def _format_validation_path(path: Iterable[Any]) -> str:
    tokens: list[str] = []
    for segment in path:
        if isinstance(segment, int):
            if tokens:
                tokens[-1] = f"{tokens[-1]}[{segment}]"
            else:
                tokens.append(f"[{segment}]")
            continue

        tokens.append(str(segment))

    return ".".join(tokens) if tokens else "$"
