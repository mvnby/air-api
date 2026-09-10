# Integration credential keyring rollout

Analytics and Google Drive credentials use one shared integration keyring. This
keyring is independent from `SECRET_KEY`: changing it does not change login or
JWT behavior, and the node-specific authentication keys remain untouched.

The secret-bearing setting is `INTEGRATION_CREDENTIAL_KEYRING_JSON`:

```json
{
  "active_key_id": "integration-YYYY-MM",
  "write_mode": "legacy",
  "keys": {
    "integration-YYYY-MM": "<shared random integration master key>"
  },
  "legacy_secret_keys": [
    "<current NL SECRET_KEY>",
    "<current BY SECRET_KEY>"
  ]
}
```

Key IDs use 1–64 ASCII letters, digits, `_`, or `-`. Integration master keys
must contain 32–256 UTF-8 bytes. Legacy keys must contain 16–4096 UTF-8 bytes.
Every key value must be unique. Runtime errors and migration output never print
key material.

Use the protected env synchronizer and pass JSON over stdin. It replaces only
`INTEGRATION_CREDENTIAL_KEYRING_JSON`, requires the production deployment lock,
and compares the reviewed `.env` SHA-256 before an atomic replacement. Never put
the JSON in a command argument, workflow input, log, or artifact.

## Expand

1. Create one shared integration master key and collect the current NL and BY
   `SECRET_KEY` values through protected storage. Do not rotate either auth key.
2. Before deploying the keyring-aware image, write the same JSON to both nodes
   with `write_mode=legacy`. The old image ignores the extra setting.
3. Deploy the tested immutable image through the normal Patroni release path.
   Each new runtime still writes the historical unprefixed format with its local
   `SECRET_KEY`, but can read historical rows from either node. The startup
   credential health check must report every analytics and Drive row readable,
   including disabled rows.

`write_mode=legacy` refuses to write when the local `SECRET_KEY` is absent from
`legacy_secret_keys`. This prevents a node from creating a row it cannot read
on its next request.

## Enable shared writes

Keep the same `active_key_id`, integration master key, and both legacy keys.
Change only `write_mode` to `active`.

1. Update and recreate the fenced standby first. Confirm its credential health
   check passes.
2. Drain the writable API runtime through the normal deployment procedure, then
   update and recreate it. Do not leave an old or legacy-writing runtime serving
   requests after this point.
3. Confirm both nodes run the same tested image and report all stored credentials
   readable.

An old image cannot read the versioned ciphertext produced in active mode. Once
active mode can persist a token, rollback must keep keyring-aware code and the
same integration key material.

## Review and rewrap

Hold the normal deployment lock for the plan/execute window and do not start a
release concurrently. Run the plan in the current primary app container:

```sh
python3 scripts/manage_integration_credential_rewrap.py plan
```

Planning starts a read-only database transaction. Review these fields:

- `ready=true` and an empty `blockers` list;
- the expected total number of rows across both domains;
- `unreadable=0` and `fingerprint_drift=0`, including disabled connections;
- each row's domain, database ID, tenant/storefront/provider scope, status,
  source, ciphertext SHA-256, and fingerprint SHA-256;
- the active key ID and exact `plan_digest`.

The output contains no decrypted credential or stored fingerprint. A ready plan
emits a signed, single-purpose `plan_token` and `reviewed_execute_command`. The
token expires after 15 minutes.

Execute only the exact command from the reviewed fresh plan. Execution refuses
a replica or read-only transaction, takes a transaction-scoped advisory lock,
locks every credential row, and recomputes the full plan. Any added, deleted, or
changed ciphertext/fingerprint makes the reviewed digest stale. All rewrapped
ciphertexts and fingerprints commit in one transaction; any error rolls the
whole transaction back.

Run a new plan after execution. It must report all rows as `active`, zero
`legacy`, zero `retained`, zero `unreadable`, zero `fingerprint_drift`, and
`complete=true`. Repeating the plan and execute flow at this state is a safe
zero-change operation.

## Contract

After the complete plan and credential health checks pass on both nodes, replace
the keyring JSON on both nodes with:

```json
{
  "active_key_id": "integration-YYYY-MM",
  "write_mode": "active",
  "keys": {
    "integration-YYYY-MM": "<same shared integration master key>"
  },
  "legacy_secret_keys": []
}
```

The normal release compares the desired integration setting with the running
API container even when the image digest is unchanged. A changed setting forces
activation through the inactive API slot; an inspection failure blocks release.

Recreate the fenced standby, verify health, then recreate the primary through
the normal release path and verify health again. Contract mode never falls back
to `SECRET_KEY` for credential decryption.

For a later integration-key rotation, add the new key to `keys`, make it active,
retain the previous integration key in `keys`, deploy both nodes, run the same
reviewed rewrap, then remove the retained key only after `complete=true` and
both node checks pass.
