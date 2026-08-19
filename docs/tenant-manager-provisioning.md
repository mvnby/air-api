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
