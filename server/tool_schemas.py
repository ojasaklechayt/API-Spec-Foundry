"""Typed request and response models for the Foundry MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AuthMode = Literal["none", "bearer", "api_key"]
DatabaseBackend = Literal["sqlite", "postgres"]
ToolStatus = Literal["ok", "invalid", "stub"]
EndpointName = Literal["list", "create", "get", "update", "delete"]


class StrictModel(BaseModel):
    """Base model that rejects undeclared tool fields."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResourceFieldInput(StrictModel):
    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    required: bool = True
    nullable: bool = False
    description: str | None = None


class ResourceInput(StrictModel):
    name: str = Field(min_length=1)
    fields: list[ResourceFieldInput] = Field(default_factory=list)
    endpoints: list[EndpointName] = Field(default_factory=list)


class DraftSpecRequest(StrictModel):
    project_name: str = Field(min_length=1)
    resources: list[ResourceInput] = Field(default_factory=list, min_length=1)
    auth: AuthMode = "none"
    db_backend: DatabaseBackend = "sqlite"


class ValidationIssue(StrictModel):
    path: str
    message: str


class DraftSpecResponse(StrictModel):
    status: ToolStatus = "ok"
    spec_yaml: str = ""
    summary: str
    resource_count: int = 0
    endpoint_count: int = 0
    warnings: list[ValidationIssue] = Field(default_factory=list)


class ValidateSpecRequest(StrictModel):
    spec: str = Field(min_length=1)


class ValidateSpecResponse(StrictModel):
    status: ToolStatus
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    summary: str
    operation_count: int = 0


class GenerateBackendRequest(StrictModel):
    spec: str
    output_dir: str = "."


class GenerateDbRequest(StrictModel):
    spec: str
    output_dir: str = "."
    db_backend: DatabaseBackend = "sqlite"


class GenerateTestsRequest(StrictModel):
    spec: str
    output_dir: str = "."


class GenerateContainersRequest(StrictModel):
    project_name: str
    output_dir: str = "."
    db_backend: DatabaseBackend = "sqlite"
    include_db: bool = True


class GenerateAllOptions(StrictModel):
    db_backend: DatabaseBackend = "sqlite"
    include_tests: bool = True
    include_containers: bool = True


class GenerateAllRequest(StrictModel):
    spec: str
    project_name: str
    output_dir: str = "."
    options: GenerateAllOptions = Field(default_factory=GenerateAllOptions)


class GenerationResponse(StrictModel):
    status: ToolStatus = "stub"
    files_written: list[str] = Field(default_factory=list)
    summary: str
    models: list[str] = Field(default_factory=list)
    test_count: int = 0
