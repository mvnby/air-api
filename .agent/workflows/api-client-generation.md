---
description: How to handle FastAPI schema/router changes and regenerate the OpenAPI client
---
# API Client Generation

**When to use this workflow:**
Whenever you modify FastAPI routers, add new endpoints, change payload/response schemas (`schemas.py`), or update operation IDs.

**The Problem:**
If you change the backend but forget to regenerate the OpenAPI schema and TypeScript client, the CI pipeline step `Verify Manager API Client Is Up To Date` will fail (exit code 1) because the repository's `openapi.json` will be out of sync.

**Steps:**

1. **Verify Backend Changes:** Ensure backend tests pass and all new `operation_id`s are added to `ALL_MANAGER_OPERATION_IDS` in `routers/manager_operation_ids.py`.
2. **Regenerate OpenAPI schema and TypeScript Client:**
// turbo

```bash
python3 scripts/legacy/extract_openapi.py && cd manager_frontend && npm run gen:api
```

3. **Commit the Artifacts:** You must stage and commit `openapi.json` and any changed/added files in `manager_frontend/src/client/`.
// turbo

```bash
git add openapi.json manager_frontend/src/client
```

4. **Push:** Now you can push your features and the CI will pass.
