# poc-boilerplate

Starter for MindLap POCs. FastAPI + SQLite backend, React + Vite frontend,
typed SDK auto-generated from the backend's OpenAPI schema.

```
backend/   FastAPI app, SQLite (async SQLAlchemy), /healthz
frontend/  React + Vite + Tailwind, TanStack Query, generated SDK in src/client/
```

## First-time setup

```bash
# Backend
cd backend
uv venv
uv pip install -e ".[dev]"

# Frontend
cd ../frontend
pnpm install

# Env
cd ..
cp .env.example backend/.env
```

## Run locally

Two terminals.

```bash
# Terminal 1 — backend on :8000
cd backend
source .venv/bin/activate.fish   # or .venv/bin/activate for bash/zsh
uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2 — frontend on :5173
cd frontend
pnpm dev
```

Verify:

```bash
curl http://localhost:8000/healthz
# {"status":"ok"}
```

Open http://localhost:5173 — the home page calls `useHealth()`, which goes
through the generated SDK, and renders `ok`.

## How the SDK works

The frontend never hand-writes API calls. It talks to the backend through a
TypeScript SDK generated from the backend's OpenAPI schema
(`@hey-api/openapi-ts`).

- Generated SDK lives in `frontend/src/client/` — **committed to the repo** so
  a fresh clone builds without regenerating.
- Hand-written hooks in `frontend/src/api/` wrap the generated SDK for
  TanStack Query (`useHealth` in `src/api/health.ts` is the reference).
- Components consume those hooks via `useQuery` / `useMutation` — they never
  import from `src/client/` directly.

**Never hand-edit `src/client/*.gen.ts` — it is overwritten on every regen.**

## Regenerate the SDK (when backend routes or schemas change)

In production the SDK is regenerated only when the backend API changes. The
`/openapi.json` endpoint is gated by the `DEBUG` flag — set it to `true` in
`.env` to expose the schema, then back to `false` before committing.

```bash
# 1. Enable the OpenAPI endpoint
#    edit backend/.env: DEBUG=true
# 2. Start the backend (see above) — it will serve /openapi.json
# 3. Regenerate from frontend/
cd frontend
pnpm regen
# Equivalent to:
#   pnpm run update-schema   # curl /openapi.json -> openapi.json
#   pnpm run generate-sdk    # openapi-ts -> src/client/*.gen.ts
# 4. Revert DEBUG=false in backend/.env
# 5. Review the openapi.json diff, update wrappers in src/api/ as needed,
#    and commit both openapi.json and src/client/*.gen.ts
```

## Add a new route end-to-end

1. **Backend** — add a route file under `backend/app/routes/`, define Pydantic
   request/response models (in the same file or `routes/schemas.py`).
2. **Register** it in `backend/app/main.py`:
   ```python
   from app.routes.my_feature import router as my_feature_router
   app.include_router(my_feature_router, prefix="/api")
   ```
3. **DB model (optional)** — add a SQLAlchemy model under `backend/app/db/`,
   then import it in `backend/app/db/base.py` so `Base.metadata` sees it
   before `init_db()` runs `create_all()`. SQLite, no migrations — the table
   is created on next backend restart.
4. **Set `DEBUG=true`** in `backend/.env`, restart the backend.
5. **Regenerate** from `frontend/`: `pnpm regen`.
6. **Wrap** the new generated function in `frontend/src/api/<feature>.ts`,
   following the `health.ts` pattern. Use `useQuery` for reads and
   `useMutation` for writes.
7. **Use** the hook from a component.
8. **Revert `DEBUG=false`** before committing.

## Verify

```bash
# Backend
cd backend
pytest

# Frontend
cd ../frontend
pnpm typecheck
pnpm build
```

## Notes

- SQLite file (`poc.db`) sits next to the backend and is gitignored. For
  POCs this is fine; it gets wiped per environment.
- No Docker, no deploy script, no auth in the template. Add per-POC.
- Tailwind is set up with an empty theme. Plug Penpot design tokens into
  `tailwind.config.js` per-POC.
