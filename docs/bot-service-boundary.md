# Telegram bot service boundary

The Telegram runtime is now an API-only client. It must not receive database,
object-storage, OCR, or backend application credentials.

## Ownership

- `bot_app/` owns aiogram polling, FSM adapter, handlers, keyboards, Telegram
  delivery, formatting, environment parsing, and the HTTP gateway.
- `/api/internal/bot/v1` owns staff authorization, business rules, persistence,
  file storage, OCR, catalog mutations, repair workflows, durable FSM state,
  and the single-active runtime lease.
- `api_contracts/bot.py` is the versioned transport contract. When the bot moves
  to its own repository, publish this contract as a small shared package or
  generate the client from `openapi.json`; do not copy backend services.

## Bot environment

Required for active polling:

- `BOT_TOKEN`
- `BOT_API_TOKEN`
- `BOT_API_BASE_URL`

Runtime controls:

- `BOT_ENABLED`
- `BOT_DROP_PENDING_UPDATES`
- `APP_ROLE`
- `BOT_API_TIMEOUT_SECONDS`
- `BOT_RUNTIME_LEASE_SECONDS`
- `BOT_RUNTIME_RENEW_SECONDS`
- `BOT_RUNTIME_RETRY_SECONDS`
- `PUBLIC_SITE_URL`

Production requires a stable HTTPS API origin. Blue-green slot hostnames are
rejected because the bot must survive API slot switches without reconfiguration.

## Deployment order

1. Deploy the backend migration and `/api/internal/bot/v1` endpoints.
2. Verify the bot bearer token against the API health endpoint.
3. Deploy the API-only bot runtime without `DATABASE_URL` or storage volumes.
4. Confirm one process owns `mvn:telegram_bot` and polling is healthy.
5. Only then remove the old bot container/image during repository extraction.

The runtime lease is short-lived and renewed through the API. Losing the lease
stops polling, preventing two bot instances from consuming updates concurrently.
