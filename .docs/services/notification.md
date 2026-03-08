# Notification Service

## Overview

The Notification Service manages alerts, notifications, and multi-channel message delivery for LlamaTrade. It enables traders to stay informed about strategy triggers, price movements, portfolio changes, and system events without constant manual monitoring.

**Why This Service Matters:**

- **Trader Awareness**: Markets move fast. A trader running multiple strategies needs immediate alerts when positions are opened, risk limits are hit, or unusual activity occurs.
- **Multi-Channel Delivery**: Different situations require different notification methods—email for daily summaries, SMS for critical alerts, Slack for team trading desks, webhooks for automated systems.
- **Alert Customization**: Traders should define their own alert conditions (price crosses $150, drawdown exceeds 5%, strategy triggers buy) rather than receiving generic platform notifications.

**Core Responsibilities:**

- Alert creation and condition evaluation
- Multi-channel notification delivery (email, SMS, Slack, webhook)
- Notification history and read status tracking
- Channel configuration and verification
- Cooldown and rate limiting for alerts

> **Note:** This service is currently ~5% implemented. The architecture and schemas are defined, but delivery mechanisms are stubbed with in-memory storage.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Notification Service                               │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        gRPC Protocol                                │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                    NotificationServicer                             │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌───────────────────┐    │    │
│  │  │  Notifications  │  │     Alerts      │  │    Channels       │    │    │
│  │  │  - list         │  │  - list/create  │  │  - list/update    │    │    │
│  │  │  - mark_read    │  │  - delete/toggle│  │  - test           │    │    │
│  │  └─────────────────┘  └─────────────────┘  └───────────────────┘    │    │
│  └───────────────────────────────┬─────────────────────────────────────┘    │
│                                  │                                          │
│  ┌───────────────────────────────▼─────────────────────────────────────┐    │
│  │                    In-Memory Storage (Stub)                         │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │ _notifications: dict[str, list[dict]]  # tenant:user → list │    │    │
│  │  │ _alerts: dict[str, list[dict]]         # tenant:user → list │    │    │
│  │  │ _channels: dict[str, list[dict]]       # tenant:user → list │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │               Channel Handlers (Future Implementation)              │    │
│  │  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌────────────────────┐   │    │
│  │  │   Email   │ │    SMS    │ │   Slack   │ │      Webhook       │   │    │
│  │  │ (SMTP/SES)│ │ (Twilio)  │ │(API/hook) │ │  (HTTP POST)       │   │    │
│  │  └───────────┘ └───────────┘ └───────────┘ └────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Alert Evaluation Flow (Future)

```
┌─────────────┐     ┌──────────────┐     ┌────────────────────┐
│  Market     │     │   Trading    │     │   Notification     │
│  Data       │     │   Service    │     │   Service          │
└──────┬──────┘     └──────┬───────┘     └─────────┬──────────┘
       │                   │                       │
       │ 1. Price update   │                       │
       │   AAPL = $152     │                       │
       │──────────────────>│                       │
       │                   │                       │
       │                   │ 2. Check user alerts  │
       │                   │    for AAPL           │
       │                   │──────────────────────>│
       │                   │                       │
       │                   │                       │ 3. Alert condition:
       │                   │                       │    AAPL > $150
       │                   │                       │    ✓ Triggered!
       │                   │                       │
       │                   │                       │ 4. Check cooldown
       │                   │                       │    (5 min since last)
       │                   │                       │
       │                   │                       │ 5. Send to channels:
       │                   │                       │    - Email
       │                   │                       │    - Slack
       │                   │                       │
       │                   │                       │ 6. Create notification
       │                   │                       │    record
       │                   │                       │
```

---

## Directory Structure

```
services/notification/
├── src/
│   ├── main.py                 # FastAPI app, health check
│   ├── models.py               # Pydantic schemas (190 lines)
│   ├── grpc/
│   │   └── servicer.py         # NotificationServicer (521 lines)
│   └── channels/               # Channel implementations (stubs)
│       ├── __init__.py
│       ├── email.py            # Email sender (stub)
│       ├── sms.py              # SMS sender (stub)
│       ├── slack.py            # Slack sender (stub)
│       └── webhook.py          # Webhook sender (stub)
├── tests/
│   ├── conftest.py
│   ├── test_health.py
│   ├── test_notifications.py
│   ├── test_alerts.py
│   ├── test_channels.py
│   ├── test_email_channel.py
│   ├── test_sms.py
│   ├── test_slack.py
│   └── test_webhook_channel.py
├── pyproject.toml
└── Dockerfile
```

---

## Core Components

