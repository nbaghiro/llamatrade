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

- **`errors.py`** — the `DSLError` / `DSLErrorCode` taxonomy plus `classify_error`,
  `create_dsl_error`, `grpc_status_from_dsl_code`.
- **`health.py`** — `HealthChecker`, `HealthStatus`, `check_postgres`, `check_redis`.
- **`utils.py`** — Fernet `encrypt_value` / `decrypt_value`, `paginate`, API-key
  generation + hashing, `generate_uuid`, `utc_now`, symbol helpers.

## Related libraries

Observability (RED middleware, metrics, logs, traces) lives in
[`llamatrade_telemetry`](../telemetry); the event system (bus, catalog, streams)
lives in [`llamatrade_events`](../events). `llamatrade_common` carries neither.
