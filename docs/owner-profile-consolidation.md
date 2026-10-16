# Owner profile consolidation

The manual **Consolidate Owner Profile** workflow performs one fixed operation:
retire StaffUser `1` into the already bound platform owner, StaffUser `4`.
It runs only after the profile release and migration chain through
`t1162telegram01` (including `t1162profile01`) are deployed to both API nodes.
There is no arbitrary account, host or command input.

## Reviewed result

The canonical owner keeps ID `4`, its exact login and password hash, auth version,
owner membership, catalog grants and all existing business/integration links.
Existing web sessions and connector grants remain valid for the same principal.
The personal display name, Telegram identity and installer link move from `1`;
phone, email and rate are copied only into empty destination fields. An existing
source avatar moves only when the destination has none; two avatars block for
an explicit choice. Telegram notification consent is the intersection of both
accounts, so consolidation never reverses an opt-out.

The source account becomes inactive, its auth version increments, its membership
is disabled and `merged_into_staff_user_id` records `4`. Unique Telegram and
installer links are released before reassignment within the same transaction.
Historical foreign keys, orders, audit entries and notification queues are not
rewritten. Authentication never follows the merge reference. Queued notification
delivery may resolve that reference only through its separate recipient checks.

The existing source Telegram binding receives a verification timestamp through
the explicitly reviewed consolidation, recorded as
`method=reviewed_owner_consolidation`; this is not a claim that a live Telegram
challenge was completed. Later linking uses the normal verified profile flow.

## Plan and execution

1. Complete the backend release, exact main CI and deployment smoke checks.
2. Run **Consolidate Owner Profile** from that exact reviewed `main` SHA with
   `operation=plan`, `apply=false`. Review the sanitized artifact: fixed source
   `1`, target `4`, `ready=true`, no blockers, expected source references and
   `preserve_target_auth_version=true`.
3. New unexplained source references block the operation, including new active
   work or integrations. Resolve their disposition explicitly; do not delete or
   reassign them merely to satisfy the plan. Both avatars also block. The plan
   digests actual profile, credential, membership, installer and avatar state;
   any intervening change requires a fresh review.
4. Run `operation=execute`, `apply=true`, using the exact reviewed
   `reviewed_plan_digest` and the same main SHA. No password secret is required:
   the canonical credential is preserved. The controller obtains a fresh signed
   token internally and delivers it through protected stdin.
5. Review the completed sanitized artifact and both-node proof. Verify the owner
   profile, preserved existing session/connector access, new Telegram identity,
   installer association and rejection of the former source account.

The workflow shares the `production-release` lock and protected `production-api`
environment. It reuses pinned SSH configuration, immutable image/provenance
checks for the exact reviewed SHA, verified Patroni topology, and per-node
deployment locks. Execution requires PostgreSQL and the existing owner-operation
advisory lock. Row locks follow auth state, company, ordered staff rows,
memberships, installer and avatar; locked state is refreshed before comparing
the digest. Changes and the audit receipt commit together. A new plan after
successful consolidation is a no-op; replaying an old plan is stale.

Protected remote calls use the reviewed deployment-lock helper's `exec-wait`:
it waits at most 30 seconds for the same exclusive lock before running the
command. This handles the lock contention confirmed during the October 2026
read-only runtime probes. The command itself is not retried, and helper source,
ownership, file safety, topology and immutable-image checks remain mandatory.

Failure artifacts retain a fixed `failure_phase` and, where available, an
allowlisted `diagnostic_code` plus integer `remote_status`. For `primary_runtime`:

| Diagnostic | Meaning |
| --- | --- |
| `local_helper_unavailable` / `local_helper_unreviewed` | The controller cannot read or trust its checked-out helper. |
| `remote_lock_busy` | The helper reported the exact reviewed errno-11 contention error after its bounded wait. |
| `remote_helper_unreviewed` / `remote_lock_unsafe` | A remote helper or lock safety check failed. |
| `remote_ssh_failed` / `remote_transport_unavailable` | SSH returned 255 or the controller could not start the transport. |
| `remote_command_failed` | Other remote failure; status alone does not prove lock contention. |
| `runtime_response_invalid` / `runtime_image_not_immutable` | The runtime response failed strict parsing or immutable-image validation. |

These codes contain no remote stdout/stderr, command, exception text or
credentials. Unknown failures remain unclassified; diagnose the stated gate
before another protected run instead of bypassing it.

Backend releases explicitly emit SLSA v1 provenance and verify the exact source,
revision and immutable image before deployment, using the same verifier as this
operation. An early failure produces a minimal sanitized artifact with a fixed
`failure_phase` code, such as `reviewed_image` or `primary_plan_transport`;
exception messages and remote responses remain private. Diagnose that phase
before retrying; do not bypass a failed image or topology check.

Both-node recovery proof compares a fresh challenge-bound runtime credential
binding only inside the protected controller. Signed tokens, bindings and
challenges are removed before artifacts, summaries or console output. Do not
run ad hoc diagnostics that print raw verification JSON or recovery bindings.
The in-image verification command is a private transport for the controller,
not a user-facing report command.

## Recovery and tests

The owner remains in `staff_shadow`; retained runtime emergency credentials are
not removed or changed. Existing **Cut Over Legacy Owner** rollback now accepts
the unified owner/installer profile with a verified Telegram binding. Rollback
restores legacy authentication and revokes staff sessions; it does not split the
person again or reverse historical links. The normal reviewed cutover can return
that same canonical account to staff authentication.

If execution or subsequent proof fails, the consolidation controller uses the
existing auth-only rollback procedure under a fresh plan and unchanged topology
and image gates. If those gates cannot be proved, recovery fails closed and
requires operator diagnosis; there is no blind retry or data reversal.

Local SQLite tests cover credential preservation, rejected source JWTs, preserved
owner JWT/connector authorization, new Telegram authorization, avatar transfer,
opt-outs, stale plans, audit/no-op behavior and transaction rollback. PostgreSQL
integration tests additionally prove unique-key transfer and concurrent operation
fencing. Required CI must run those tests before release. The ordinary profile
and Telegram tests cover later user-initiated linking and credential rotation.

Related: [legacy owner recovery](legacy-owner-cutover.md),
[production data operations](production-data-operations.md),
[users and access](users-and-access.md).
