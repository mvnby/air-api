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
6. Move the autonomous bot into a separate repository only after the boundary
   checks below pass.

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
