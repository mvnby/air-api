# MVN / Kitlane agent guide

## Working contract

- Define the requested outcome and a check that proves it; use a short plan only
  for multi-step or risky work. A requested fix includes in-scope edits and tests;
  honor existing authorization. Analysis-only requests stop at findings.
- Inspect the branch and working tree; preserve unrelated work. Fix the cause,
  keep the change cohesive, and review the diff before publishing.
- After verified changes: commit, push, PR, green CI, then squash merge per
  [Git workflow](docs/git-workflow.md). Verify any triggered deployment and its
  smoke checks before claiming completion; never push directly to `main`.

## Boundaries

- Backend: FastAPI + SQLModel. `routers/` handles HTTP, `services/` owns
  business logic, and `crud/` owns persistence; no direct DB business logic in routers.
  Keep blocking I/O off the async event loop.
- Internal product workflows belong in `manager_frontend/` + `routers/manager_*`.
  SQLAdmin is removed; never reintroduce legacy `/admin` workflows.
- Public storefront UI, assets, tests and deployment belong in `mvnby/mvn-web`;
  it consumes this API over HTTP only.
- Active staff Telegram polling is deployed from `mvnby/mvn-telegram-bot`;
  this API owns business rules and the internal bot contract.
- Reuse `services/spec_normalizer.py`; add spec definitions/aliases to
  `services/spec_registry.py`, from which the normalizer derives `KEY_MAP`.
- About 700 lines or mixed responsibilities is a signal to assess cohesion.
  Split when needed for this task; propose unrelated refactors separately.
- Manager list endpoints require `limit <= 100`.

## Read by task

Use [docs/README.md](docs/README.md) to locate additional topics; it is a map,
not a checklist of documents to read. Open only the relevant procedure:

| Task | Required entry point |
| --- | --- |
| Multi-step planning, repeated failures, delegation or improving agent instructions | [Agent workflow](docs/agent-workflow.md), relevant section |
| Local setup, backend/Manager tests, imports/specs, leads or API client changes | [Development workflow](docs/development-workflow.md), relevant section |
| Commit, PR, CI or merge | [Git workflow](docs/git-workflow.md) |
| Production data operation | [Production data operations](docs/production-data-operations.md), then the matching runbook |
| Deployment / HA / database topology | [Deployment](docs/deployment.md) / [API HA](docs/api-ha-runbook.md), relevant procedure; production data gates also apply to mutations |
| Bot contract or runtime ownership | [Bot service boundary](docs/bot-service-boundary.md) |
| Storefront ownership or deployment | [Web service extraction](docs/web-service-extraction.md); UI work continues in `mvn-web` |

Dated audits and rollout plans describe their recorded scope; verify current
code and live state before treating them as present-day facts or authorization.

## Efficient execution

- Use scoped `rg --files` / `rg -n`, then bounded reads in the relevant domain.
  Skip dependencies, caches, build output, `outputs/`, `.codex-tmp/`, lockfiles,
  `openapi.json` and generated `manager_frontend/src/client/` in ordinary searches;
  inspect them when relevant. Do not scan sibling worktrees or old chats by default.
- Batch independent reads/checks and retain results. Repeat only after a relevant
  change, failure or unresolved concern; diagnose repeated failure before retrying.
- Use bounded waits for CI/deploy/agents and concise status changes. Do not reload
  unchanged logs or repeatedly wake the model to poll. Preserve required gates.
- Choose the least expensive adequate model/effort; honor explicit user choices.
  Standing delegation authorization covers safe, independent, in-scope work only
  when it saves total cost, including review. Keep small/coupled tasks with one agent;
  use the [delegation procedure](docs/agent-workflow.md#delegation-and-effort).
- Keep related implementation and validation together. For a necessary handoff,
  record decisions, changed files, checks and the next action, not the transcript.

## Verification and production gates

- Run checks appropriate to the changed behavior. Documentation-only edits need
  link/Markdown checks and review of moved instructions, not local application
  builds or database tests. Required CI still applies before merge.
- API route/operation ID/schema changes require OpenAPI and Manager client
  regeneration, a Manager build and changed generated artifacts in the commit;
  commands live in [verification](docs/development-workflow.md#verification-by-change).
- PostgreSQL tests require a separate physical DB per process/worker. Never use
  a production base URL; the base DB name must contain `test`. CI proves worker
  isolation before parallel suites; use [the test procedure](docs/development-workflow.md#backend-tests)
  before changing concurrency or starting broad local suites.
- Production runs from images, not a git checkout. Data operations start
  report-only/dry-run. Cleanup requires explicit authorization; do not execute
  backfills, provisioning or grants without the linked procedure's review gates.
- Tenant-scope backfill execution is retired after contract migration. Shared
  grants remain system-owned; an empty offer set never means share-all.
- Keep internal Patroni names/SSH aliases/paths `mvn-api` and `zakup` unchanged;
  `mvn-api-nl` and `mvn-api-by` are display names only.
- A deployment is successful only after `/api/health`,
  `/api/v1/products?limit=5` and `/api/v1/filters/config` smoke checks pass.
