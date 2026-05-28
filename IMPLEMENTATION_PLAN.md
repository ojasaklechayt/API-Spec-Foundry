# API Spec Foundry — Implementation Plan

> **POC goal:** Install the plugin, describe an API in plain English, get a runnable FastAPI project.  
> **Rule:** Each phase produces something testable before the next begins.

---

## Phase 0 — Repo & Plugin Skeleton
**Goal:** Plugin loads in Claude Code, `foundry` agent appears in `/agents`, MCP server starts. No tools do real work yet.

### 0.1 — Directory structure
```
api-spec-foundry/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── agents/
│   └── foundry.md           # flat file, not a subdirectory
├── servers/
│   ├── foundry.js           # MCP server entrypoint
│   └── generators/
│       ├── draft.js            # stub
│       ├── validate.js         # stub
│       ├── backend.js          # stub
│       ├── db.js               # stub
│       ├── tests.js            # stub
│       └── containers.js       # stub
├── .mcp.json
├── settings.json
└── README.md
```

### 0.2 — `.claude-plugin/plugin.json`
```json
{
  "name": "api-spec-foundry",
  "description": "Spec-first API generator. Describe your API; get a runnable FastAPI project.",
  "version": "0.1.0",
  "author": { "name": "mindlap.dev", "email": "ojas@mindlap.dev" },
  "license": "MIT"
}
```

### 0.3 — `.claude-plugin/marketplace.json`
```json
{
  "name": "api-spec-foundry-marketplace",
  "owner": { "name": "mindlap.dev", "email": "ojas@mindlap.dev" },
  "metadata": { "description": "API Spec Foundry plugin store" },
  "plugins": [
    {
      "name": "api-spec-foundry",
      "source": "./",
      "description": "Spec-first API generator.",
      "version": "0.1.0"
    }
  ]
}
```

### 0.4 — `settings.json`
```json
{ "agent": "api-spec-foundry:foundry" }
```

### 0.5 — `agents/foundry.md` (stub)
Minimal — enough to confirm the agent loads and appears in `/agents`:
```markdown
---
name: foundry
description: Spec-first API generator. Describe your API; Foundry builds it.
model: inherit
disallowedTools: Edit, MultiEdit, Write, Glob
---

You are Foundry. Tools are not wired yet — this is a skeleton.
```

**Note:** `disallowedTools` blocks Claude’s built-in file-write tools, forcing it to use the MCP tools instead. There is no `tools:` allowlist field in the agent frontmatter — use `disallowedTools` as the restriction mechanism.

### 0.6 — `.mcp.json`
```json
{
  "mcpServers": {
    "core": {
      "command": "node",
      "args": ["${CLAUDE_PLUGIN_ROOT}/servers/foundry.js"]
    }
  }
}
```
Key points:
- **`${CLAUDE_PLUGIN_ROOT}`** — Claude Code sets this env var automatically. Always use it, never hardcode paths.
- **Server key is `core`** — this becomes part of the tool name: `mcp__plugin_api_spec_foundry_core__<ToolName>`.

