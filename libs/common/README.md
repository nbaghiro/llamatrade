# LlamaTrade Common Library

Shared, service-agnostic building blocks imported as `llamatrade_common`. This is
the platform's **auth edge** plus a few cross-cutting utilities. It deliberately
stays free of `grpc` and `connectrpc` imports so any service (or lib) can depend
on it.

## Auth (`auth.py`) — the single platform mechanism

- **`AuthMiddleware`** — pure-ASGI, **fail-closed** (HTTP 401) middleware that
  verifies the inbound bearer token on every non-public request and stashes a
  verified `TenantContext` in a `ContextVar`. Accepts a user access JWT
  (`type=access`) or an internal service token (`type=service`); public paths
  (`/health`, `/metrics`, …) and CORS preflight pass through.
- **`TenantContext`** — the frozen, request-scoped verified identity
  (`tenant_id` / `user_id` / `roles` / `is_service`), read via `current_context()`.
- **`resolve_identity(wire_tenant_id, wire_user_id)`** — returns the trusted
  `(tenant_id, user_id)`: for a user token the token identity is authoritative and
  a mismatched wire `tenant_id` is rejected (cross-tenant guard); a service context
  trusts the forwarded wire identity.
- **`resolve_identity_connect(wire_context)`** (`connect.py`) — the connectrpc
  wrapper: same resolution, mapping `AuthError` → `ConnectError`. Kept out of
  `auth.py` so that module stays connectrpc-free. The grpc.aio equivalent lives in
  each grpc servicer.
- **`mint_service_token()` / `verify_credential()`** — issue / verify HS256 JWTs
  over `JWT_SECRET`. Inter-service gRPC clients attach a minted service token (via
  the interceptor in `llamatrade_proto`) so they pass the callee's fail-closed edge.

## Other utilities

- **`health.py`** — `HealthChecker`, `HealthStatus`, `check_postgres`, `check_redis`.
- **`ratelimit.py`** — Redis-backed fixed-window rate limiter (fails open on a
  Redis outage).
- **`revocation.py`** — `RevocationStore`: Redis-backed token denylist (`jti`) +
  per-user revoke-all timestamp (fails open).
- **`utils.py`** — `encrypt_value` / `decrypt_value` / `reencrypt_value`,
  `paginate`, API-key generation + hashing, `generate_uuid`, `utc_now`, symbol
  helpers.

## Credential encryption (`utils.py`)

`encrypt_value` / `decrypt_value` go through the envelope cipher named by
`CREDENTIAL_CIPHER`, which is a config choice, not a code change:

- **`local`** (default) — PBKDF2 + Fernet over `ENCRYPTION_KEY` with a random
  per-value salt. Envelope: `base64(salt || fernet_token)`.
- **`gcp-kms`** — a random per-credential Fernet data key encrypts the value and
  Cloud KMS wraps that data key, so a database dump is inert without the caller's
  KMS permission on the key. Envelope:
  `kms1.<b64 key version name>.<b64 wrapped data key>.<b64 fernet token>`.

The KMS key comes from `KMS_KEY_NAME` (a full crypto key resource name) or from
`KMS_PROJECT_ID` / `KMS_LOCATION` / `KMS_KEY_RING` / `KMS_KEY`, where the first
two fall back to `GCP_PROJECT_ID` / `GCP_REGION`. A missing key in
`production`/`staging` fails when the cipher is built. The `google-cloud-kms`
package is an extra (`llamatrade-common[gcp-kms]`) imported only on the KMS path;
services on the local cipher do not need it installed.

KMS failures map onto the same errors the local cipher raises: `InvalidToken`
when the key cannot open the envelope, `RuntimeError` for permission-denied,
key-not-found and unavailability. Google exceptions never reach callers.

Rotation: Cloud KMS decrypts across key versions, so envelopes stay readable
after a rotation. `reencrypt_value` moves a stored value onto the current key
material (a fresh salt for `local`, the primary version for `gcp-kms`), and
`GcpKmsCipher.key_version_name` reports the version an envelope was written
under so operators can find the stale rows.

## Related libraries

Observability (RED middleware, metrics, logs, traces) lives in
[`llamatrade_telemetry`](../telemetry); the event system (bus, catalog, streams)
lives in [`llamatrade_events`](../events). `llamatrade_common` carries neither.
