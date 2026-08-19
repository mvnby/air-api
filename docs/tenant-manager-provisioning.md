# Tenant manager provisioning

`scripts/provision_tenant_manager.py` is the reviewed production path for a
new, password-authenticated manager of an existing non-system tenant. A
creation execute requires one secret input source; a later idempotent no-op
does not. It does
not create tenants or storefronts, and it never prints or stores a clear-text
password outside the process memory needed to create the bcrypt hash.

It resolves the exact tenant and storefront, then fails closed unless the
tenant is active and non-system and its requested storefront is active and the
default storefront. It rejects an existing username or phone unless both refer
to the same already-compliant manager identity. A compliant identity has
exactly one membership: active `manager` in the requested tenant; its global
role list is exactly `manager`, it has no legacy installer link, and it has no
other tenant membership. An existing identity must also have no Telegram ID or
Telegram username: a globally linked Telegram manager could receive bot-admin
notifications outside the requested tenant scope.

Run this only after the release containing the command is deployed and the
target's migration head is verified. The app container must have the same
`SECRET_KEY` used for the plan and execute calls; plans expire after 15 minutes.
Use a privileged, audited production shell and the running application image.

First, make a read-only plan (no password source is accepted):

```sh
docker compose -f /opt/air-api/docker-compose.prod.yml exec -T app \
  python3 scripts/provision_tenant_manager.py plan \
  --tenant-slug polotsk --storefront-slug main \
  --display-name 'Андрей' --username '<reviewed-login>' \
  --phone +375297146293
```

Review `ready`, `blockers`, `current`, and `changes`. Only if `ready` is true,
run the emitted `reviewed_execute_command`. It intentionally ends in
`--password-stdin`; pass a generated password without putting it in shell
history, a command line, CI logs, or a committed file. The command accepts a
single trailing newline from stdin or a private password file. A password must
be at least 12 characters; use a password-manager generated value.

For a private file, the file must be a regular `0400` or `0600` UTF-8 file and should be
removed securely by the operator after use. `--password-env` is supported for
an already-injected secret, but is less preferable because environment values
can be exposed by process inspection or diagnostics.

The execute transaction is all-or-nothing. Re-running after a successful
creation is a safe no-op and does not need or reset the password. A changed target,
new collision, or stale plan token blocks before a write. Do not use this tool
to convert an existing employee with other memberships or elevated privileges:
review and remediate that identity separately.

## Production GitHub workflow

Use **Provision Tenant Manager** for production instead of a local SSH shell.
The workflow is manual, accepts only an exact reviewed `main` SHA, and is gated
by the `production-api` environment. It verifies the complete two-node Patroni
topology through repository-pinned SSH host keys, requires exactly one healthy
primary, discovers the active `app-blue`/`app-green` service from
`.active-api-slot`, and pins its exact container ID and immutable image for the
whole operation. A concurrent deployment or slot change therefore stops the
operation instead of redirecting it to another container. Immediately before
an execute, the controller proves the complete topology and synchronous
replication a second time. The workflow shares the `production-release`
concurrency group and every remote runtime command takes the same attested
per-project `.deploy.lock` used by deployment. It fails instead of waiting on a
busy lock, so there is no cross-workflow deadlock. It has no input for an
arbitrary host, project path, container, script, or remote command.

The `plan` operation is read-only. Its three-day artifact deliberately removes
the signed plan token and emitted execute command; review `ready`, `blockers`,
`current`, `changes`, `target`, the primary node, and immutable runtime image.
The stable `result.plan_digest` is the only value copied into the execute form.
A blocked plan still uploads this sanitized artifact for diagnosis, while the
workflow remains visibly failed.

The `execute` operation requires all of the following:

- the same exact target fields;
- `apply=true`;
- the reviewed 64-character `plan_digest`;
- the static, short-lived `TENANT_MANAGER_ONE_TIME_PASSWORD` secret in the
  `production-api` GitHub environment.

Execute creates another fresh plan on the current primary and compares its
digest with the reviewed digest. The fresh signed token and password travel
together over stdin to the exact tenant-manager CLI; neither is placed in a
command argument, container environment, artifact, or workflow summary.
Delete the temporary GitHub secret immediately after the execute run, whether
the run succeeds or fails. Do not create per-manager or dynamically indexed
secret names: one protected, documented short-lived secret keeps the
operational boundary reviewable.

### One-time Polotsk sequence for Andrey

Wait until the release containing this workflow and the
`--execution-json-stdin` CLI option is deployed. Then record the exact current
`main` SHA and run **Provision Tenant Manager** with:

```text
operation: plan
apply: false
tenant_slug: polotsk
storefront_slug: main
display_name: Андрей
username: andrey.polotsk
phone: +375297146293
reviewed_plan_digest: <empty>
confirm_sha: <exact current main SHA>
```

Download the sanitized plan artifact. Continue only when `ready=true`,
`blockers=[]`, the target is exact, and `changes` contains only
`create_staff_user` and `create_active_manager_membership` (or is empty for an
already compliant idempotent rerun).

If `changes=[]`, stop here: the existing manager already satisfies the exact
tenant boundary. Do not create the temporary password secret and do not run
execute. For the current `andrey.polotsk` production identity, this read-only
no-op plan is the expected path.

Only when `changes` is the exact ordered creation pair should the following
password and execute steps be used.

Generate and retain the initial password in an owner-only file outside every
repository. These commands do not print it or put it in shell history:

```sh
umask 077
mkdir -p "$HOME/.config/mvn-secrets"
password_file="$HOME/.config/mvn-secrets/andrey.polotsk.password"
openssl rand -base64 24 > "${password_file}"
chmod 600 "${password_file}"
gh secret set TENANT_MANAGER_ONE_TIME_PASSWORD \
  --repo mvnby/air-api --env production-api < "${password_file}"
```

Keep that local file only until the credential has been transferred to Andrey
through an approved private channel or saved in the chosen password manager.
Never display it in a terminal, issue, task, PR, workflow input, or chat.

Run the execute form after reviewing the plan:

```text
operation: execute
apply: true
tenant_slug: polotsk
storefront_slug: main
display_name: Андрей
username: andrey.polotsk
phone: +375297146293
reviewed_plan_digest: <result.plan_digest from the reviewed artifact>
confirm_sha: <the same still-current main SHA>
```

Immediately remove the GitHub copy, including after a failed run:

```sh
gh secret delete TENANT_MANAGER_ONE_TIME_PASSWORD \
  --repo mvnby/air-api --env production-api
```

Review the execute artifact for `ready=true`, `changed=true` (or the expected
idempotent `changed=false`), the exact target, and assigned staff/membership
IDs. Then verify an Andrey login in a fresh browser session and confirm that
the manager UI is limited to tenant `polotsk` and storefront `main`.
