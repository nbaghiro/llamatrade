# Notification Service

> **Implementation status: stub (in-memory, no persistence).** The service exposes the full
> RPC surface for alerts, notifications, and channels, but all state lives in per-process
> in-memory dicts, nothing is delivered to any channel, and there is no alert-evaluation engine.
> The DB-backed, multi-channel, alert-evaluating design is captured under "Planned / Not
> implemented".

## Overview

The Notification Service is intended to manage alerts, notifications, and multi-channel message
delivery for LlamaTrade — letting traders define alert conditions and receive them by email, SMS,
Slack, or webhook. Today it is an early stub: the gRPC surface exists and is tenant-isolated, but
it stores data in memory and does not evaluate alerts or deliver messages.

**Core Responsibilities (target):**

- Alert creation and condition evaluation
- Multi-channel notification delivery (email, SMS, Slack, webhook)
- Notification history and read-status tracking
- Channel configuration and verification
- Cooldown and rate limiting for alerts

**What actually runs today:**

- A `grpc.aio` servicer with 9 RPCs behind the fail-closed `AuthMiddleware`
- In-memory storage keyed `f"{tenant_id}:{user_id}"` for notifications, alerts, and channels
- Verified tenant/user identity via `resolve_identity` (`_identity` helper)
- No PostgreSQL, no delivery, no alert evaluation

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                      FastAPI :8870                                        ║
╠══════════════════════════════════════════════════════════════════════════════════════════╣
║ Connect / gRPC ASGI app  ·  fail-closed AuthMiddleware  ·  resolve_identity per call      ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                       NotificationServicer  ·  9 RPCs  ·  STUB                            │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Notifications · ListNotifications · MarkAsRead                                            │
│ Alerts · ListAlerts · CreateAlert · DeleteAlert · ToggleAlert                             │
│ Channels · ListChannels · UpdateChannel · TestChannel                                     │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│                        In-memory dicts (lost on restart)                                 │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ self._notifications  ·  self._alerts  ·  self._channels   (keyed "tenant_id:user_id")     │
└──────────────────────────────────────────────────────────────────────────────────────────┘

  channels/{email,sms,slack,webhook}.py exist as classes but their send() methods are stubs
  (return True) and are NOT invoked by the servicer. There is no PostgreSQL and no models.py.
