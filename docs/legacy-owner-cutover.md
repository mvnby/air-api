# Legacy owner shadow cutover

`Cut Over Legacy Owner` is the only production path for moving the canonical
runtime-env owner into the bounded `StaffUser` identity. It has no target,
username, host, command, or path input: its target is always the
active system tenant `mvn` and default storefront `main`.

The workflow can be started only from an exact reviewed `main` SHA in the
`production-api` environment. It shares the normal `production-release` lock,
uses repository-pinned SSH host keys, proves one healthy Patroni primary, and
executes only `scripts/cutover_legacy_owner.py` inside an exact active,
immutable application container. A plan artifact is short-lived and removes
the signed replay token before upload.

Before any plan or mutation, the controller resolves the immutable registry
digest currently tagged `backend:<reviewed main SHA>`, then verifies that its
BuildKit provenance names exactly this repository and revision. It refuses
unless both active Patroni application containers run that exact digest and
expose the reviewed CLI capability. During both staff-shadow and rollback proof, each
container returns a domain-separated HMAC binding of its retained local legacy runtime
credential. The controller compares the bindings only in memory, then removes
them before every artifact and summary; a different local `ADMIN_*` value on
either node blocks the operation.

1. Run `operation=plan`, `plan_for=cutover`, `apply=false`, and record the
   exact `plan_digest`. To review a manual rollback instead, use
   `operation=plan`, `plan_for=rollback`; a rollback needs its own fresh,
   operation-bound digest.
2. Review the sanitized artifact: target must be `mvn/main`, blockers empty,
   runtime immutable, and no unrelated tenant or membership may appear.
3. Store the new staff password in the static, short-lived
   `LEGACY_OWNER_ONE_TIME_PASSWORD` secret in the `production-api` GitHub
   environment. Run `operation=execute`, `apply=true`, with that digest and the
   same exact current `main` SHA. The password must satisfy the shared minimum
   of 9 characters and bcrypt maximum of 72 UTF-8 bytes.
4. The workflow re-plans and re-proves topology before mutation. After a
   successful shadow transition it invokes read-only `verify` inside the
   active container on both Patroni nodes. The retained runtime password remains
   inside those containers. Verification proves the exact bound system owner,
   membership, a bcrypt match against the one-time credential supplied again
   over stdin, self-service availability, and rejected legacy
   JWT and Google callback paths.
5. If either proof fails, the controller obtains a fresh rollback-bound plan,
   returns the state to `legacy` on the primary, and proves that rollback before
   failing the run. Manual `rollback` has the same reviewed-digest guard.
   Its artifact includes the same two-node legacy proof. In that proof,
   `credential_matches=true` means each container has a present, canonical
   local `ADMIN_*` credential; it is not an assertion of current policy
   compliance or that this
   legacy password still equals the retained StaffUser bcrypt hash.

The execute credential is masked before use and passes from the protected
workflow to the fixed controller, exact primary container, and dual-node
read-only proof only over stdin. It is never a workflow input, command argument,
container environment variable, artifact, summary, log, or audit field. Delete
the temporary GitHub environment secret immediately after execute, whether the
run succeeds or fails.

Create that static secret only after the compatible workflow is deployed:
repository **Settings → Environments → production-api → Environment secrets →
Add secret**, with the exact name `LEGACY_OWNER_ONE_TIME_PASSWORD`. Keep the
value in the owner's password manager and never copy it into a task, PR, issue,
workflow form, or chat. Tell the operator only that the secret is installed.

This is deliberately only a shadow cutover. It does **not** remove, rename, or
reset `ADMIN_USERNAME` or `ADMIN_PASSWORD`; the retained runtime password is a
rollback credential and is ignored for normal login in `staff_shadow`. No
password, bcrypt hash, token,
or secret is written to a summary or artifact. Removing the legacy runtime
environment is a later contraction operation after an approved soak and a
separate two-node recovery plan.