| Component                | File                  | Purpose                               |
| ------------------------ | --------------------- | ------------------------------------- |
| **NotificationServicer** | `grpc/servicer.py`    | gRPC servicer, in-memory stub storage |
| **EmailChannel**         | `channels/email.py`   | Email delivery (stub)                 |
| **SMSChannel**           | `channels/sms.py`     | SMS delivery via Twilio (stub)        |
| **SlackChannel**         | `channels/slack.py`   | Slack message delivery (stub)         |
| **WebhookChannel**       | `channels/webhook.py` | HTTP webhook delivery (stub)          |

---

## RPC Endpoints

### Notifications

| Method              | Request                    | Response                    | Description                                      |
| ------------------- | -------------------------- | --------------------------- | ------------------------------------------------ |
| `ListNotifications` | `ListNotificationsRequest` | `ListNotificationsResponse` | List notifications with pagination, unread count |
| `MarkAsRead`        | `MarkAsReadRequest`        | `MarkAsReadResponse`        | Mark one or all notifications as read            |

### Alerts

| Method        | Request              | Response              | Description                                  |
| ------------- | -------------------- | --------------------- | -------------------------------------------- |
| `ListAlerts`  | `ListAlertsRequest`  | `ListAlertsResponse`  | List user's alerts (optionally active only)  |
| `CreateAlert` | `CreateAlertRequest` | `CreateAlertResponse` | Create new alert with condition and channels |
| `DeleteAlert` | `DeleteAlertRequest` | `DeleteAlertResponse` | Delete an alert                              |
| `ToggleAlert` | `ToggleAlertRequest` | `ToggleAlertResponse` | Enable/disable an alert                      |

### Channels

| Method          | Request                | Response                | Description                              |
| --------------- | ---------------------- | ----------------------- | ---------------------------------------- |
| `ListChannels`  | `ListChannelsRequest`  | `ListChannelsResponse`  | List configured notification channels    |
| `UpdateChannel` | `UpdateChannelRequest` | `UpdateChannelResponse` | Configure a channel (enable, set config) |
| `TestChannel`   | `TestChannelRequest`   | `TestChannelResponse`   | Send test notification to channel        |

---

## Data Models

### Alert Condition Types

```
┌──────────────────────────────────────────────────────────────────────┐
│                      ALERT CONDITION TYPES                           │
├──────────────────────┬───────────────────────────────────────────────┤
│ PRICE_ABOVE          │ Trigger when asset price exceeds threshold    │
│ PRICE_BELOW          │ Trigger when asset price falls below threshold│
│ PRICE_PERCENT_CHANGE │ Trigger on % change from reference price      │
│ STRATEGY_SIGNAL      │ Trigger when strategy emits buy/sell signal   │
│ PORTFOLIO_VALUE      │ Trigger on portfolio value threshold          │
│ DRAWDOWN             │ Trigger when drawdown exceeds limit           │
│ ORDER_FILLED         │ Trigger when order is executed                │
│ POSITION_OPENED      │ Trigger when new position is opened           │
│ POSITION_CLOSED      │ Trigger when position is closed               │
└──────────────────────┴───────────────────────────────────────────────┘
```

### Channel Types

```
┌──────────────────────────────────────────────────────────────────────┐
│                        CHANNEL TYPES                                 │
├──────────────┬───────────────────────────────────────────────────────┤
│ EMAIL        │ SMTP/SES delivery to configured email address         │
│ SMS          │ Text message via Twilio to phone number               │
│ PUSH         │ Mobile push notification (Firebase/APNS)              │
│ SLACK        │ Post to Slack channel via webhook or API              │
│ WEBHOOK      │ HTTP POST to custom endpoint                          │
└──────────────┴───────────────────────────────────────────────────────┘
```

### Pydantic Schemas

```python
# Alert Creation
class AlertCreate(BaseModel):
    type: int                    # AlertConditionType proto value
    symbol: str | None = None    # Required for price alerts
    threshold: float | None = None
    channels: list[int] = [CHANNEL_TYPE_EMAIL]  # Default to email
    message_template: str | None = None

# Alert Response
class AlertResponse(BaseModel):
    id: UUID
    type: int                    # AlertConditionType
    symbol: str | None
    threshold: float | None
    channels: list[int]          # List of ChannelType values
    is_active: bool
    triggered_count: int
    last_triggered_at: datetime | None
    created_at: datetime

# Notification Response
class NotificationResponse(BaseModel):
    id: UUID
    channel: int                 # ChannelType
    priority: NotificationPriority  # low/medium/high/critical
    subject: str
    message: str
    status: int                  # pending/sent/failed/read
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime

# Channel Configuration
class ChannelConfig(BaseModel):
    type: int                    # ChannelType
    is_enabled: bool
    config: ChannelConfigUnion   # Type-specific configuration

# Channel-specific configs
class EmailConfig(TypedDict):
    smtp_host: str
    smtp_port: int
    from_address: str

class SlackConfig(TypedDict):
    webhook_url: str
    channel: str

class WebhookChannelConfig(TypedDict):
    url: str
    secret: str | None
    headers: dict[str, str]
```