### 0.7 — `servers/foundry.js` (skeleton)
Zero npm dependencies — pure Node.js built-ins only:
```js
#!/usr/bin/env node
import { createInterface } from 'node:readline';

const TOOLS = [
  { name: 'draft_spec',        description: 'Draft an OpenAPI spec from a description', inputSchema: { type: 'object', properties: { project_name: { type: 'string' }, resources: { type: 'array' }, auth: { type: 'string' } }, required: ['project_name', 'resources'] } },
  { name: 'validate_spec',     description: 'Validate an OpenAPI spec', inputSchema: { type: 'object', properties: { spec: { type: 'string' } }, required: ['spec'] } },
  { name: 'generate_backend',  description: 'Generate FastAPI backend from spec', inputSchema: { type: 'object', properties: { spec: { type: 'string' }, output_dir: { type: 'string' } }, required: ['spec'] } },
  { name: 'generate_db',       description: 'Generate SQLAlchemy models from spec', inputSchema: { type: 'object', properties: { spec: { type: 'string' }, output_dir: { type: 'string' }, db_backend: { type: 'string' } }, required: ['spec'] } },
  { name: 'generate_tests',    description: 'Generate pytest contract tests from spec', inputSchema: { type: 'object', properties: { spec: { type: 'string' }, output_dir: { type: 'string' } }, required: ['spec'] } },
  { name: 'generate_containers', description: 'Generate Dockerfile and docker-compose', inputSchema: { type: 'object', properties: { project_name: { type: 'string' }, output_dir: { type: 'string' }, include_db: { type: 'boolean' } }, required: ['project_name'] } },
  { name: 'generate_all',      description: 'Run all generators end-to-end', inputSchema: { type: 'object', properties: { spec: { type: 'string' }, project_name: { type: 'string' }, output_dir: { type: 'string' }, options: { type: 'object' } }, required: ['spec', 'project_name'] } },
];

async function handleToolCall(name, args) {
  // stubs — replaced in later phases
  return JSON.stringify({ status: 'not_implemented', tool: name });
}

const rl = createInterface({ input: process.stdin, terminal: false });
rl.on('line', async (line) => {
  const { jsonrpc, id, method, params } = JSON.parse(line);
  let result;
  if (method === 'initialize') {
    result = { protocolVersion: '2024-11-05', capabilities: { tools: {} }, serverInfo: { name: 'api-spec-foundry', version: '0.1.0' } };
  } else if (method === 'tools/list') {
    result = { tools: TOOLS };
  } else if (method === 'tools/call') {
    const text = await handleToolCall(params.name, params.arguments ?? {});
    result = { content: [{ type: 'text', text }] };
  } else {
    result = {};
  }
  process.stdout.write(JSON.stringify({ jsonrpc, id, result }) + '\n');
});
```

### Done when
- `claude --plugin-dir ./api-spec-foundry` starts without errors
- `/agents` shows `api-spec-foundry:foundry`
- All 7 tools appear (returning `not_implemented`)
- Local install works:
  ```
  /plugin marketplace add ~/path/to/api-spec-foundry
  /plugin install api-spec-foundry@api-spec-foundry-marketplace
  ```

---

## Phase 1 — Spec Parser: `validate_spec` + `draft_spec`
**Goal:** Both tools work end-to-end. Given a description → get valid OAS YAML. Given a broken spec → get structured errors.

### 1.1 — OAS YAML builder (`servers/generators/draft.js`)
Pure function: takes structured input, returns an OAS 3.1 YAML string.
- Use template literals to build the YAML structure (no external YAML lib needed for generation).
- Output covers: `info`, `paths` (one path+method per endpoint per resource), `components/schemas` (one schema per resource with typed fields).
- `draft_spec` input shape:
  ```
  project_name  string
  resources[]   { name, fields[]{name, type, required, nullable}, endpoints[] }
  auth          "none"|"bearer"|"api_key"
  ```
- OAS type mapping: `string`→`string`, `int`→`integer`, `bool`→`boolean`, `datetime`→`string/date-time`.

### 1.2 — OAS validator (`servers/generators/validate.js`)
Pure function: takes a YAML/JSON string, returns `{ valid, errors[], warnings[] }`.
- Parse YAML to object using a minimal hand-rolled parser (or `node:util` + regex for the POC).
- Validation rules for POC:
  - `info.title` present
  - `info.version` present
  - At least one path defined
  - Each operation has an `operationId`
  - Each request body references a defined schema
- Structured errors: `{ path: "/info/title", message: "required field missing" }`

### 1.3 — Wire into `servers/foundry.js`
Replace `draft_spec` and `validate_spec` stubs with calls to the new modules.

### 1.4 — Tests (`servers/tests/`)
Using Node’s built-in `node:test` (no test framework dep):
```
servers/tests/
├── draft.test.js      # input → valid YAML; round-trip through validate → no errors
└── validate.test.js   # valid spec → clean; missing title → error at /info/title
```

### Done when
- `draft_spec({ project_name: "todo", resources: [{name:"Task", ...}] })` returns valid OAS 3.1 YAML
- `validate_spec(<that YAML>)` returns `{ valid: true, errors: [] }`
- `validate_spec(<broken YAML>)` returns structured errors
- Tests pass with `node --test servers/tests/`

---

## Phase 2 — Code Generators
**Goal:** Each generator is a plain function that takes an OAS YAML string + output dir and writes correct files.

