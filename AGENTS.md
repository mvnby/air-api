# AGENTS Guide

## Boundaries

- Backend: FastAPI + SQLModel. `routers/` handles HTTP, `services/` owns
  business logic, and `crud/` owns persistence; no direct DB business logic in routers.
- Internal product workflows belong in `manager_frontend/` + `routers/manager_*`.
  SQLAdmin is removed; never reintroduce legacy `/admin` workflows.
- Public storefront source, UI, assets, tests and deployment belong in the
  separate `mvnby/mvn-web` repository. It consumes this API over HTTP only.
- Active staff Telegram polling is deployed from `mvnby/mvn-telegram-bot`;
  this API owns business rules and the internal bot contract.
- Reuse `services/spec_normalizer.py`; add spec definitions/aliases to
  `services/spec_registry.py`, from which the normalizer derives `KEY_MAP`.
- Keep changes focused and modules cohesive. If a touched file exceeds about
  700 lines or mixes responsibilities, propose a bounded split; do not turn a
  small fix into an unrelated repository-wide refactor.
- Manager list endpoints require `limit <= 100`.

## Read by task

Use [docs/README.md](docs/README.md) to locate additional topics; it is a map,
not a checklist of documents to read. Open only the relevant procedure:

| Task | Required entry point |
| --- | --- |
| Local setup, backend/Manager tests, imports/specs, leads or API client changes | [Development workflow](docs/development-workflow.md), relevant section |
| Commit, PR, CI or merge | [Git workflow](docs/git-workflow.md) |
| Production data operation | [Production data operations](docs/production-data-operations.md), then the matching runbook |
| Deployment / HA / database topology | [Deployment](docs/deployment.md) / [API HA](docs/api-ha-runbook.md), relevant procedure; production data gates also apply to mutations |
| Bot contract or runtime ownership | [Bot service boundary](docs/bot-service-boundary.md) |
| Storefront ownership or deployment | [Web service extraction](docs/web-service-extraction.md); UI work continues in `mvn-web` |

Dated audits and rollout plans describe their recorded scope; verify current
code and live state before treating them as present-day facts or authorization.

## Efficient execution

- Locate filenames/symbols with scoped `rg --files` / `rg -n`, then read bounded
  sections. Avoid dumping whole large modules, documents, API schemas or logs.
- For ordinary source searches, skip dependencies, caches, build output,
  `outputs/`, `.codex-tmp/`, lockfiles, `openapi.json` and generated
  `manager_frontend/src/client/`. Open them explicitly when the task needs them;
  these search defaults do not exempt generated artifacts from verification.
- Search within this checkout and the relevant domain. Do not inventory sibling
  worktrees, old task logs or all documentation unless the task requires it.
- Batch independent reads/checks and retain their results; repeat a check only
  after a relevant change, failure, or unresolved concern.
- While CI, deployment or another agent runs, use a bounded watcher/wait facility
  and return concise changed status, failure details or completion. Avoid tight
  sleep-and-query loops that repeatedly wake the model with unchanged results.
  Keep the user informed without re-fetching the same logs for each update.
- Do not remove required tests, release gates or final runtime verification to
  save tokens. A new independent task may start fresh with a short handoff;
  keep related implementation and validation together.

## Delegation and effort

- Choose the least expensive model/effort that reliably fits the task. Recommend
  a cheaper or stronger setting when the user's choice is materially mismatched.
- Terra `low`/`medium`: inventory, documentation, focused checks and small fixes;
  Terra `medium`/`high`: routine implementation/tests and bounded refactors;
  Sol `high`/`xhigh`: architecture, concurrency, migrations, HA and security.
  Reserve the highest efforts for difficult work that justifies their cost.
- This is standing authorization to delegate safe, independent, in-scope work
  only when it costs less than doing it locally. Keep small or tightly coupled
  tasks with one agent; do not create a reviewer for every trivial edit.
- Before worthwhile delegation, say: «Дружища, давай это сделает отдельный агент
  и с пониженными весами». Send the goal, boundaries, paths and acceptance checks,
  not full conversation history unless necessary.
- The primary agent owns integration, validation, publication and the final
  report; a subagent's result is evidence, not automatic approval.

## Verification and production gates

- Run checks appropriate to the changed behavior. Documentation-only edits need
  link/Markdown checks and review of moved instructions, not local application
  builds or database tests. Required CI still applies before merge.
- When API routes, operation IDs or schemas change, regenerate OpenAPI with
  `python3 scripts/legacy/extract_openapi.py`, then run `npm run gen:api` and
  `npm run build` in `manager_frontend/`; commit changed generated artifacts.
- PostgreSQL tests require a separate physical DB per process/worker. Never use
  a production base URL; the base DB name must contain `test`. Keep broad suites
  serial until the worker-isolation proof and CI timing evidence justify xdist.
- Production runs from images, not a git checkout. Data operations start
  report-only/dry-run. Cleanup requires explicit authorization; do not execute
  backfills, provisioning or grants without the linked procedure's review gates.
- Tenant-scope backfill execution is retired after contract migration. Shared
  grants remain system-owned; an empty offer set never means share-all.
- Keep internal Patroni names/SSH aliases/paths `mvn-api` and `zakup` unchanged;
  `mvn-api-nl` and `mvn-api-by` are display names only.
- A deployment is successful only after `/api/health`,
  `/api/v1/products?limit=5` and `/api/v1/filters/config` smoke checks pass.
- After verified changes: commit, push, and open a PR. Follow the Git workflow's
  green-CI gate before merging; never push changes directly to `main`.
