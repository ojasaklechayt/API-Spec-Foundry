"""FastMCP composition root for the API Spec Foundry plugin."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel

from server.exceptions import DraftSpecError
from server.spec_builder import build_openapi_spec
from server.tool_schemas import (
    DraftSpecRequest,
    DraftSpecResponse,
    GenerateAllRequest,
    GenerateBackendRequest,
    GenerateContainersRequest,
    GenerateDbRequest,
    GenerateTestsRequest,
    GenerationResponse,
    ValidateSpecRequest,
    ValidateSpecResponse,
)
from server.validator import validate_openapi_spec

SERVER_NAME = "api-spec-foundry"
SERVER_VERSION = "0.1.0"

TOOL_NAMES = (
    "draft_spec",
    "validate_spec",
    "generate_backend",
    "generate_db",
    "generate_tests",
    "generate_containers",
    "generate_all",
)


def handle_draft_spec(request: DraftSpecRequest) -> DraftSpecResponse:
    """Draft a deterministic OpenAPI document from structured resource input."""
    try:
        spec_yaml, endpoint_count = build_openapi_spec(request)
    except DraftSpecError as exc:
        return DraftSpecResponse(
            status="invalid",
            spec_yaml="",
            summary=str(exc),
            resource_count=len(request.resources),
            endpoint_count=0,
            warnings=[],
        )

    resource_count = len(request.resources)
    return DraftSpecResponse(
        status="ok",
        spec_yaml=spec_yaml,
        summary=f"{resource_count} resources, {endpoint_count} endpoints",
        resource_count=resource_count,
        endpoint_count=endpoint_count,
        warnings=[],
    )


def handle_validate_spec(request: ValidateSpecRequest) -> ValidateSpecResponse:
    """Validate an OpenAPI draft and return structured errors or warnings."""
    return validate_openapi_spec(request.spec)


def _generation_response(tool_name: str) -> GenerationResponse:
    return GenerationResponse(
        summary=f"Scaffold only. {tool_name} is registered but not implemented yet."
    )


TOOL_SURFACE: tuple[dict[str, Any], ...] = (
    {
        "name": "draft_spec",
        "request_model": DraftSpecRequest,
        "response_model": DraftSpecResponse,
        "handler": handle_draft_spec,
    },
    {
        "name": "validate_spec",
        "request_model": ValidateSpecRequest,
        "response_model": ValidateSpecResponse,
        "handler": handle_validate_spec,
    },
    {
        "name": "generate_backend",
        "request_model": GenerateBackendRequest,
        "response_model": GenerationResponse,
        "handler": lambda _: _generation_response("generate_backend"),
    },
    {
        "name": "generate_db",
        "request_model": GenerateDbRequest,
        "response_model": GenerationResponse,
        "handler": lambda _: _generation_response("generate_db"),
    },
    {
        "name": "generate_tests",
        "request_model": GenerateTestsRequest,
        "response_model": GenerationResponse,
        "handler": lambda _: _generation_response("generate_tests"),
    },
    {
        "name": "generate_containers",
        "request_model": GenerateContainersRequest,
        "response_model": GenerationResponse,
        "handler": lambda _: _generation_response("generate_containers"),
    },
    {
        "name": "generate_all",
        "request_model": GenerateAllRequest,
        "response_model": GenerationResponse,
        "handler": lambda _: _generation_response("generate_all"),
    },
)


def describe_tool_surface() -> list[dict[str, str]]:
    """Return a lightweight description of the registered tool contract."""
    return [
        {
            "name": entry["name"],
            "request_model": entry["request_model"].__name__,
            "response_model": entry["response_model"].__name__,
        }
        for entry in TOOL_SURFACE
    ]


def _register_tool(
    mcp: FastMCP,
    *,
    name: str,
    request_model: type[BaseModel],
    handler: Callable[[BaseModel], BaseModel],
) -> None:
    def tool(request: BaseModel) -> dict[str, Any]:
        response = handler(request)
        return response.model_dump()

    tool.__name__ = name
    tool.__annotations__ = {
        "request": request_model,
        "return": dict[str, Any],
    }
    mcp.tool(tool, name=name)


def build_server() -> FastMCP:
    """Create the FastMCP server and register the planned tool surface."""
    mcp = FastMCP(name=SERVER_NAME)

    for entry in TOOL_SURFACE:
        _register_tool(
            mcp,
            name=entry["name"],
            request_model=entry["request_model"],
            handler=entry["handler"],
        )

    # Tests use this explicit attribute instead of depending on FastMCP internals.
    mcp._foundry_registered_tools = TOOL_NAMES  # type: ignore[attr-defined]
    return mcp


def main() -> None:
    """Boot the stdio MCP server."""
    server = build_server()

    # Phase 1 tests need a non-blocking way to validate the exact runtime entrypoint.
    if os.getenv("FOUNDRY_EXIT_AFTER_STARTUP") == "1":
        print(
            json.dumps(
                {
                    "status": "booted",
                    "server": SERVER_NAME,
                    "version": SERVER_VERSION,
                    "tool_count": len(TOOL_NAMES),
                }
            )
        )
        return

    server.run()


if __name__ == "__main__":
    main()
