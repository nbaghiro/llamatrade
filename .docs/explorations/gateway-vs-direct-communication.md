# API Gateway vs Direct Service Communication

> Exploration document comparing two approaches for frontend-to-backend communication in LlamaTrade.

## Overview

| Aspect | API Gateway | Direct Communication |
|--------|-------------|---------------------|
| **Pattern** | Browser → Gateway → Services | Browser → Services |
| **Examples** | Kong, Envoy, Traefik, AWS API Gateway | Connect protocol, direct gRPC-Web |
| **Best For** | Public APIs, large service counts | Internal APIs, latency-sensitive apps |

**Decision:** LlamaTrade uses **direct service communication** via Connect protocol.

---

## Architecture Comparison

### Option A: API Gateway

```
┌─────────┐      ┌─────────────┐      ┌──────────┐
│ Browser │ ───▶ │ API Gateway │ ───▶ │ Services │
└─────────┘      │   (:8000)   │      └──────────┘
                 └─────────────┘
```

- Single entry point for all API traffic
- Gateway validates JWT, rate limits, logs, then proxies to services
- Services receive pre-validated requests with tenant context

### Option B: Direct Communication (Current)

```
┌─────────┐      ┌──────────┐
│ Browser │ ───▶ │ Auth     │ :8810
│         │ ───▶ │ Strategy │ :8820
│         │ ───▶ │ Trading  │ :8850
│         │ ───▶ │ ...      │
└─────────┘      └──────────┘
```

- Frontend connects to each service directly
- Each service validates JWT via shared middleware
- Connect protocol enables HTTP/1.1 + JSON communication

---

## Detailed Comparison

### Authentication & Authorization

| Aspect | API Gateway | Direct Communication |
|--------|-------------|---------------------|
| JWT validation | Once at gateway | Each service validates |
| Token propagation | Gateway passes context downstream | Frontend sends token to each service |
| Consistency | Single implementation | Shared middleware required |
| Failure mode | Gateway down = no auth | Per-service auth failures isolated |

### Performance

| Aspect | API Gateway | Direct Communication |
|--------|-------------|---------------------|
| Latency overhead | +1-5ms per request (extra hop) | No overhead |
| Connection pooling | Gateway manages pools | Each service manages own |
| Streaming | Gateway must support/proxy | Native support |
| Scaling | Gateway must scale with total traffic | Each service scales independently |

### Operational Complexity

| Aspect | API Gateway | Direct Communication |
|--------|-------------|---------------------|
| Services to deploy | N + 1 (gateway) | N |
| Configuration | Centralized route config | Distributed (env vars) |
| Debugging | Request flows through proxy | Direct request/response |
| Local development | Must run gateway | No extra processes |

### Cross-Cutting Concerns

| Concern | API Gateway | Direct Communication |
|---------|-------------|---------------------|
| Rate limiting | Centralized, easy | Per-service or external (Redis) |
| Logging | Single point, consistent | Shared middleware |
| Metrics | Gateway collects all | Each service emits own |
| CORS | One config | Per-service config |
| Circuit breaking | Built-in | Must implement or use library |

### Failure Modes

| Scenario | API Gateway | Direct Communication |
|----------|-------------|---------------------|
| Gateway down | **All APIs down** | N/A |
| Single service down | Other services work | Other services work |
| Network partition | Gateway as SPOF | Partial functionality |
| Cascading failures | Gateway can circuit-break | Must handle per-service |

---

## Pros & Cons Summary

### API Gateway

**Pros:**
- Single entry point — one URL, simpler CORS
- Centralized cross-cutting concerns (auth, rate limiting, logging)
- Service discovery abstraction — frontend doesn't need service URLs
- Built-in circuit breaking and retry logic
- Easier for external API consumers
- Request transformation capabilities

**Cons:**
- Single point of failure
- Added latency (+1-5ms per request)
- Operational overhead (deploy, monitor, configure)
- gRPC-Web transcoding complexity
- Scaling bottleneck
- Configuration drift risk

### Direct Communication

**Pros:**
- No single point of failure
- Lower latency (no proxy hop)
- Simpler architecture (fewer moving parts)
- Independent service scaling
- Connect protocol works over HTTP/1.1, JSON visible in DevTools
- Easier local development

**Cons:**
- Multiple endpoints for frontend to track
- CORS configuration per service
- Cross-cutting concerns distributed across services
- Risk of inconsistent middleware implementations
- No centralized rate limiting out of the box
- Service discovery via configuration

---

## How LlamaTrade Mitigates Direct Communication Cons

| Concern | Solution |
|---------|----------|
| Auth consistency | `llamatrade_common` shared middleware in all services |
| Service discovery | Environment variables (`VITE_AUTH_URL`, `VITE_STRATEGY_URL`, etc.) |
| CORS | Same allowed origins configured in each service |
| Rate limiting | Redis-based rate limiting in shared middleware (planned) |
| Logging | Structured logging with correlation IDs in shared middleware |
| Load balancing | GCP L7 Load Balancer in production |
| Circuit breaking | Client-side retry logic + service health checks |

---

## When to Choose Each Approach

### Choose API Gateway When:

- Building a **public API** for third-party developers
- Need **API key management** and usage quotas
- Have **20+ microservices** (service mesh territory)
- Require **advanced traffic management** (canary, A/B, blue-green)
- Team doesn't control all services (need policy enforcement)
- Need **request/response transformation**

### Choose Direct Communication When:

- Building an **internal API** (your frontend only)
- Have **strong shared library discipline**
- Application is **latency-sensitive** (real-time data)
- Have **small-to-medium service count** (<15 services)
- Team **owns all services** and can enforce patterns
- Want **simpler local development** experience

---

## Why LlamaTrade Chose Direct Communication

1. **Connect protocol** — Eliminates need for gRPC-Web transcoding proxy. Works natively over HTTP/1.1 with JSON payloads.

2. **Shared middleware library** — `llamatrade_common` ensures consistent auth, logging, and error handling across all services.

3. **Latency requirements** — Real-time market data streaming benefits from eliminating the proxy hop.

4. **Simpler development** — No gateway process to run locally. Each service is independently testable.

5. **Production routing** — GCP L7 Load Balancer provides path-based routing and SSL termination without requiring an application-level gateway.

6. **Service count** — With 8 backend services, the complexity of managing multiple endpoints is manageable.

---

## Revisiting This Decision

Consider adding an API gateway if:

- We expose a **public API** for third-party integrations
- We need **sophisticated rate limiting** with quotas per API key
- Service count grows significantly (**20+**)
- We need **canary deployments** or **traffic splitting**
- **External teams** need to integrate with consistent policies

The current architecture supports adding a gateway layer later without major refactoring — services already handle their own auth, so a gateway would simply add another layer rather than replace existing functionality.
