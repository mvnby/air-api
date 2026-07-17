# Telegram bot service extraction

## Target boundary

The Telegram runtime is a client of the versioned MVN internal API. It owns
Telegram updates, dialogs, buttons, formatting and FSM state. It must not own
CRM, catalog, staff, repair, warranty, OCR or attachment business logic.

The backend remains the only owner of the main PostgreSQL database. Bot
requests authenticate with a dedicated service credential; the API then
authorizes the Telegram user for each use case.

## Migration sequence

1. Establish `/api/internal/bot/v1`, service authentication and the typed HTTP
   gateway without changing production bot behavior.
2. Move read-only staff, catalog, selection, calendar and task scenarios.
3. Move idempotent order/task writes. Never dual-write through local and HTTP
   paths.
4. Move attachment, OCR, repair and warranty scenarios.
5. Move FSM/runtime ownership, remove database access and publish a dedicated
   bot image.
6. Move the autonomous bot into the private `mvnby/mvn-telegram-bot` repository
   and deploy it independently on the Netherlands node.

Steps 1-6 are complete. The monolith retains the internal API and a disabled
`legacy-bot` rollback profile; it no longer deploys or activates Telegram
polling as part of API/Patroni role changes.

### Staff access cutover

Telegram handlers resolve staff identity and roles through one bot-owned
provider. `BOT_ACCESS_BACKEND=database` is the explicit rollback mode during
the rollout. Set `BOT_ACCESS_BACKEND=api` only after deploying the same strong
`BOT_API_TOKEN` to the API and bot runtimes. API mode performs a startup health
check and never silently falls back to the database after an HTTP failure.

Production must use `https://api.mvn.by/api/internal/bot/v1`. Blue/green service
names (`app-blue` and `app-green`) change on every deployment and the inactive
slot is removed, so they are not valid service-discovery addresses for the bot.
Settings reject API mode without a token, without HTTPS in production, or with
a slot-local hostname.

The temporary database provider is removed after API mode has been verified in
production. Catalog, orders, repair and FSM database paths remain separate
migration slices; this switch covers staff authorization only.

### Catalog search slice

The staff search flow, inline product search, product details and the
forwardable client text use `/api/internal/bot/v1/catalog/*`. The API repeats
staff authorization for the Telegram identity and returns a deliberately small
product-card projection instead of exposing a generic manager or public catalog
contract.

Search cards are read-only. Price changes and product deletion stay in the
Manager application and are not exposed by the autonomous bot API. Relative
media paths are resolved through the public API origin; the bot does not depend
on the monolith's local media filesystem.

The legacy step-by-step selection and the current multi-room selection remain
separate migration slices. They must be replaced by one backend-orchestrated
selection use case rather than many remote product queries.

### Read-only task slice

The staff task list uses `POST /api/internal/bot/v1/tasks/my`. Telegram identity
and pagination stay in the JSON body so staff identifiers do not enter access
log URLs. The API authorizes the identity once, then queries by the verified
legacy installer mapping.

Scheduled work stages and legacy installer assignments are merged, ordered by
start time and deduplicated by order. A work stage is the source of truth when
both representations exist; unrelated legacy assignments are still returned.
Task status changes and reports remain a separate write slice and continue to
use the existing local path until idempotent API commands are introduced.

## Scope guardrails

- Freeze new bot product features while a scenario is being migrated.
- Use use-case endpoints instead of exposing generic database CRUD.
- Keep business rules in backend services; do not copy them into the bot.
- Cut over one vertical scenario at a time and delete its local path after
  verification.
- Do not add an event bus or a generic microservice platform for this split.

## Definition of done

- `bot_app/` has no imports from `core.database`, `models`, `crud` or backend
  `services`.
- The bot container has no main-database credential or network access.
- Repeated Telegram callbacks cannot create duplicate writes.
- API downtime produces a bounded, staff-readable bot error.
- Stopping the bot has no effect on the API, web or manager application.
- HA role changes leave exactly one active Telegram polling runtime.
- Contract and smoke tests cover every retained staff workflow.
