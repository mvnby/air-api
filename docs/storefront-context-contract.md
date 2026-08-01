# Trusted public storefront request contract

## Purpose and trust boundary

Public catalog reads, Lead creation and checkout must get their storefront from
the server runtime that served the website. Browser-provided tenant or
storefront IDs, `Origin`, `X-Forwarded-Host` and unsigned storefront headers are
never authority.

The canonical MVN website may temporarily call the ordinary API host without a
signature. A non-canonical storefront is accepted only through a complete
short-lived HMAC envelope produced by its trusted SSR or same-origin proxy.

## Required signed headers

The trusted runtime sends exactly one value for each header:

- `X-MVN-Storefront-Key-Id`: configured runtime key ID, for example
  `mvn-web-2026-08`;
- `X-MVN-Storefront-Host`: the public storefront hostname, for example
  `orsha.mvn.by`;
- `X-MVN-Storefront-Timestamp`: canonical Unix seconds (`0` or a decimal value
  with no sign, whitespace or leading zeroes);
- `X-MVN-Storefront-Signature`: `v2=<64 lowercase SHA-256 hex characters>`.

Every signed protected write also sends exactly one canonical
`Idempotency-Key`. Signed reads must not send that header. Duplicate,
comma-combined, whitespace-padded or otherwise non-canonical values fail at the
outer gateway.

Any incomplete set, duplicate value, unknown `X-MVN-Storefront-*` header,
unknown key ID or malformed value returns `401`. The browser-facing proxy must
strip all incoming headers with that prefix before creating its own envelope.
Incomplete, duplicate and unknown sets are rejected at the outer ASGI boundary
without reading or parsing the request body.
These infrastructure credentials are deliberately omitted from the generated
OpenAPI/browser client; this document is the signing contract for trusted
server runtimes.

## Canonical v2 message

The signature is HMAC-SHA256 over these eight fields in this exact order:

```text
v2
<timestamp>
<HTTP method>
<raw path and optional raw query>
<upstream API hostname>
<storefront hostname>
<lowercase SHA-256 hex of the exact request body>
<lowercase SHA-256 hex of the canonical Idempotency-Key, or empty for reads>
```

There is one ASCII LF byte (`0x0a`) between fields and no trailing newline.
The complete byte sequence is signed with the UTF-8 secret.

`v2` is the only version accepted for writes. The historical seven-field `v1`
message did not bind `Idempotency-Key` and is therefore never accepted for
`POST`, `PUT`, `PATCH` or `DELETE`. An emergency compatibility verifier for
`GET`, `HEAD` and `OPTIONS` exists behind
`STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS=false`; when enabled it accepts the
historical seven fields ending at the body digest. The flag requires a complete
primary signing-key pair. It stays false during normal operation and cannot
weaken write authentication.

Canonicalization rules:

1. `timestamp` is canonical base-10 Unix seconds.
2. The HTTP method is uppercased as ASCII.
3. The target starts with `/`. Append `?` and the raw query bytes only when the
   query is non-empty. Do not decode, reorder or re-encode query parameters.
   The fragment is never present. CR or LF is invalid.
4. The upstream API hostname comes from the actual HTTP `Host`/`:authority`
   received by air-api. It is lowercased, converted to IDNA ASCII and stripped
   of a port and trailing dot. It must also be in
   `STOREFRONT_CONTEXT_API_HOSTS` (the production default includes
   `api.mvn.by` and loopback smoke-check hosts).
5. The storefront hostname uses the same lowercase IDNA/no-port/no-trailing-dot
   normalization.
