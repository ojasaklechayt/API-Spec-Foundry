# API Spec Foundry — Feature Specification

> **Status:** Draft · POC phase  
> **Author:** ojas@mindlap.dev  
> **Last updated:** 2026-05-27

---

## 1. What it is

API Spec Foundry is a **Claude Code Plugin** that ships a custom **agent** — the same pattern as `trim:code`. When the plugin is installed and the `foundry` agent is active, the user just describes what they want; the agent calls Foundry's MCP tools to draft specs, validate them, and generate a complete, runnable project directly into the working directory.

Foundry is a **pure code-gen engine** — no LLM inside, no API key required. The agent (Claude) is the intelligence. The MCP tools are plain functions wrapped in a thin stdio JSON-RPC layer.

**On "does it have to be MCP?"** — Yes, MCP is the only way Claude can call your functions. But MCP is not a framework or a server stack — it is literally: read JSON from stdin, call your function, write JSON to stdout. Your generators stay plain functions; MCP is just the pipe Claude uses to reach them.

---

## 2. Plugin structure

```
api-spec-foundry/
├── .claude-plugin/
│   ├── plugin.json          # plugin identity
│   └── marketplace.json     # local store registration (required for /plugin install)
├── agents/
│   └── foundry.md           # flat file — NOT a subdirectory
├── servers/
│   └── foundry.js           # MCP server — zero npm deps, pure Node built-ins
├── .mcp.json                # dev-mode wiring (uses ${CLAUDE_PLUGIN_ROOT})
├── settings.json            # sets foundry as default agent
└── README.md
```

> **Why Node.js?** Node ships bundled with Claude Desktop and Claude Code — zero install step, no venv, no `pip install`. The generators write Python files; the server that calls them can be any language.

---

## 3. Plugin registration files

### `.claude-plugin/plugin.json`
```json
{
  "name": "api-spec-foundry",
  "description": "Spec-first API generator. Describe your API, get a runnable FastAPI project.",
  "version": "0.1.0",
  "author": { "name": "mindlap.dev", "email": "ojas@mindlap.dev" },
  "license": "MIT"
}
```

### `.claude-plugin/marketplace.json`
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

### `settings.json`
```json
{
  "agent": "api-spec-foundry:foundry"
}
```

### Install commands (user runs once)
```bash
/plugin marketplace add ~/path/to/api-spec-foundry
/plugin install api-spec-foundry@api-spec-foundry-marketplace
/plugin list   # confirm active
```

---

## 4. The `foundry` agent (`agents/foundry.md`)

Flat markdown file in `agents/`. File name = agent name. Full name after install: `api-spec-foundry:foundry`.

### Frontmatter fields that exist

| Field | Purpose |
|---|---|
| `name` | Agent identifier |
| `description` | Shown in `/agents` list |
| `model` | Pin model or `inherit` |
| `disallowedTools` | Comma-separated built-in tools to **block** |

There is no `tools:` allowlist in the frontmatter. To restrict Claude to MCP tools, **block the built-in equivalents** via `disallowedTools`.

### `agents/foundry.md`
```markdown
---
name: foundry
description: Spec-first API generator. Describe your API; Foundry builds it.
model: inherit
disallowedTools: Edit, MultiEdit, Write, Glob
---

You are Foundry, a spec-first API generation agent.

You help users go from a plain-English API description to a runnable FastAPI
project. You do this by calling Foundry's MCP tools — never by writing files
yourself.

## Workflow

1. **Gather** — ask the user one focused question covering: resources + key
   fields, auth (none / bearer / api_key), and DB (sqlite or postgres).
   Do not ask multiple separate questions.

2. **Draft** — call `mcp__plugin_api_spec_foundry_core__draft_spec` with the
   structured input. Show the user a short summary (resources, endpoint count).
   Ask: “Does this look right, or any changes?”

3. **Validate** — call `mcp__plugin_api_spec_foundry_core__validate_spec`.
   If errors, fix them and re-draft silently. Surface only if unfixable.

4. **Generate** — call `mcp__plugin_api_spec_foundry_core__generate_all`.
   Print the file list and the exact command to run the server. Stop there.

## Rules
- Never write files manually. Always use the MCP tools.
- Keep responses short. Let tool output speak for itself.
- If the user says “just generate it”, skip step 2’s confirmation.
```