```

---

## Directory Structure

```
services/notification/
├── src/
│   ├── main.py                 # FastAPI app, AuthMiddleware, health check
│   ├── grpc/
│   │   └── servicer.py         # NotificationServicer (9 RPCs, in-memory stub)
│   └── channels/               # Channel classes (stub send(); not wired to the servicer)
│       ├── email.py            # EmailChannel.send() -> True
│       ├── sms.py              # SMSChannel (stub)
│       ├── slack.py            # SlackChannel (stub)
│       └── webhook.py          # WebhookChannel (stub)
├── tests/
├── pyproject.toml
└── Dockerfile
```

There is **no** `models.py` — request/response types are the proto messages (`notification_pb2`),
and the servicer maps its in-memory dicts to protos via `_to_proto_*` helpers.

---

## Core Components

| Component                | File                  | Purpose                                             |
| ------------------------ | --------------------- | --------------------------------------------------- |
| **NotificationServicer** | `grpc/servicer.py`    | gRPC servicer; in-memory storage; proto conversion  |
| **EmailChannel** (stub)  | `channels/email.py`   | `send()` returns `True`; not called by the servicer |
| **SMSChannel** (stub)    | `channels/sms.py`     | Stub sender; not wired                               |
| **SlackChannel** (stub)  | `channels/slack.py`   | Stub sender; not wired                              |
| **WebhookChannel** (stub)| `channels/webhook.py` | Stub sender; not wired                              |

---

## RPC Endpoints (9 gRPC methods)

### Notifications

| Method              | Request                    | Response                    | Behavior (current)                                |
| ------------------- | -------------------------- | --------------------------- | ------------------------------------------------- |
| `ListNotifications` | `ListNotificationsRequest` | `ListNotificationsResponse` | Reads in-memory list; pagination + unread count   |
| `MarkAsRead`        | `MarkAsReadRequest`        | `MarkAsReadResponse`        | Flags in-memory entries read (single or mark-all) |

### Alerts

| Method        | Request              | Response              | Behavior (current)                              |
| ------------- | -------------------- | --------------------- | ----------------------------------------------- |
| `ListAlerts`  | `ListAlertsRequest`  | `ListAlertsResponse`  | Reads in-memory alerts (optionally active only) |
| `CreateAlert` | `CreateAlertRequest` | `CreateAlertResponse` | Appends an alert dict to memory (no evaluation) |
| `DeleteAlert` | `DeleteAlertRequest` | `DeleteAlertResponse` | Removes from memory (NOT_FOUND if absent)       |
| `ToggleAlert` | `ToggleAlertRequest` | `ToggleAlertResponse` | Flips `is_active` in memory                     |

### Channels

| Method          | Request                | Response                | Behavior (current)                                       |
| --------------- | ---------------------- | ----------------------- | -------------------------------------------------------- |
| `ListChannels`  | `ListChannelsRequest`  | `ListChannelsResponse`  | Returns stored channels, or a default disabled EMAIL one |
| `UpdateChannel` | `UpdateChannelRequest` | `UpdateChannelResponse` | Upserts a channel config in memory                       |
| `TestChannel`   | `TestChannelRequest`   | `TestChannelResponse`   | Always returns `success=True, "...(stub)"` — sends nothing |

---

## Data Models

Alert condition types and channel types come from the proto (`notification_pb2`) — e.g.
`ALERT_CONDITION_TYPE_*` and `CHANNEL_TYPE_EMAIL` / `CHANNEL_TYPE_SLACK` / `CHANNEL_TYPE_WEBHOOK`.
The servicer holds plain dicts (id, tenant_id, user_id, condition, channels, cooldown_minutes,
timestamps) and converts them to `Notification` / `Alert` / `Channel` protos on read. There is no
`models.py` and no Pydantic schema layer.

---

## Configuration

### Environment Variables

| Variable       | Required | Default           | Description                                    |
| -------------- | -------- | ----------------- | ---------------------------------------------- |
| `JWT_SECRET`   | Yes      | -                 | Verifies inbound tokens (middleware)           |
| `CORS_ORIGINS` | No       | localhost origins | Allowed CORS origins                           |
| `DATABASE_URL` | No       | -                 | Read by the shared DB lib; unused by the stub  |

SMTP / Twilio / Slack settings are **not** read anywhere yet — delivery is unimplemented.

### Port Assignment

| Service      | Port |
| ------------ | ---- |
| Notification | 8870 |

---

## Health Check

```http
GET /health
```

```json
{
  "status": "healthy",
  "service": "notification",
  "version": "0.1.0"
}
```

---

## Tenant Isolation

- **Fail-closed edge**: `main.py` installs `AuthMiddleware`, so every RPC requires a valid token.
- **Verified identity**: each RPC derives `(tenant_id, user_id)` via `resolve_identity`
  (`_identity(request.context)`), rejecting a forged wire tenant; `_abort_auth` maps `AuthError`
  to the appropriate `grpc.StatusCode`. In-memory storage is keyed by the verified
  `f"{tenant_id}:{user_id}"`, so there is no cross-user leakage within a process — but nothing is
  persisted or shared across instances.

---

## Error Handling

| Error               | Code | When                                          |
| ------------------- | ---- | --------------------------------------------- |
| `UNAUTHENTICATED`   | 16   | Missing/invalid token; unresolved identity    |
| `PERMISSION_DENIED` | 7    | Forged wire tenant (`resolve_identity`)       |
| `NOT_FOUND`         | 5    | Alert not found (`DeleteAlert`/`ToggleAlert`) |
| `INTERNAL`          | 13   | Unexpected servicer error                     |

---

## Capabilities (today)

- 9-RPC gRPC surface for notifications, alerts, and channels
- In-memory CRUD with pagination and unread counts
- Fail-closed tenant/user isolation via `resolve_identity`
- Proto conversion helpers (`_to_proto_notification` / `_to_proto_alert` / `_to_proto_channel`)

## Planned / Not implemented

- **Persistence** — replace in-memory dicts with PostgreSQL tables (notifications, alerts, channels), tenant/user scoped, so data survives restarts and is shared across instances.
- **Channel delivery** — wire `EmailChannel` (SMTP/SES), `SMSChannel` (Twilio), `SlackChannel`, and `WebhookChannel` into an actual send path; their `send()` methods are stubs today.
- **Alert-evaluation engine** — evaluate alert conditions against market-data/trading events, apply cooldowns, and emit notifications. No such evaluation exists.
- **`TestChannel` real delivery** — currently always returns success without sending.
- **PUSH channel** (Firebase/APNS) — referenced conceptually but has no implementation.
- **Notification templating, rate limiting, and channel verification.**

---

## Summary

The Notification Service defines the intended alerting/notification API — 9 gRPC RPCs for
notifications, alerts, and channels — but is an early **stub**: all state is in-memory (no
PostgreSQL, no `models.py`), no message is ever delivered (the `channels/` senders are stubs and
unwired), and there is no alert-evaluation engine. What is real and correct today is the
fail-closed, `resolve_identity`-based tenant/user isolation on every call. The DB-backed,
multi-channel, alert-evaluating system is future work (see "Planned / Not implemented").