All generators share the same shape:
```
parse YAML → walk resources → render templates → write files → return files_written[]
```

### 2.1 — Shared utilities (`servers/generators/utils.js`)
```js
// writeFile(outputDir, relPath, content)  — creates dirs, writes file
// snakeCase(str)   — "TaskItem" → "task_item"
// pluralise(str)   — "task" → "tasks" (simple rules, no lib)
// pyType(oasType)  — maps OAS types to Python type strings
```

### 2.2 — Backend generator (`servers/generators/backend.js`)
For each resource in the spec, write:
- `app/routes/<resource>.py` — FastAPI `APIRouter`, one async function per endpoint, Pydantic models inline, `# USER LOGIC` placeholder in each handler body
- `app/main.py` — imports + registers every router, lifespan, CORS, exception handler
- `app/routes/schemas.py` — shared Pydantic request/response models

Templates: plain JS template literals. Example fragment:
```js
const routerTemplate = (resource, endpoints) => `
from fastapi import APIRouter, HTTPException
from .schemas import ${resource.name}Response, ${resource.name}Create

router = APIRouter(prefix="/${resource.table_name}", tags=["${resource.name}"])

${endpoints.map(ep => endpointTemplate(resource, ep)).join('\n\n')}
`.trim();
```

### 2.3 — DB generator (`servers/generators/db.js`)
For each resource, write:
- `app/db/models/<resource>.py` — `DeclarativeBase` subclass, one `Column` per field
- `app/db/base.py` — imports all models, exposes `Base.metadata`
- `app/db/session.py` — async session factory
- `app/core/config.py` — Pydantic Settings (`DATABASE_URL`, `CORS_ORIGINS`, `DEBUG`)

### 2.4 — Test generator (`servers/generators/tests.js`)
For each resource, write:
- `tests/test_<resource>.py` — 3 tests per endpoint: happy path, schema assertion, 422 negative
- `tests/conftest.py` — `app` fixture, `AsyncClient` fixture, in-memory SQLite fixture

### 2.5 — Container generator (`servers/generators/containers.js`)
Project-level files only (no resource loop):
- `Dockerfile` — multi-stage (`builder` → `runtime`), HEALTHCHECK on `/healthz`
- `docker-compose.yml` — `backend` service; optional `db` service if Postgres
- `.env.example` — every env var referenced in generated code
- `pyproject.toml` — valid uv-compatible project file with correct deps

### 2.6 — Wire individual tools into `servers/foundry.js`
Replace stubs for `generate_backend`, `generate_db`, `generate_tests`, `generate_containers`.

### 2.7 — Tests
```
servers/tests/
├── backend.test.js     # given fixture spec → assert files exist + key strings in content
├── db.test.js
├── tests.test.js
└── containers.test.js
```
Each test: write to `os.tmpdir()`, assert file exists, assert `class Task(Base)` / `async def list_tasks` etc. appear.

### Done when
- Each generator writes correct files to a temp dir
- Generated Python has no syntax errors (`python -m py_compile <file>`)
- All tests pass

---

## Phase 3 — `generate_all` + Integration
**Goal:** One tool call → complete, runnable project.

### 3.1 — `generate_all` orchestrator (`servers/generators/all.js`)
```
1. validate_spec(spec) → abort if errors
2. BackendGenerator(spec, outputDir)
3. DBGenerator(spec, outputDir, dbBackend)
4. TestGenerator(spec, outputDir)       [if includeTests]
5. ContainerGenerator(projectName, outputDir, includeDb) [if includeContainers]
6. write openapi.yaml to outputDir
7. return { files_written, summary }
```

### 3.2 — Healthz route
Always emit `app/routes/health.py` — `GET /healthz → {"status": "ok"}`.

### 3.3 — Integration test
```js
// servers/tests/integration.test.js
import { test } from 'node:test';
import { execSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { generateAll } from '../generators/all.js';

test('generate_all produces a runnable project', async (t) => {
  const outDir = mkdtempSync(tmpdir() + '/foundry-test-');
  const result = await generateAll(TASK_MANAGER_FIXTURE_SPEC, 'task-manager', outDir, {});

  // files exist
  assert(result.files_written.length >= 20);

  // generated Python is importable
  execSync(`python -c "import sys; sys.path.insert(0,'${outDir}'); from app.main import app"`);

  // generated tests pass
  execSync(`cd ${outDir} && uv run pytest`, { stdio: 'inherit' });
});
```