6. Hash the exact transmitted body bytes, before JSON/form parsing. The empty
   body digest is
   `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
7. For a protected write, validate the exact `Idempotency-Key` value and append
   its lowercase SHA-256 digest. For `GET`, `HEAD` and `OPTIONS`, append an
   empty eighth field and omit the header. A captured body/signature cannot be
   paired with a new key.

For a structurally complete envelope, air-api reads the exact bounded body,
checks the API host, key ID, timestamp, raw target, storefront host, digest and
HMAC, and only then calls FastAPI. The verified normalized storefront hostname
is carried inward as an immutable ASGI scope marker; route dependencies never
re-authenticate from raw headers. The body is replayed unchanged for JSON or
multipart parsing. This buffer is hard-limited by
`STOREFRONT_CONTEXT_MAX_BODY_BYTES` (20 MiB by default, matching the current API
ingress limit); an oversized signed request returns `413` without reaching the
endpoint. A valid signature with malformed JSON can therefore return `422`,
while a partial or forged envelope with the same bytes returns `401` before the
parser or database dependency runs.

Unsigned canonical protected writes use the same 20 MiB ceiling without
buffering: a canonical `Content-Length` is checked first, then an outer receive
wrapper counts streamed chunks and raises `413` before FastAPI parsing or
dependencies. Reads, intentionally open routes and CORS preflight keep their
existing path.

Installation-estimate and repair-diagnostic attachments also enforce an
18 MiB aggregate file-content limit inside the API. This protects direct
canonical traffic that does not pass through the signed-body buffer and leaves
approximately 2 MiB for multipart boundaries and form fields under the default
20 MiB gateway envelope. Each image remains independently limited to 10 MiB.

Changing method, raw path, raw query, upstream API host, storefront host, any
body byte or the idempotency key invalidates the signature.

## Runtime keyring and rotation

Keys exist only in runtime secret configuration:

- `STOREFRONT_CONTEXT_SIGNING_KEY_ID` and
  `STOREFRONT_CONTEXT_SIGNING_SECRET` are the primary pair;
- `STOREFRONT_CONTEXT_PREVIOUS_SIGNING_KEY_ID` and
  `STOREFRONT_CONTEXT_PREVIOUS_SIGNING_SECRET` are the optional rotation pair;
- `STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS` is a default-off, read-only
  rollback switch; it never permits a v1 write;
- every secret contains at least 32 UTF-8 bytes;
- key IDs are a case-sensitive allowlist and are never supplied by the
  database or a public payload.

The API selects one allowed key by ID and compares the HMAC in constant time.
The previous key is accepted only while a complete primary pair is configured.
Clearing the primary pair disables every signed request, including a request
using a stale previous key.

Zero-downtime rotation:

1. Add the new pair as primary and keep the old pair as previous.
2. Deploy air-api, then switch each trusted storefront runtime to the new key.
3. Run read, Lead and Order canaries with the new key.
4. Wait longer than `STOREFRONT_CONTEXT_MAX_AGE_SECONDS`.
5. Remove the previous pair.

Never reuse `SECRET_KEY`, bot credentials or a Cloudflare token.

The current primary/previous slots form one MVN-operated platform keyring: a
holder can sign for any active storefront domain. It is therefore suitable only
for runtimes controlled by MVN. Before an external tenant controls its own
runtime, introduce per-runtime credentials bound to an explicit storefront-host
allowlist or keep signing in the centrally managed MVN edge.

## Replay boundary

`STOREFRONT_CONTEXT_MAX_AGE_SECONDS` is constrained to 30–900 seconds. Requests
outside the past/future window fail closed. The body and idempotency-key digests
prevent changing a captured write.

There is deliberately no in-memory nonce cache: it would allow replay against
another HA replica. Until a shared PostgreSQL/Redis nonce ledger is introduced,
an identical captured request can be replayed within the accepted time window.
Its signed idempotency key is immutable, so the domain receipt replays the
original result instead of creating another resource. Keep the window short,
use TLS, never log the envelope, and do not treat this HMAC as user
authentication.

## Public write idempotency

`POST /api/v1/orders` and every public Lead intake (`contact`,
`product-availability`, `installation-estimate`, and `repair-diagnostic`) use
the `Idempotency-Key` header. The accepted value is 16–128 characters from
`A-Z`, `a-z`, `0-9`, `.`, `_`, `:`, and `-`.

The API hashes the key and validated logical request content before storage.
Receipts are unique by server-resolved tenant, storefront, command, and key;
they never store the key, raw body, form fields, filenames, or other request
PII. Multipart fingerprints use normalized form fields and each attachment's
content hash, MIME type, size, field, and position. Regenerating a multipart
boundary therefore does not change the fingerprint.

The receipt and business mutation commit in one PostgreSQL transaction. A
concurrent request on another replica waits at the unique insert, then either
replays the original successful status/body or takes ownership after a failed
transaction. The wait is bounded by a 3-second PostgreSQL `lock_timeout`; a
busy request returns `503` with `Retry-After: 1`. Reusing a key with different
logical content returns `409`.

Successful receipts are retained for at least 30 days. `expires_at` is indexed
and the scheduler deletes expired rows in bounded, lock-safe hourly batches. Once
cleanup removes a receipt, the same key may create a new command; clients must
not assume replay protection beyond the documented 30-day horizon.

Signed storefront writes without a bound `Idempotency-Key` fail HMAC
authentication with `401` before parsing or mutation. During the
canonical MVN transition only, an unsigned request accepted under
`STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=false` receives an ephemeral
server-generated key. This fallback preserves legacy availability but cannot
deduplicate a client retry. Installation estimate keeps its pre-existing rule:
the header is required even for unsigned canonical traffic. Before enabling
required signatures, `mvn-web` must
generate one key per user submission, retain it across transport retries, and
send it for checkout, contact, availability, and repair; installation estimate
already does so. Remove the unsigned fallback only together with the canonical
signed-traffic rollout.

The coordinated `mvn-web` release must also lower installation's current
30 MiB client aggregate to 18 MiB and add the same 18 MiB aggregate check to
repair. The API limit is authoritative; browser checks exist only to fail early
with a useful message.

Repair intake persists one deduplicated `repair.diagnostic_ai_requested.v1`
job in the same transaction as the order and receipt. The HA scheduler leases
and recovers that durable job. A token-fenced heartbeat renews a live lease,
then releases the database session before private-object reads, OCR, or the LLM
call. The final transaction locks and verifies the same live event lease first,
then reloads and locks the tenant-scoped Order. It applies only AI-owned fields
whose values have not changed since the immutable snapshot, preserving
concurrent Manager edits and every non-AI metadata field. A terminal latest
state is never overwritten by a stale result. A stale replica therefore cannot
write after another replica reclaims the event.

The provider payload contains only the selected symptom and timing, validated
conditional answers, validated check labels, and recognized equipment fields.
It excludes the customer's name, phone, address, and free comment. DeepSeek
failures use a typed retry contract: network errors, `429`, and `5xx` retry;
permanent `4xx` responses such as `401`/`403` terminate the job. Exhausting all
attempts atomically marks the event dead and the Order diagnosis failed. An
API-process crash after commit cannot leave the order permanently pending, and
a retry does not enqueue a second job.

The repair `payload` form field is capped at 16 KiB before JSON decoding and is
validated with a strict per-symptom allowlist derived from the storefront
question config. Unknown fields, wrong conditional keys or option values,
duplicate checks, incompatible `nothing_checked`, excessive counts, and an
invalid or overlong error code are rejected before database or provider work.

Installation and repair photos are private `ServiceAttachment` objects linked
to their Order and exposed to Manager only through tenant-scoped attachment
APIs. Repair Order metadata stores only the attachment ID and technical file
facts; it contains no public URL, bucket, provider, or storage key. Repair AI
may read a nameplate only when the active Order link category, attachment
source, exact source purpose, tenant, storefront, and Order all match.

Both intake families write variants scoped by tenant, storefront, the
idempotency-key hash, and a per-attempt nonce (`public-installation-*` and
`public-repair-*`). They deliberately do not delete objects immediately after
an exception: the transaction may already have committed while its
acknowledgement was lost, so compensation could destroy a valid attachment.
Instead, one durable HA-safe inventory reconciler scans local or S3 storage in
bounded pages, examines at most the configured limit, and deletes only objects
that are still unreferenced after a 24-hour grace period. Its cursor and lease
are stored in PostgreSQL, lease comparisons and advancement use the database
clock, and cursor advancement occurs only after the whole page succeeds.
Deletion is idempotent, so a crash retries the same page safely; reaching the
end wraps the cursor for the next inventory pass.

Exact `mvn-web` signer delta: generate and retain the submission key first,
send it as the sole `Idempotency-Key` header, SHA-256 the exact canonical key
string, and append that 64-character lowercase digest after the body digest in
the v2 message. For `GET`/`HEAD`/`OPTIONS`, omit the header and append an empty
final field. The browser never supplies signing headers. A same-origin proxy
may receive the app's submission key, but it must validate one canonical value,
remove any raw inbound `Idempotency-Key`, set exactly one outbound value, and
sign that value. A proxy-generated key must be retained across retries rather
than regenerated per attempt.

Reference delta for a Node/TypeScript signer (after rejecting duplicate raw
headers and normalizing the method, target and hosts exactly as above):

```ts
const readMethod = method === "GET" || method === "HEAD" || method === "OPTIONS";
let canonicalKey: string | null = null;
if (readMethod) {
  if (submissionKey !== undefined) {
    throw new Error("Idempotency-Key is forbidden on signed reads");
  }
} else {
  if (
    typeof submissionKey !== "string" ||
    submissionKey.length < 16 ||
    submissionKey.length > 128 ||
    !/^[A-Za-z0-9._:-]+$/.test(submissionKey)
  ) {
    throw new Error("Invalid Idempotency-Key");
  }
  canonicalKey = submissionKey;
}
const idempotencyKeySha256 = canonicalKey === null
  ? ""
  : createHash("sha256").update(canonicalKey, "ascii").digest("hex");
