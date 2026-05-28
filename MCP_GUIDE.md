# API Spec Foundry — MCP Tools Guide

> **Who this is for:** Engineers using or extending the `foundry` agent.  
> **What it covers:** Every MCP tool — inputs, internals, outputs, the order they must be called, why that order matters, and why this beats asking plain Claude to write code.

---

## 1. What the MCP layer is

MCP (Model Context Protocol) is the only way Claude can call your functions. It is not a framework — it is literally:

```
Claude  →  JSON-RPC call over stdio  →  your function  →  JSON result  →  Claude
```

The Foundry server (`server/main.py`) is a FastMCP process. Claude Code spawns it from `.mcp.json`. Each tool is a plain Python function with a Pydantic request/response model. The MCP layer is just the dispatcher.

Tool names inside the agent follow the pattern:
```
mcp__foundry__<tool_name>
```

---

## 2. The seven tools

### Tool 1 — `draft_spec`

**What it does:** Converts a structured API description into a complete, deterministic OpenAPI 3.1 YAML document.

**Input (`DraftSpecRequest`)**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `project_name` | `string` | ✅ | — | Used as `info.title` and directory slug |
| `resources` | `ResourceInput[]` | ✅ | — | At least one resource |
| `auth` | `"none"\|"bearer"\|"api_key"` | — | `"none"` | Adds security scheme to spec |
| `db_backend` | `"sqlite"\|"postgres"` | — | `"sqlite"` | Stored in spec `x-` extension; downstream generators read it |

**`ResourceInput` shape**

```json
{
  "name": "Task",
  "fields": [
    { "name": "title",   "type": "string",   "required": true,  "nullable": false },
    { "name": "status",  "type": "string",   "required": true,  "nullable": false },
    { "name": "due_date","type": "string",   "required": false, "nullable": true  },
    { "name": "user_id", "type": "integer",  "required": true,  "nullable": false }
  ],
  "endpoints": ["list", "create", "get", "update", "delete"]
}
```

Allowed `type` values: `string`, `integer`, `boolean`, `number` — mapped to OAS/Python types downstream.  
Allowed `endpoints` values: `list`, `create`, `get`, `update`, `delete`.

**Internals:** `server/spec_builder.py`  
Builds a structured `dict` walking every resource → fields → endpoints. Emits `paths`, `components/schemas`, security schemes, and `x-foundry-db-backend` extension. Serialised to YAML with PyYAML.

**Output (`DraftSpecResponse`)**

| Field | Type | Notes |
|---|---|---|
| `status` | `"ok"\|"invalid"` | `"invalid"` if resources are empty or malformed |
| `spec_yaml` | `string` | Full OAS 3.1 YAML — pass this verbatim to every downstream tool |
| `summary` | `string` | e.g. `"2 resources, 10 endpoints"` — show this to the user |
| `resource_count` | `int` | |
| `endpoint_count` | `int` | |
| `warnings` | `ValidationIssue[]` | Non-blocking issues; show to user |

---

### Tool 2 — `validate_spec`

**What it does:** Runs structural and semantic checks against an OAS document. Must pass before any generator runs.

**Input (`ValidateSpecRequest`)**

| Field | Type | Required | Notes |
|---|---|---|---|
| `spec` | `string` | ✅ | Raw YAML or JSON — output of `draft_spec` or user-supplied |

**Internals:** `server/validator.py`  
Parses the spec to a dict, then checks:
- `info.title` and `info.version` present
- At least one path defined
- Every operation has a unique `operationId`
- Every `$ref` resolves to a defined schema in `components/schemas`
- Request bodies reference valid schemas

**Output (`ValidateSpecResponse`)**

| Field | Type | Notes |
|---|---|---|
| `status` | `"ok"\|"invalid"` | |
| `valid` | `bool` | `true` = safe to generate |
| `errors` | `ValidationIssue[]` | Blocking — generation should not proceed |
| `warnings` | `ValidationIssue[]` | Non-blocking — surface to user |
| `summary` | `string` | Human-readable verdict |
| `operation_count` | `int` | Sanity check |

