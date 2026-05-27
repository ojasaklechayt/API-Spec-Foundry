# API Spec Foundry

Foundry is a Claude Code plugin plus local MCP server for deterministic API
spec drafting, validation, and project generation. The tested happy path for
this repo is:

```text
draft_spec -> validate_spec -> generate_all -> generated pytest
```

Generated output is expected under `<output_dir>/<project_slug>/`.

## Install

Prerequisites:

- `uv`
- Claude Code with plugin support enabled

Install the plugin from this repo:

```bash
/plugin install /app
/plugin list
```

The plugin activates the `foundry` agent and wires the local MCP server from
`.mcp.json`. The runtime entrypoint is `uv run --project server python -m server.main`.

## Generate The Task Manager Demo

Use the `foundry` agent and provide a Task Manager prompt that includes:

- `User` with `email`, `name`, `is_active`
- `Task` with `title`, `status`, `due_date`, `user_id`
- auth `none`
- database `sqlite`

Expected agent flow:

1. `draft_spec`
2. user confirmation
3. `validate_spec`
4. `generate_all`

The generated project target should be:

```text
<output_dir>/task-manager/
```

## Verify

Run the server-side verification suites from the repo root:

```bash
uv run --project /app/server --extra dev pytest /app/tests/e2e/test_foundry_demo.py
uv run --project /app/server --extra dev pytest /app/tests/server /app/tests/e2e/test_foundry_demo.py
```

Current branch note: Story 19 depends on Story 17's generator implementation.
If `generate_all` is still scaffold-only, the e2e proof test records that state
as an explicit dependency `xfail` instead of reporting a false green run.

When the generator pipeline is healthy, the e2e test performs the full temp-dir
flow and runs:

```bash
uv run --project <generated_project> pytest
```

## Evidence To Record Back In MindLap

Capture:

- exact `uv run ... pytest ...` commands
- pass/fail or `xfail` counts
- whether the generated project pytest run completed cleanly
- any reproduced Story 17 generator defect if the e2e proof is blocked