### Tool name format

Once installed, MCP tools are callable as:
```
mcp__plugin_<plugin-name>_<server-key>__<ToolName>
```
Hyphens in plugin name → underscores. Plugin `api-spec-foundry`, server key `core`:
```
mcp__plugin_api_spec_foundry_core__draft_spec
mcp__plugin_api_spec_foundry_core__validate_spec
mcp__plugin_api_spec_foundry_core__generate_all
```

---

## 5. MCP server (`.mcp.json` + `servers/foundry.js`)

### `.mcp.json`
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
`${CLAUDE_PLUGIN_ROOT}` — env var Claude Code sets automatically to the plugin’s installed location.
Server key is `core` — this is what appears in the tool name prefix.

### `servers/foundry.js` — structure
Zero npm dependencies. Pure Node.js built-ins (`node:readline`, `node:fs`, `node:path`).

```js
#!/usr/bin/env node
import { createInterface } from 'node:readline';
// import generator logic from local modules

const TOOLS = [
  { name: 'draft_spec',   description: '...', inputSchema: { ... } },
  { name: 'validate_spec', description: '...', inputSchema: { ... } },
  { name: 'generate_backend', ... },
  { name: 'generate_db', ... },
  { name: 'generate_tests', ... },
  { name: 'generate_containers', ... },
  { name: 'generate_all', ... },
];

async function handleToolCall(name, args) {
  // dispatch to generator functions
}

// JSON-RPC 2.0 over stdio
const rl = createInterface({ input: process.stdin, terminal: false });
rl.on('line', async (line) => {
  const { jsonrpc, id, method, params } = JSON.parse(line);
  let result;
  if (method === 'initialize') {
    result = { protocolVersion: '2024-11-05', capabilities: { tools: {} },
               serverInfo: { name: 'api-spec-foundry', version: '0.1.0' } };
  } else if (method === 'tools/list') {
    result = { tools: TOOLS };
  } else if (method === 'tools/call') {
    const text = await handleToolCall(params.name, params.arguments ?? {});
    result = { content: [{ type: 'text', text }] };
  } else { result = {}; }
  process.stdout.write(JSON.stringify({ jsonrpc, id, result }) + '\n');
});
```

---

## 6. MCP Tools (the engine)

All tools live as plain JS functions inside `servers/`. The JSON-RPC layer in `foundry.js` is just the dispatcher.

### `draft_spec`
```
Input:
  project_name  string
  resources     []{name, fields[]{name,type,required,nullable}, endpoints[]string}
  auth          "none"|"bearer"|"api_key"   default: none

Output (JSON string):
  spec_yaml     string   complete OpenAPI 3.1 YAML
  summary       string   "3 resources, 15 endpoints"
```

### `validate_spec`
```
Input:  spec   string (raw YAML or JSON)
Output: valid bool, errors[]{path,message}, warnings[]{path,message}
```

### `generate_backend`
```
Input:  spec, output_dir (default: cwd)
Output: files_written[]string
```
Emits FastAPI routers + Pydantic v2 models, one file per OAS tag.

### `generate_db`
```
Input:  spec, output_dir, db_backend ("sqlite"|"postgres", default: sqlite)
Output: files_written[]string, models[]string
```
Emits async SQLAlchemy models from `components/schemas`.

### `generate_tests`
```
Input:  spec, output_dir
Output: files_written[]string, test_count int
```
Emits pytest contract tests: happy path + schema assertion + negative (422).

### `generate_containers`
```
Input:  project_name, output_dir, include_db bool
Output: files_written[]string
```
Emits multi-stage `Dockerfile`, `docker-compose.yml`, `.env.example`.