`ValidationIssue` shape: `{ path: string, message: string }` — e.g. `{ path: "/info/title", message: "required field missing" }`.

---

### Tool 3 — `generate_backend`

**What it does:** Generates the FastAPI application skeleton — routers, Pydantic schemas, and the app entrypoint.

**Input (`GenerateBackendRequest`)**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `spec` | `string` | ✅ | — | Validated OAS YAML |
| `output_dir` | `string` | — | `"."` | Absolute or relative path; project slug is appended automatically |

**Internals:** `server/generators/backend.py`  
Passes the spec through `server/parser.py` → internal IR (resource list, field types, endpoint map). Renders Jinja2 templates:

| Template | Output file |
|---|---|
| `app/main.py.j2` | `app/main.py` — router registration, lifespan, CORS |
| `app/routes/resource.py.j2` | `app/routes/<resource>.py` — per-resource `APIRouter` |

**Output (`GenerationResponse`)**

| Field | Type | Notes |
|---|---|---|
| `status` | `"ok"\|"invalid"` | |
| `files_written` | `string[]` | Relative paths under `output_dir` |
| `summary` | `string` | e.g. `"Generated backend scaffold for task-manager."` |

---

### Tool 4 — `generate_db`

**What it does:** Generates async SQLAlchemy models, a session factory, and app config derived from `components/schemas`.

**Input (`GenerateDbRequest`)**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `spec` | `string` | ✅ | — | Validated OAS YAML |
| `output_dir` | `string` | — | `"."` | |
| `db_backend` | `"sqlite"\|"postgres"` | — | `"sqlite"` | Overrides spec extension if provided |

**Internals:** `server/generators/db.py`  
Templates:

| Template | Output file |
|---|---|
| `app/db/models/resource.py.j2` | `app/db/models/<resource>.py` — `DeclarativeBase` subclass |
| `app/db/models/__init__.py.j2` | `app/db/models/__init__.py` |
| `app/db/base.py.j2` | `app/db/base.py` — imports all models, exports `Base.metadata` |
| `app/db/session.py.j2` | `app/db/session.py` — async session factory |
| `app/core/config.py.j2` | `app/core/config.py` — Pydantic Settings |

**Output (`GenerationResponse`)** — same shape as above; includes `models[]` list.

---

### Tool 5 — `generate_tests`

**What it does:** Generates a pytest contract test suite — happy path, schema assertions, and 422 negative tests — for every endpoint.

**Input (`GenerateTestsRequest`)**

| Field | Type | Required | Default |
|---|---|---|---|
| `spec` | `string` | ✅ | — |
| `output_dir` | `string` | — | `"."` |

**Internals:** `server/generators/tests.py`  
Templates:

| Template | Output file |
|---|---|
| `tests/conftest.py.j2` | `tests/conftest.py` — `AsyncClient` fixture, in-memory SQLite |
| `tests/test_resource.py.j2` | `tests/test_<resource>.py` — 3 tests per endpoint |

**Output (`GenerationResponse`)** — includes `test_count` integer.

---

### Tool 6 — `generate_containers`

**What it does:** Generates Docker and deployment assets — Dockerfile, Compose file, env example, and `pyproject.toml`.

**Input (`GenerateContainersRequest`)**

| Field | Type | Required | Default | Notes |
|---|---|---|---|---|
| `project_name` | `string` | ✅ | — | Used in image names, service names |
| `output_dir` | `string` | — | `"."` | |
| `db_backend` | `"sqlite"\|"postgres"` | — | `"sqlite"` | Adds `db` service to Compose if `postgres` |
| `include_db` | `bool` | — | `true` | Toggle Compose DB service |

**Internals:** `server/generators/containers.py`  
Templates:

| Template | Output file |
|---|---|
| `Dockerfile.j2` | `Dockerfile` — multi-stage, HEALTHCHECK on `/healthz` |
| `docker-compose.yml.j2` | `docker-compose.yml` |
| `.env.example.j2` | `.env.example` |

**Output (`GenerationResponse`)** — files written list.

---

### Tool 7 — `generate_all`

**What it does:** Runs the full pipeline in one call — validation gate, then all four generators in dependency order.

**Input (`GenerateAllRequest`)**

| Field | Type | Required | Default |
|---|---|---|---|
| `spec` | `string` | ✅ | — |
| `project_name` | `string` | ✅ | — |
| `output_dir` | `string` | — | `"."` |
| `options.db_backend` | `"sqlite"\|"postgres"` | — | `"sqlite"` |
| `options.include_tests` | `bool` | — | `true` |
| `options.include_containers` | `bool` | — | `true` |

**Internals:** `server/generators/orchestrator.py`  
Internal execution order:

```
1. validate_openapi_spec(spec)          ← abort if errors
2. build_ir(spec)                       ← parse once, share IR
3. generate_backend(ir, output_root)
4. generate_db(ir, output_root, db_backend)
5. generate_tests(ir, output_root)      ← if include_tests
6. generate_containers(...)             ← if include_containers
7. write openapi.yaml to output_root
```

**Output (`GenerationResponse`)** — aggregated `files_written`, `models`, `test_count`, and a `summary` with the project root path.

---

## 3. Call order and why it matters

```
draft_spec  →  validate_spec  →  generate_all
     (1)             (2)             (3)
```

This is the canonical agent flow. Here is why each step must precede the next:

### Step 1: `draft_spec` before everything

`draft_spec` is the **source of truth** for the entire project. Every downstream generator reads from the same `spec_yaml` string it produces. If you skip it and pass a hand-written or user-supplied spec directly, you risk:

- Non-standard OAS structure the parser doesn't handle (unknown field names, wrong `$ref` paths)
- Missing `x-foundry-db-backend` extension that `generate_db` reads
- `operationId` collisions that break the test generator's file-naming logic

**Rule:** Always call `draft_spec` first, even when the user supplies a partial spec — treat user input as _input to the drafter_, not as the spec itself.

### Step 2: `validate_spec` before any generator

The generators do **no error handling** for malformed specs — they fail with stack traces, not friendly messages. `validate_spec` is the gate:

- Catches missing `info.title` / `info.version` before they cause silent bad output
- Detects broken `$ref` chains before the parser throws
- Returns structured `errors[]` with JSON paths so the agent can ask the user a targeted fix question instead of dumping a traceback

`generate_all` runs `validate_spec` internally and aborts if it fails — but if you call generators individually (`generate_backend`, `generate_db`, etc.), you must validate first yourself.

### Step 3: Generator order within `generate_all`

When calling individual generators (not `generate_all`), order matters:

```
generate_backend  →  generate_db  →  generate_tests  →  generate_containers
```

| Why this order | Detail |
|---|---|
| `backend` before `db` | Routes import SQLAlchemy models by name; models must exist on disk for `import` resolution in generated conftest |
| `db` before `tests` | `conftest.py` imports `Base.metadata` from `app/db/base.py`; base file is written by `generate_db` |
| `tests` before `containers` | `pyproject.toml` written by containers must include `pytest` and `httpx` as dev deps; knowing `test_count > 0` lets the template conditionally add them |
| `containers` last | `Dockerfile` and Compose reference the project structure; must know all files exist first |

---

## 4. Input → Output flow diagram

