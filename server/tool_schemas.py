"""Typed request and response models for the Foundry MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AuthMode = Literal["none", "bearer", "api_key"]
DatabaseBackend = Literal["sqlite", "postgres"]
ToolStatus = Literal["stub"]


class ResourceFieldInput(BaseModel):
    name: str
    type: str
    required: bool = True
    nullable: bool = False
    description: str | None = None


class ResourceInput(BaseModel):
    name: str
    fields: list[ResourceFieldInput] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)


class DraftSpecRequest(BaseModel):
    project_name: str
    resources: list[ResourceInput] = Field(default_factory=list)
    auth: AuthMode = "none"
    db_backend: DatabaseBackend = "sqlite"


class ValidationIssue(BaseModel):
    path: str
    message: str


class DraftSpecResponse(BaseModel):
    status: ToolStatus = "stub"
    spec_yaml: str = ""
    summary: str
    warnings: list[str] = Field(default_factory=list)


class ValidateSpecRequest(BaseModel):
    spec: str


class ValidateSpecResponse(BaseModel):
    status: ToolStatus = "stub"
    valid: bool = False
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    summary: str


class GenerateBackendRequest(BaseModel):
    spec: str
    output_dir: str = "."


class GenerateDbRequest(BaseModel):
    spec: str
    output_dir: str = "."
    db_backend: DatabaseBackend = "sqlite"


class GenerateTestsRequest(BaseModel):
    spec: str
    output_dir: str = "."


class GenerateContainersRequest(BaseModel):
    project_name: str
    output_dir: str = "."
    include_db: bool = True


class GenerateAllOptions(BaseModel):
    db_backend: DatabaseBackend = "sqlite"
    include_tests: bool = True
    include_containers: bool = True


class GenerateAllRequest(BaseModel):
    spec: str
    project_name: str
    output_dir: str = "."
    options: GenerateAllOptions = Field(default_factory=GenerateAllOptions)


class GenerationResponse(BaseModel):
    status: ToolStatus = "stub"
    files_written: list[str] = Field(default_factory=list)
    summary: str
    models: list[str] = Field(default_factory=list)
    test_count: int = 0