### `generate_all`
```
Input:
  spec          string   validated OAS YAML/JSON
  project_name  string
  output_dir    string   default: cwd
  options: { db_backend, include_tests, include_containers }

Output:  files_written[]string, summary string
```

---

## 7. What gets generated

```
<output_dir>/
├── openapi.yaml
├── app/
│   ├── main.py
│   ├── core/config.py
│   ├── db/base.py, session.py
│   ├── db/models/task.py, user.py, comment.py
│   └── routes/tasks.py, users.py, comments.py
├── tests/conftest.py, test_tasks.py, test_users.py, test_comments.py
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── pyproject.toml
```

---

## 8. User flow

```
# One-time install
/plugin marketplace add ~/path/to/api-spec-foundry
/plugin install api-spec-foundry@api-spec-foundry-marketplace

# Activate agent globally (optional — or per-project .claude/settings.json)
# ~/.claude/settings.json: { "agent": "api-spec-foundry:foundry" }

# Then just talk:
User:   "I need a Task Manager API. Tasks have title, status, due date.
         Users own tasks. SQLite. No auth."

Foundry: [calls draft_spec → 2 resources, 10 endpoints]
         Here’s what I drafted:
         • Task — list, create, get, update, delete
         • User — list, create, get, update, delete
         Auth: none. DB: SQLite. Look good?

User:   "Yes"

Foundry: [calls validate_spec → clean]
         [calls generate_all]
         Done. 21 files created.
         Next: uv run uvicorn app.main:app --reload
```

---

## 9. Technical stack

| Layer | Choice | Why |
|---|---|---|
| MCP server | Node.js, zero deps | Bundled with Claude — no install step for users |
| Generator logic | Node.js modules in `servers/` | Co-located with the server, no subprocess |
| Spec parsing | JS OAS parser (`@readme/openapi-parser`, or hand-rolled) | No Python dep for the plugin itself |
| Code generation | Template literals / mustache | Simple; no build step |
| Generated backend | FastAPI + Pydantic v2 + SQLAlchemy async | Matches the existing boilerplate |
| Generated tests | pytest + pytest-asyncio + httpx | Matches the existing boilerplate |

---

## 10. POC checklist

### Plugin scaffolding
- [ ] `.claude-plugin/plugin.json`
- [ ] `.claude-plugin/marketplace.json`
- [ ] `agents/foundry.md` (flat file, correct frontmatter with `disallowedTools`)
- [ ] `settings.json` with `"agent": "api-spec-foundry:foundry"`
- [ ] `.mcp.json` using `${CLAUDE_PLUGIN_ROOT}` and server key `core`

### MCP server
- [ ] `servers/foundry.js` — JSON-RPC 2.0 stdio skeleton
- [ ] `draft_spec` tool
- [ ] `validate_spec` tool
- [ ] `generate_backend` tool
- [ ] `generate_db` tool
- [ ] `generate_tests` tool
- [ ] `generate_containers` tool
- [ ] `generate_all` tool

### End-to-end
- [ ] `/plugin install` works, agent appears in `/agents`
- [ ] Describe API → agent calls tools in correct order → files written
- [ ] Generated project passes `uv run pytest` with zero manual edits

---

## 11. Open questions

| # | Question |
|---|---|
| 1 | `output_dir` — always default to `cwd`? That way the agent never needs to ask. |
| 2 | Should the agent confirm the draft with the user before generating, or just generate and let them iterate? |
| 3 | OAS validation in Node: use `@readme/openapi-parser` (one dep) or a hand-rolled check (zero deps)? |

---

## Sources
- [Create plugins — Claude Code Docs](https://code.claude.com/docs/en/create-plugins)
- [Plugins reference — Claude Code Docs](https://code.claude.com/docs/en/plugins-reference)
- [Claude Code Plugin System — Trim concepts guide](internal)