```
User description (plain English)
        │
        ▼
┌─────────────────────────────────────┐
│  draft_spec                          │
│  Input:  project_name, resources[],  │
│          auth, db_backend            │
│  Output: spec_yaml (OAS 3.1 YAML)    │
│          summary, resource_count,    │
│          endpoint_count              │
└──────────────┬──────────────────────┘
               │  spec_yaml
               ▼
┌─────────────────────────────────────┐
│  validate_spec                       │
│  Input:  spec (string)               │
│  Output: valid (bool),               │
│          errors[], warnings[],       │
│          operation_count             │
└──────────────┬──────────────────────┘
               │  spec (if valid=true)
               ▼
┌─────────────────────────────────────┐
│  generate_all                        │
│  Input:  spec, project_name,         │
│          output_dir, options{}       │
│                                      │
│  ┌──────────────────────────────┐   │
│  │ build_ir(spec)               │   │
│  └──────┬───────────────────────┘   │
│         ├── generate_backend  ──►  app/routes/, app/main.py │
│         ├── generate_db       ──►  app/db/models/, session   │
│         ├── generate_tests    ──►  tests/                    │
│         ├── generate_containers ► Dockerfile, compose        │
│         └── write openapi.yaml                               │
│                                      │
│  Output: files_written[], summary    │
└─────────────────────────────────────┘
               │
               ▼
   <output_dir>/<project_slug>/
   ├── openapi.yaml
   ├── app/
   │   ├── main.py
   │   ├── core/config.py
   │   ├── db/base.py, session.py
   │   ├── db/models/<resource>.py
   │   └── routes/<resource>.py
   ├── tests/conftest.py, test_<resource>.py
   ├── Dockerfile
   ├── docker-compose.yml
   ├── .env.example
   └── pyproject.toml
```

---

## 5. Using individual generators vs. `generate_all`

| Scenario | Use |
|---|---|
| Full project from scratch | `generate_all` — one call, handles ordering and validation gate |
| Regenerate only routes after schema change | `validate_spec` → `generate_backend` |
| Add Postgres support to existing project | `validate_spec` → `generate_db(db_backend="postgres")` |
| Add tests to existing project | `validate_spec` → `generate_tests` |
| Re-containerize after rename | `generate_containers` (no spec needed, no validation required) |

---

## 6. Why this MCP approach beats plain Claude

### The core problem with plain Claude writing code

When you ask Claude to "write me a FastAPI project," Claude is doing two things at once:
1. **Deciding** what the API should look like (implicit spec)
2. **Writing** 20+ files from memory

This conflates design with implementation. The result is:

| Problem | Plain Claude | Foundry MCP |
|---|---|---|
| **Non-determinism** | Two runs of the same prompt produce different file structures, import paths, or naming conventions | Same `spec_yaml` always produces identical output — templates are deterministic |
| **No validation gate** | Claude generates code that may have broken imports, wrong `$ref`s, or contradictory models | `validate_spec` catches structural errors before a single file is written |
| **No audit trail** | The spec lives in Claude's context; can't version or diff it | `draft_spec` returns an explicit YAML artifact you can commit, share, and re-run |
| **Silent schema drift** | If you ask Claude to add a field, it may update routes but forget models (or vice versa) | All generators read the same IR from the spec; schema changes propagate everywhere atomically |
| **No incremental regeneration** | Asking Claude to "regenerate just the tests" risks rewriting things it shouldn't touch | Individual tools (`generate_tests`) scope to one layer; other files are untouched |
| **Context window exhaustion** | Large projects (20+ files) overflow context; Claude starts forgetting earlier files | Generators run entirely in Python; file I/O is off-model |
| **Token cost** | Writing 20 files in Claude's context burns ~30–80k tokens per run | `generate_all` writes files without returning their content to context; output is just a file list |

### What the agent adds on top

The agent (`agents/foundry/AGENT.md`) is the only piece that uses Claude's reasoning. It handles:
- **Natural language parsing** — turns "Users own tasks, SQLite, no auth" into a structured `DraftSpecRequest`
- **Clarification** — asks one focused question when required fields are missing
- **Confirmation gate** — shows the draft summary and waits for user sign-off before generating
- **Error translation** — if `validate_spec` returns `{ path: "/paths/~1tasks/get", message: "missing operationId" }`, the agent rewrites it as a plain English question