### Notification Priority

| Priority   | Use Case                                       |
| ---------- | ---------------------------------------------- |
| `LOW`      | Daily summaries, informational updates         |
| `MEDIUM`   | Strategy signals, position changes             |
| `HIGH`     | Risk alerts, large position changes            |
| `CRITICAL` | Margin calls, system failures, security alerts |

---

## Configuration

### Environment Variables

| Variable            | Required | Default | Description                           |
| ------------------- | -------- | ------- | ------------------------------------- |
| `DATABASE_URL`      | Yes      | -       | PostgreSQL connection string (future) |
| `SMTP_HOST`         | No       | -       | Email SMTP server                     |
| `SMTP_PORT`         | No       | `587`   | SMTP port                             |
| `SMTP_USER`         | No       | -       | SMTP authentication user              |
| `SMTP_PASSWORD`     | No       | -       | SMTP authentication password          |
| `TWILIO_SID`        | No       | -       | Twilio account SID for SMS            |
| `TWILIO_TOKEN`      | No       | -       | Twilio auth token                     |
| `TWILIO_FROM`       | No       | -       | Twilio phone number                   |
| `NOTIFICATION_PORT` | No       | `8870`  | Service port                          |

### Port Assignment

| Service      | Port |
| ------------ | ---- |
| Notification | 8870 |

---

## Health Check

```http
GET /health
```

**Response:**

```json
{
  "status": "healthy",
  "service": "notification",
  "version": "0.1.0"
}
```

---

## Internal Service Connections

### Who Calls Notification Service

| Service          | Methods Used                                   | Purpose                     |
| ---------------- | ---------------------------------------------- | --------------------------- |
| **Web Frontend** | `ListNotifications`, `MarkAsRead`              | Display notification center |
| **Web Frontend** | `ListAlerts`, `CreateAlert`, `ToggleAlert`     | Alert management UI         |
| **Web Frontend** | `ListChannels`, `UpdateChannel`, `TestChannel` | Channel configuration       |
| **Trading**      | (Future) Alert evaluation trigger              | Strategy signals            |
| **Market-Data**  | (Future) Price alert evaluation                | Price threshold triggers    |

### What Notification Service Calls (Future)

| Target             | Purpose                              |
| ------------------ | ------------------------------------ |
| **PostgreSQL**     | Alert, notification, channel storage |
| **SMTP/SES**       | Email delivery                       |
| **Twilio**         | SMS delivery                         |
| **Slack API**      | Slack message posting                |
| **HTTP Endpoints** | Webhook delivery                     |

---

## Complete Data Flow Example

### Creating and Triggering a Price Alert (Future)

```
1. User creates alert via frontend
   └─> CreateAlert({
         type: PRICE_ABOVE,
         symbol: "AAPL",
         threshold: 150.00,
         channels: [EMAIL, SLACK],
         cooldown_minutes: 60
       })

2. NotificationServicer stores alert
   └─> Generate UUID
   └─> Store in alerts table (or in-memory dict for now)
   └─> Return CreateAlertResponse

3. Market-Data service streams price update
   └─> AAPL price: $151.25

4. Alert evaluation (future implementation)
   └─> Query active alerts for AAPL
   └─> Check condition: 151.25 > 150.00 ✓
   └─> Check cooldown: last_triggered_at + 60 min < now ✓

5. Create notification
   └─> INSERT INTO notifications (
         tenant_id, user_id, type: ALERT_TRIGGERED,
         title: "Price Alert: AAPL",
         message: "AAPL crossed above $150.00 (now $151.25)"
       )

6. Dispatch to channels
   └─> EmailChannel.send(user_email, subject, message)
   └─> SlackChannel.send(webhook_url, message)

7. Update alert
   └─> times_triggered += 1
   └─> last_triggered_at = now
```

### Configuring a Slack Channel

```
1. User navigates to notification settings
   └─> Frontend calls ListChannels()
   └─> Returns default channels (email unconfigured)

2. User adds Slack webhook URL
   └─> Frontend calls UpdateChannel({
         type: CHANNEL_TYPE_SLACK,
         is_enabled: true,
         config: {
           webhook_url: "https://hooks.slack.com/services/xxx",
           channel: "#trading-alerts"
         }
       })

3. NotificationServicer updates channel
   └─> Store/update in channels dict
   └─> Return UpdateChannelResponse

4. User clicks "Test"
   └─> Frontend calls TestChannel(type: SLACK)
   └─> SlackChannel.send_test()
   └─> Return TestChannelResponse(success: true)
```