const canonicalMessage = [
  "v2",
  String(timestamp),
  method,
  rawPathAndQuery,
  apiHostname,
  storefrontHostname,
  bodySha256,
  idempotencyKeySha256,
].join("\n");

outboundHeaders.delete("Idempotency-Key");
if (canonicalKey !== null) outboundHeaders.set("Idempotency-Key", canonicalKey);
```

The eighth array element is mandatory even when empty. There is no newline
after it. Sign the resulting UTF-8 bytes with the existing HMAC-SHA256 secret
and send the `v2=<lowercase hex>` wire format.

## Resolution and compatibility

- No signing headers, an allowed ordinary API host and
  `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=false`: resolve only canonical
  active `mvn/main`; `Host`, `Origin` or forwarded browser headers cannot select
  another storefront.
- No signing headers on an unapproved/non-API host: `401`.
- `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=true`: every protected public
  storefront request must be signed, including canonical MVN traffic.
- Invalid, stale or forged envelope: `401`.
- Valid signature for an unknown, disabled or non-public
  `StorefrontDomain -> Storefront -> Tenant` relation: `404`.
- Valid relation: pass its immutable `TenantScope` to the public command.

For protected `/api/v1/**` routes, unsigned API-host validation and the
require-signed switch also run at the outer ASGI boundary. A wrong `Host` or an
unsigned request while the switch is enabled therefore returns `401` before
body parsing. Canonical unsigned writes remain unbuffered but stream-counted
when the switch is off, preserving ordinary browser CORS behavior while
enforcing the same outer body ceiling.

Every response to a request containing any `X-MVN-Storefront-*` header is
forced to `Cache-Control: private, no-store`, `CDN-Cache-Control: no-store` and
`Vary: X-MVN-Storefront-Host`. This is applied at the final ASGI response
boundary, so it also covers rejected oversized bodies (`413`), FastAPI body
validation (`422`), route misses (`404`) and invalid/partial envelopes (`401`).
Existing `Vary` values are preserved and de-duplicated. Unhandled errors are
given the same headers explicitly by the global exception handler because
Starlette's outer error middleware creates that response outside the user
middleware chain. Shared caching belongs behind the trusted storefront runtime
and must be keyed by storefront.

The signing envelope is a server-to-server contract for trusted SSR or a
same-origin website proxy. Browsers must not receive credentials or send these
headers directly, and CORS preflight is not an authentication or signing
boundary. In air-api the signed-gateway/private-response middleware wraps CORS,
session and routing middleware; CORS behavior therefore remains unchanged while
all storefront-marked responses remain non-cacheable by shared intermediaries.

Neither `tenant_id` nor `storefront_id` is accepted from public payloads. The
public context DTO exposes only public slugs and display attributes.

## Protected public surfaces

The gateway is attached to storefront context, catalog/revision/spec/filter,
content/config/collection reads, public Lead adapters and public Order checkout.
It is not attached to Manager, internal bot, system or health/readiness
boundaries. The only intentionally open `/api/v1` routes are the exact `GET`
endpoints for EGR proxy, bank proxy, address suggestions and Yandex Business
feed; an app-level route inventory test rejects any new unclassified route.

## Production canary and rollback

The 2026-08-01 read-only production preflight verified that both active API
containers had every storefront signing, previous-key and require-signed
variable absent. The deployed `mvn-web` host served static files and had no
Node/runtime/container signing process. There was therefore no live signed v1
traffic to preserve when introducing v2.

Use this rolling order:

1. Keep `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS=false`.
2. Deploy the backend that verifies v2 while canonical unsigned traffic remains
   allowed. Keep `STOREFRONT_CONTEXT_ALLOW_LEGACY_V1_READS=false` unless an
   emergency read-only rollback requires it.
3. Configure the API primary key pair and allowed upstream API host on both HA
   runtimes with the require-signed switch still false; configure the same pair
   only in the trusted storefront server.
4. Deploy the storefront/proxy v2 signer. Create the second `Storefront` and
   active primary `StorefrontDomain` through
   the reviewed tenant setup path. Do not put test domains in migrations.
5. Call `GET /api/v1/storefront/context` through the proxy and verify its public
   identity and no-store headers.
6. Run one signed catalog query, one Lead and one Order canary. Verify exact
   persisted `tenant_id/storefront_id` and Manager visibility.
7. Tamper with protocol version, idempotency key, query, body, host and
   signature; each request must return `401`
   and create no row.
8. Keep canonical unsigned `mvn.by` smoke checks green. Only after canonical
   traffic is server-signed should you turn on
   `STOREFRONT_CONTEXT_REQUIRE_SIGNED_REQUESTS`.

Rollback is configuration-first: remove second-storefront routing, disable the
require-signed switch, and clear the primary/previous key pairs if the trusted
proxy is suspected. Canonical unsigned `mvn/main` remains available while the
switch is false. If only signed reads need temporary compatibility, enable the
legacy-v1-read flag without allowing any v1 write. No schema rollback is
required.