Clause's reasoning is used **only** for language understanding and conversation flow. File generation is entirely off-model.

---

## 7. Quick reference — complete call sequence

### Happy path (agent standard flow)

```python
# 1. Agent gathers description, structures it:
draft = mcp__foundry__draft_spec({
    "project_name": "task-manager",
    "resources": [
        {
            "name": "User",
            "fields": [
                {"name": "email",     "type": "string",  "required": True},
                {"name": "name",      "type": "string",  "required": True},
                {"name": "is_active", "type": "boolean", "required": True}
            ],
            "endpoints": ["list", "create", "get", "update", "delete"]
        },
        {
            "name": "Task",
            "fields": [
                {"name": "title",    "type": "string",  "required": True},
                {"name": "status",   "type": "string",  "required": True},
                {"name": "due_date", "type": "string",  "required": False, "nullable": True},
                {"name": "user_id",  "type": "integer", "required": True}
            ],
            "endpoints": ["list", "create", "get", "update", "delete"]
        }
    ],
    "auth": "none",
    "db_backend": "sqlite"
})
# draft.status == "ok"
# draft.summary == "2 resources, 10 endpoints"   ← show user

# 2. Validate:
validation = mcp__foundry__validate_spec({ "spec": draft.spec_yaml })
# validation.valid == True
# If False: fix and re-draft

# 3. Generate everything:
result = mcp__foundry__generate_all({
    "spec": draft.spec_yaml,
    "project_name": "task-manager",
    "output_dir": ".",
    "options": {
        "db_backend": "sqlite",
        "include_tests": True,
        "include_containers": True
    }
})
# result.status == "ok"
# result.files_written → 21 paths
# result.summary → "Generated project at ./task-manager"
```

### Running the generated project
```bash
cd task-manager
uv run uvicorn app.main:app --reload
# or run tests:
uv run pytest
```

---

## 8. Error handling reference

| Tool | What can go wrong | How it surfaces |
|---|---|---|
| `draft_spec` | Empty resources, unknown field type | `status: "invalid"`, `summary` has message, `spec_yaml` is empty |
| `validate_spec` | Missing `info`, broken `$ref`, duplicate `operationId` | `valid: false`, `errors[]` with JSON paths |
| `generate_backend` | Spec unparseable after validation passed | `status: "invalid"`, `summary` has exception message |
| `generate_db` | Unknown OAS type with no Python mapping | `status: "invalid"` |
| `generate_tests` | Same | `status: "invalid"` |
| `generate_containers` | Bad project name (empty) | `status: "invalid"` |
| `generate_all` | Validation fails on entry | Returns immediately with validation summary, no files written |

All tools return clean JSON — they never raise to the agent. The agent checks `status` and `valid` on every response.

---

## 9. Source file map

| Concern | File |
|---|---|
| MCP server entry + tool dispatch | `server/main.py` |
| Request / response models | `server/tool_schemas.py` |
| Spec builder (draft_spec engine) | `server/spec_builder.py` |
| OAS validator | `server/validator.py` |
| OAS → internal IR parser | `server/parser.py` |
| Backend generator | `server/generators/backend.py` |
| DB generator | `server/generators/db.py` |
| Test generator | `server/generators/tests.py` |
| Container generator | `server/generators/containers.py` |
| `generate_all` orchestrator | `server/generators/orchestrator.py` |
| Shared file-write utilities | `server/generators/common.py` |
| Jinja2 templates | `server/templates/` |
| Agent system prompt | `agents/foundry/AGENT.md` |
| MCP server wiring | `.mcp.json` |
| Unit tests | `tests/server/` |
| End-to-end proof test | `tests/e2e/test_foundry_demo.py` |
| Fixture spec | `tests/fixtures/task_manager_openapi.yaml` |
