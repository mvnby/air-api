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

## Existing orders

The `/api/internal/bot/v1/order-desk/{order_id}` operations use the selected
staff company and storefront. The desk returns saved proposal prices, quantities,
planning fields and allowed actions. A command supplies the displayed order revision
and an actor-scoped idempotency key. A concurrent edit produces a conflict before the
command writes. Reading older orders leaves their proposal grouping intact.

The client quote projects one proposal and its services. A native commercial draft
also binds one saved proposal and an active issuer template. Drafts and private
PDF previews use the document service. Telegram prepares the share chooser for
client text and delivers a requested PDF only to the initiating manager.

Any writable manager with access to the order can record its equipment status and
received payments. Supplier offers and line-level reservation requests follow the
same supply permissions as Manager. Payment history and balances use the canonical
order currency and workflow rules. Official document issuance reserves a number for
one confirmed draft and supports retrying that document after a rendering failure.
Individual buyers can receive a retail receipt draft bound to a saved proposal and the seller's public offer.
The private PDF endpoint returns the stored artifact for that document and order.

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

## Deployment ownership

The active polling runtime is deployed from the private `mvnby/mvn-telegram-bot`
repository on the Netherlands node. The monolith deploys only API services.
Its former `bot` Compose service is retained under the explicit `legacy-bot`
profile for a time-bounded emergency rollback and is fenced by the Patroni role
agent on both database roles.

Cutover and rollback must keep this order:

1. Verify the external container and bot API contract while `BOT_ENABLED=false`.
2. Deploy the monolith release that fences the legacy polling container.
3. Enable polling in the external service and confirm the runtime lease.
4. To roll back, disable external polling first, then explicitly start the
   `legacy-bot` profile with `LEGACY_BOT_ENABLED=true`.

The runtime lease is short-lived and renewed through the API. Losing the lease
stops polling, preventing two bot instances from consuming updates concurrently.