---

## Error Handling

### gRPC Error Codes

| Error                 | Code | When Raised                                   |
| --------------------- | ---- | --------------------------------------------- |
| `NOT_FOUND`           | 5    | Alert/notification not found                  |
| `INVALID_ARGUMENT`    | 3    | Invalid channel type, missing required fields |
| `FAILED_PRECONDITION` | 9    | Channel not configured, verification required |
| `INTERNAL`            | 13   | Delivery failure, database errors             |

---

## Testing

### Test Structure

```
tests/
├── conftest.py                 # Fixtures
├── test_health.py              # Health check tests
├── test_notifications.py       # Notification listing, read status
├── test_alerts.py              # Alert CRUD tests
├── test_channels.py            # Channel configuration tests
├── test_email_channel.py       # Email delivery tests
├── test_sms.py                 # SMS delivery tests
├── test_slack.py               # Slack delivery tests
└── test_webhook_channel.py     # Webhook delivery tests
```

### Running Tests

```bash
# Run all notification tests
cd services/notification && pytest

# Run with coverage
cd services/notification && pytest --cov=src --cov-report=term-missing

# Run specific test
cd services/notification && pytest tests/test_alerts.py -v
```

### Key Test Scenarios

- **Notifications**: List with pagination, filter unread, mark as read
- **Alerts**: Create, list, toggle, delete, cooldown logic
- **Channels**: Configure, enable/disable, test delivery
- **Delivery**: Email formatting, Slack message structure, webhook signing

---

## Current Implementation Status

> **Project Stage:** Early Development (Stub Service)

### What's Real (Implemented)

- [x] gRPC servicer with all method signatures
- [x] In-memory storage for notifications, alerts, channels
- [x] ListNotifications with pagination and unread count
- [x] MarkAsRead (single and mark-all)
- [x] CreateAlert with condition storage
- [x] DeleteAlert, ToggleAlert
- [x] ListChannels with default channel creation
- [x] UpdateChannel configuration
- [x] TestChannel (always returns success)
- [x] Proto-to-dict conversion helpers

### What's Stubbed (TODO)

- [ ] Database persistence (all in-memory)
- [ ] Email delivery (SMTP/SES integration)
- [ ] SMS delivery (Twilio integration)
- [ ] Slack delivery (webhook/API integration)
- [ ] Webhook delivery (HTTP client)
- [ ] Push notifications (Firebase/APNS)
- [ ] Alert evaluation engine
- [ ] Integration with Market-Data for price alerts
- [ ] Integration with Trading for strategy signals
- [ ] Channel verification (email confirmation, etc.)
- [ ] Rate limiting and abuse prevention
- [ ] Notification templating system

### Known Limitations

1. **No persistence**: All data is lost on service restart
2. **No actual delivery**: TestChannel always succeeds, no real sending
3. **No alert evaluation**: Alerts are stored but never triggered
4. **No external integrations**: SMTP, Twilio, Slack not connected

---

## Future Implementation Plan

### Phase 1: Database Persistence

- Migrate in-memory dicts to SQLAlchemy models
- Add notification, alert, channel tables
- Implement proper queries with tenant isolation

### Phase 2: Email Channel

- Integrate with AWS SES or SMTP
- Implement email verification flow
- Add HTML email templates

### Phase 3: Alert Evaluation Engine

- Background task for price alert monitoring
- Integration with Market-Data price streams
- Cooldown and deduplication logic

### Phase 4: Additional Channels

- Twilio SMS integration
- Slack API/webhook support
- Custom webhook delivery with signing

### Phase 5: Advanced Features

- Push notifications
- Alert condition builder UI
- Notification preferences/quiet hours

---

## Summary

The Notification Service manages alerts, notifications, and multi-channel message delivery for LlamaTrade. While the architecture and API surface are fully defined with 10 RPC methods, the service is currently a stub implementation (~5% complete) using in-memory storage.

The intended design supports multiple notification channels (email, SMS, Slack, webhook), customizable alert conditions (price thresholds, strategy signals, portfolio events), and user-configurable channel preferences. Future implementation will add database persistence, external integrations for delivery, and an alert evaluation engine that connects with Market-Data and Trading services.

For now, the service demonstrates the planned API surface and data models, allowing frontend development to proceed against a stable interface while backend delivery mechanisms are built out.
