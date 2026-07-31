# Order domain decomposition

**Goal:** turn the current Order implementation into explicit read models and
transactional commands without changing the Manager API or user workflows.

The starting point contains three oversized files:

- `services/order_service.py`: about 3,900 lines and mixed reads, writes,
  formatting, workflow rules and transaction control;
- `schemas.py`: about 4,500 lines with unrelated API domains;
- `manager_frontend/src/components/orders/OrderEditDrawer.vue`: about 4,200
  lines with all order workspaces and network state in one component.

Each release below must be independently testable and deployable. Do not mix a
behavior change with a file move.

## R1: Manager Order projections

Move Manager list/detail query composition and response mapping to
`OrderProjectionService`. Manager read routes call that service directly;
`OrderService` retains thin delegates for existing internal callers during the
transition.

Acceptance:

- response models and generated OpenAPI are unchanged;
- list/detail, pricing, mail and tenant-isolation tests pass;
- no commit or rollback is added;
- `OrderService` loses the moved mapping/query implementation.

Known transitional behavior: detail reads still call
`ensure_default_proposal(...)` to repair legacy orders that have no proposal.
R2 must move that repair behind a command boundary before projections can be
declared strictly read-only.

## R2: Commands and transaction boundary

Introduce focused command handlers for:

1. create/update order;
2. proposal lifecycle and line reconciliation;
3. work-stage lifecycle;
4. payments;
5. order deletion.

Domain helpers may flush but must not commit or rollback. The outer command
handler owns one transaction and returns the post-commit projection. Failure at
any point must roll back the order, customer changes, links and outbox events as
one unit. Add fault-injection tests at the final step of each command.

Deliver R2 as three independently deployable slices:

1. [x] proposal create/update/select commands;
2. [x] work-stage and payment commands;
3. [ ] order create/update/delete plus Lead qualification.

When a command participates in an explicit caller-owned unit of work, its local
boundary is a SAVEPOINT; ordinary HTTP commands own the root transaction.

## R3: Order and Lead schemas

Move Order/Lead DTOs into domain modules and re-export them from `schemas.py` so
existing imports and OpenAPI operation contracts remain stable. Complete one
domain at a time and verify generated client output after every move.

## R4: Manager Order workspace

Split `OrderEditDrawer.vue` along user-visible responsibilities:

- customer/object context;
- proposal and commercial lines;
- execution planning and installers;
- repair workflow;
- payments and bank receipts;
- documents, mail and attachments.

Shared network/draft state belongs in typed composables. The drawer remains the
orchestrator and should not duplicate section state. Every extraction requires
component tests plus a production build.

## Stop condition

This refactor is complete when no Order command commits inside a domain helper,
Manager read routes use projections, Order/Lead DTOs have domain ownership, and
the drawer is a small orchestrator rather than another monolith. Further file
movement without one of those measurable outcomes is out of scope.