### Done when
- `generate_all` with the Task Manager fixture spec writes 20+ files
- `uv run pytest` inside the output passes with zero manual edits
- `from app.main import app` imports cleanly

---

## Phase 4 — Agent System Prompt & Conversational Flow
**Goal:** Full end-to-end conversational experience. User describes API → agent calls tools in correct order → runnable project appears.

### 4.1 — Finalize `agents/foundry.md`
Full system prompt with:
- **Gather:** one focused question covering resources, fields, auth, DB. Not one-by-one.
- **Draft:** call `mcp__plugin_api_spec_foundry_core__draft_spec`, show summary, ask for confirmation.
- **Validate:** call `mcp__plugin_api_spec_foundry_core__validate_spec`, fix errors silently, surface only if unfixable.
- **Generate:** call `mcp__plugin_api_spec_foundry_core__generate_all`, print file list + run command.
- **Rules:** never write files directly; always use MCP tools; keep responses concise.

Use the **exact tool names** with underscores (hyphens in plugin name become underscores):
```
mcp__plugin_api_spec_foundry_core__draft_spec
mcp__plugin_api_spec_foundry_core__validate_spec
mcp__plugin_api_spec_foundry_core__generate_all
```

### 4.2 — Manual conversational test scenarios

| Scenario | Expected behaviour |
|---|---|
| "I need a blog API with posts and comments" | Asks 1 clarifying question, drafts, confirms, generates |
| User gives full description upfront | Skips clarifying question, drafts, confirms, generates |
| User requests change after draft | Re-calls `draft_spec`, re-confirms, generates |
| Spec has a validation error | Reports error in plain English, asks how to fix |
| User says "just generate it" | Skips confirmation, calls `generate_all` immediately |

### 4.3 — README.md
- One-line description
- Install commands (marketplace add + plugin install)
- 30-second demo
- Requirements (Node.js 18+ — bundled with Claude Code; Python 3.12+ for running generated output)
- What gets generated

### Done when
- All 5 test scenarios produce correct agent behaviour
- README lets a new user install and use without asking questions

---

## Phase 5 — Polish & Distribution
**Goal:** Plugin is shareable from GitHub and submittable to the community marketplace.

### 5.1 — Error handling
Every tool returns a clean JSON error string instead of throwing:
```js
// Instead of throw:
return JSON.stringify({ error: 'invalid_spec', message: 'Missing info.title' });
```

### 5.2 — Generated code quality
- Run `ruff check` on all generated `.py` files; fix any template issues.
- Spot-check generated type annotations (`mypy --strict` on `app/`).

### 5.3 — Plugin validation
```bash
claude plugin validate   # fix any issues before submission
```

### 5.4 — GitHub release
- Tag `v0.1.0`
- Test install from GitHub:
  ```
  /plugin marketplace add https://github.com/mindlap/api-spec-foundry
  /plugin install api-spec-foundry@api-spec-foundry-marketplace
  ```

### 5.5 — Community marketplace submission
- Submit via `claude.ai/settings/plugins/submit`
- Requirements: `claude plugin validate` clean, README, version pinned in `plugin.json`

### Done when
- Install from GitHub works on a fresh machine
- `claude plugin validate` passes
- Submitted to community marketplace

---

## Summary

| Phase | Builds | Done when |
|---|---|---|
| **0** | Plugin skeleton | Agent loads, MCP server starts, tools return `not_implemented` |
| **1** | `draft_spec` + `validate_spec` | Description → valid OAS YAML; broken spec → structured errors |
| **2** | 4 code generators | Each generator writes correct, importable Python to a temp dir |
| **3** | `generate_all` + integration | One call → full project → `uv run pytest` passes |
| **4** | Agent system prompt | Conversational end-to-end: plain English → runnable project |
| **5** | Polish + distribution | Installable from GitHub, submitted to marketplace |

---

## Build order within phases 1–3
```
write failing test  →  implement function  →  test passes  →  wire into MCP tool  →  smoke-test via agent
```
