# Agent Service

## Overview

The Agent Service is LlamaTrade's AI Strategy Agent (Copilot). It lets users generate, edit, and reason about trading strategies through natural-language conversation. It turns a plain-English request into validated strategy DSL, runs read-only analysis tools against the user's own data, and proposes side-effecting actions the user explicitly approves before they run.

**Why This Service Matters:**

- **Natural-language strategy authoring**: Users describe an idea in prose; the agent produces validated DSL and a committable strategy artifact, lowering the barrier to building automated strategies.
- **Grounded, tenant-scoped answers**: The agent answers over the caller's real strategies, portfolio, and backtests via tools — not hallucinated data — all under the caller's tenant.
- **Safe autonomy**: Read tools run automatically; write/side-effecting tools are *proposed* and only execute after the user confirms (draft-and-confirm), so the Copilot stays self-directed and never trades or spends compute behind the user's back.

**Core Responsibilities:**

- Conversation session and message management (persistent history)
- Streaming LLM responses with separated reasoning ("thinking") and answer channels
- An agentic tool loop over strategy / portfolio / backtest / validation / memory tools
- NL → strategy DSL, surfaced as a pending artifact the user can commit to a real strategy
- Draft-and-confirm approval for write actions
- Lightweight per-user memory (preferences, goals) extracted from conversation

---

## Architecture Overview

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                                      FastAPI :8890                                        ║
╠══════════════════════════════════════════════════════════════════════════════════════════╣
║ Connect / gRPC ASGI app  ·  fail-closed AuthMiddleware  ·  CORS  ·  SSE streaming         ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝
                                              │
                                              ▼
╭──────────────────────────────────────────────────────────────────────────────────────────╮
│                                AgentServicer  ·  10 RPCs                                  │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ Sessions · CreateSession · GetSession · ListSessions · DeleteSession                     │
│ Messaging · SendMessage · StreamMessage · ConfirmToolCall                                │
│ Artifacts · CommitArtifact · GetArtifact                                                 │
│ Suggestions · GetSuggestedPrompts                                                        │
╰──────────────────────────────────────────────────────────────────────────────────────────╯
                                              │
                                              ▼
        ╭────────────────╮ ╭──────────────────╮ ╭────────────────╮ ╭──────────────────╮
        │  AgentService  │ │ ConversationSvc  │ │ ArtifactService│ │  MemoryService   │
        ├────────────────┤ ├──────────────────┤ ├────────────────┤ ├──────────────────┤
        │ tool loop      │ │ sessions/messages│ │ pending → real │ │ facts + hints    │
        │ streaming      │ │ (DB)             │ │ strategy       │ │ (regex extract)  │
        ╰────────────────╯ ╰──────────────────╯ ╰────────────────╯ ╰──────────────────╯
                │                                       │
                ▼                                       ▼
        ╭────────────────╮                      ┌──────────────────┐
        │   LLM client   │                      │    PostgreSQL    │
        ├────────────────┤                      ├──────────────────┤
        │ Gemini default │                      │ agent_sessions   │
        │ Anthropic alt  │                      │ agent_messages   │
        ╰────────────────╯                      │ pending_artifacts│
                │                                │ agent_memory_*   │
                ▼                                └──────────────────┘
        ╭──────────────────────────────────────────────╮
        │           ToolExecutor · 14 tools            │
        ├──────────────────────────────────────────────┤
        │ strategy · portfolio · backtest · validation │
        │ memory   ·  S2S Connect clients to services  │
        ╰──────────────────────────────────────────────╯
```

### Message / tool loop

```
 user message
     │
     ▼
 load history (last 40 turns) → build few-shot + history + system prompt
     │
     ▼
 ┌───────────────────────── tool loop (≤ 10 iterations) ─────────────────────────┐
 │ stream LLM → CONTENT_DELTA / THINKING_DELTA / TOOL_USE_*                       │
 │   no tool calls           → done                                              │
 │   read tool  (auto)       → execute, feed result back, continue               │
 │   write tool (run_backtest) → emit TOOL_CONFIRMATION_REQUIRED, halt turn      │
 │   validate_dsl success    → create PendingArtifact, emit ARTIFACT_CREATED     │
 └───────────────────────────────────────────────────────────────────────────────┘
     │
     ▼
 persist assistant message (single writer) → COMPLETE
     │
     └─ (fire-and-forget) extract memory facts from the user message
```

Write actions resume via `ConfirmToolCall(approved=true)`, which executes the gated tool and streams a plain-language summary.

---

## Directory Structure

```
services/agent/
├── src/
│   ├── main.py                    # FastAPI app, Connect mount, health check
│   ├── grpc/
│   │   ├── servicer.py            # AgentServicer - 10 RPC methods
│   │   └── error_handler.py       # @handle_service_errors, parse_uuid
│   ├── services/
│   │   ├── agent_service.py       # Core orchestration + tool loop + streaming
│   │   ├── conversation_service.py# Session/message CRUD (DB)
│   │   ├── artifact_service.py    # Pending artifact → committed strategy
│   │   ├── memory_service.py      # Memory facts + memory hint
│   │   └── extraction_service.py  # Regex fact extraction from conversation
│   ├── llm/
│   │   ├── client.py              # LLMClient ABC, provider selection, config
│   │   ├── gemini.py              # Google Gemini client (default)
│   │   ├── anthropic.py           # Anthropic client (fallback)
│   │   └── thinking.py            # Splits reasoning vs answer channels
│   ├── prompts/
│   │   ├── system.py              # System prompt + memory hint builder
│   │   ├── few_shot.py            # Few-shot examples
│   │   └── context.py             # Context-aware suggested prompts
│   └── tools/
│       ├── base.py                # BaseTool, ToolContext, ToolResult
│       ├── executor.py            # ToolExecutor registry + execution
│       ├── definitions.py         # Tool definitions for the LLM API
│       ├── clients.py             # S2S Connect clients (service tokens)
│       ├── strategy_tools.py      # list/get strategies, list templates
│       ├── portfolio_tools.py     # portfolio summary/performance/positions
│       ├── backtest_tools.py      # get/list results, run_backtest
│       ├── validation_tools.py    # validate_dsl, get_asset_info
│       └── memory_tools.py        # recall_memory, user profile, past strategies
├── tests/
├── pyproject.toml
└── Dockerfile
```

---

## Core Components

| Component               | File                             | Purpose                                                         |
| ----------------------- | -------------------------------- | -------------------------------------------------------------- |
| **AgentServicer**       | `grpc/servicer.py`               | Connect servicer, 10 RPCs; relays agent events to stream protos |
| **AgentService**        | `services/agent_service.py`      | Tool loop, streaming, artifact creation, memory kickoff         |
| **ConversationService** | `services/conversation_service.py`| Sessions and messages (PostgreSQL)                             |
| **ArtifactService**     | `services/artifact_service.py`   | Commit a pending artifact into a real strategy                  |
| **MemoryService**       | `services/memory_service.py`     | Store memory facts, build memory hint for the system prompt     |
| **ToolExecutor**        | `tools/executor.py`              | Registers 14 tools; runs them; gates confirmation               |
| **LLMClient**           | `llm/client.py`                  | Provider-agnostic streaming/complete interface                  |

---

## RPC Endpoints

### Sessions

| Method          | Request                | Response                | Description                                     |
| --------------- | ---------------------- | ----------------------- | ----------------------------------------------- |
| `CreateSession` | `CreateSessionRequest` | `CreateSessionResponse` | Create a new conversation session               |
| `GetSession`    | `GetSessionRequest`    | `GetSessionResponse`    | Get a session, optionally with messages/artifacts |
| `ListSessions`  | `ListSessionsRequest`  | `ListSessionsResponse`  | List the user's sessions (paginated)            |
| `DeleteSession` | `DeleteSessionRequest` | `DeleteSessionResponse` | Delete a session and its messages               |

### Messaging

| Method            | Request                   | Response (stream)      | Description                                             |
| ----------------- | ------------------------- | ---------------------- | ------------------------------------------------------ |
| `SendMessage`     | `SendMessageRequest`      | `SendMessageResponse`  | Non-streaming turn (collects the stream into one reply) |
| `StreamMessage`   | `SendMessageRequest`      | stream `AgentStreamEvent` | Streaming turn (SSE): content/thinking/tool/artifact events |
| `ConfirmToolCall` | `ConfirmToolCallRequest`  | stream `AgentStreamEvent` | Approve/deny a proposed write tool, then resume the turn |

### Artifacts

| Method           | Request                 | Response                 | Description                                        |
| ---------------- | ----------------------- | ------------------------ | -------------------------------------------------- |
| `CommitArtifact` | `CommitArtifactRequest` | `CommitArtifactResponse` | Turn a pending artifact into a real strategy       |
| `GetArtifact`    | `GetArtifactRequest`    | `GetArtifactResponse`    | Fetch a pending artifact by id                     |

### Suggestions

| Method                | Request                      | Response                      | Description                        |
| --------------------- | ---------------------------- | ----------------------------- | ---------------------------------- |
| `GetSuggestedPrompts` | `GetSuggestedPromptsRequest` | `GetSuggestedPromptsResponse` | Context-aware prompt suggestions   |

### Stream event types (`AgentStreamEvent`)

`CONTENT_DELTA`, `THINKING_DELTA`, `TOOL_CALL_START`, `TOOL_CALL_COMPLETE`, `ARTIFACT_CREATED`, `TOOL_CONFIRMATION_REQUIRED`, `ERROR`, `COMPLETE`.

---

## LLM Configuration

Provider selection is config-driven (`llm/client.py`), and provider SDKs are imported lazily so only the selected provider needs to be installed.

| Variable                | Default              | Description                                          |
| ----------------------- | -------------------- | ---------------------------------------------------- |
| `AGENT_LLM_PROVIDER`    | `google`            | `google`/`gemini` or `anthropic`                     |
| `AGENT_LLM_MODEL`       | provider default    | Main chat model override                             |
| `AGENT_LLM_FAST_MODEL`  | provider default    | Fast/cheap model override                            |

| Provider    | Default chat model    | Default fast model         |
| ----------- | --------------------- | -------------------------- |
| `google`    | `gemini-2.5-flash`    | `gemini-2.5-flash-lite`    |
| `anthropic` | `claude-sonnet-5`     | `claude-haiku-4-5`         |

Chat calls use `max_tokens=4096`, `temperature=0.3` (lower for consistent DSL generation).

---

## Tools

The `ToolExecutor` registers 14 tools. Read tools run automatically; only `run_backtest` sets `requires_confirmation = True` (proposed, then user-approved). Tools call other services over Connect using an S2S service token that carries the caller's tenant/user (`tools/clients.py`).

| Tool                        | Group      | Confirm? | Description                                   |
| --------------------------- | ---------- | -------- | --------------------------------------------- |
| `list_strategies`           | strategy   | no       | List the tenant's strategies                  |
| `get_strategy`              | strategy   | no       | Fetch one strategy (incl. DSL)                |
| `list_templates`            | strategy   | no       | List public strategy templates               |
| `get_portfolio_summary`     | portfolio  | no       | Account/portfolio summary                     |
| `get_portfolio_performance` | portfolio  | no       | Portfolio performance metrics                 |
| `get_positions`             | portfolio  | no       | Current positions                             |
| `validate_dsl`              | validation | no       | Validate strategy DSL (success → artifact)    |
| `get_asset_info`            | validation | no       | Look up asset/symbol info                     |
| `get_backtest_results`      | backtest   | no       | Fetch a backtest's results                    |
| `list_backtests`            | backtest   | no       | List the tenant's backtests                   |
| `run_backtest`              | backtest   | **yes**  | Submit a real backtest job (proposed)         |
| `recall_memory`             | memory     | no       | Recall stored memory facts                    |
| `get_user_profile`          | memory     | no       | Derived user profile from memory              |
| `search_past_strategies`    | memory     | no       | Search the user's prior strategies            |

### Artifacts

When `validate_dsl` succeeds, the agent creates a **pending strategy artifact** (name/description parsed from the DSL) and emits `ARTIFACT_CREATED`. The user later calls `CommitArtifact` (with optional field overrides) to materialize it into a real strategy resource.

### Memory

After each turn, `AgentService` fire-and-forgets `extract_facts_heuristic` (regex patterns in `extraction_service.py`, base confidence ~0.7) over the *user's* message and stores facts in `agent_memory_facts` under a fresh `tenant_session`. A compact "memory hint" is injected into the system prompt for personalization. Extraction is heuristic/regex today — the LLM is not used to extract facts.

---

## Configuration

### Environment Variables

| Variable             | Required | Default              | Description                        |
| -------------------- | -------- | -------------------- | ---------------------------------- |
| `DATABASE_URL`       | Yes      | -                    | PostgreSQL connection string       |
| `JWT_SECRET`         | Yes      | -                    | Verifies inbound tokens (middleware) |
| `AGENT_LLM_PROVIDER` | No       | `google`             | LLM provider                       |
| `AGENT_LLM_MODEL`    | No       | provider default     | Chat model override                |
| `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` | Conditionally | - | Credentials for the selected provider |
| `CORS_ORIGINS`       | No       | localhost origins    | Allowed CORS origins               |

### Port Assignment

| Service | Port |
| ------- | ---- |
| Agent   | 8890 |

---

## Health Check

```http
GET /health
```

```json
{
  "status": "healthy",
  "service": "agent",
  "version": "0.1.0"
}
```

---

## Internal Service Connections

### Who Calls Agent Service

| Caller           | Methods Used                                              | Purpose                       |
| ---------------- | -------------------------------------------------------- | ----------------------------- |
| **Web Frontend** | All 10 RPCs                                               | Copilot chat, artifacts, prompts |

### What Agent Service Calls (S2S, service token + wire tenant/user)

| Target         | Via                    | Purpose                                      |
| -------------- | ---------------------- | -------------------------------------------- |
| **Strategy**   | `tools/strategy_tools` | List/get strategies, templates, validate DSL |
| **Portfolio**  | `tools/portfolio_tools`| Summary, performance, positions              |
| **Backtest**   | `tools/backtest_tools` | Get/list results, run backtests              |
| **PostgreSQL** | services layer         | Sessions, messages, artifacts, memory        |
| **LLM API**    | `llm/*`                | Gemini (default) or Anthropic                |

---

## Tenant Isolation

- **Fail-closed edge**: `AuthMiddleware` verifies the bearer token and stashes the principal (`current_context()`).
- **Verified identity**: every RPC derives `(tenant_id, user_id)` via `resolve_identity_connect(request.context)` (`_validate_tenant_context`), which rejects a wire tenant that doesn't match the token (`PERMISSION_DENIED`) and trusts the wire only for service tokens.
- **RLS**: all DB work runs inside `tenant_session(tenant_id)`, so Postgres row-level security scopes every query to the tenant. The fire-and-forget memory write opens its own `tenant_session` so the GUC is bound for the `agent_memory_facts` insert.
- **Outbound S2S** presents a service token and carries the caller's real tenant/user on the wire (`tools/clients.py`), which downstream services honor.

---

## Error Handling

- Connect RPCs use `@handle_service_errors` + `parse_uuid` (`grpc/error_handler.py`); typical codes: `INVALID_ARGUMENT` (bad/empty input), `NOT_FOUND` (session/artifact), `PERMISSION_DENIED` (forged tenant), `INTERNAL` (unexpected).
- Streaming RPCs (`StreamMessage`, `ConfirmToolCall`) surface errors as an `ERROR` stream event rather than aborting; unexpected exceptions are logged and reported as `Internal error: <type>`.
- History load failures degrade to empty history rather than failing the turn.

---

## Known Gaps

- **No Kubernetes manifest yet** — there is no `infrastructure/k8s/base/agent/` deployment, so the agent is not part of the staging deploy loop.
- **Memory extraction is regex-only** — `extraction_service.py` uses heuristic patterns; there is no LLM-based extraction or semantic memory search wired in.
- **Confirmation covers `run_backtest` only** — it is the sole registered write tool today; strategy/portfolio mutation tools are not registered.

---

## Summary

The Agent Service is a real, streaming AI Copilot exposed over 10 Connect RPCs on port 8890. It runs an agentic tool loop (up to 10 iterations) over 14 strategy/portfolio/backtest/validation/memory tools, defaulting to Google Gemini (`gemini-2.5-flash`) with an Anthropic (`claude-sonnet-5`) fallback selectable via `AGENT_LLM_PROVIDER`. Natural-language requests become validated DSL surfaced as a pending artifact the user commits into a real strategy; write actions (currently `run_backtest`) are proposed and require explicit `ConfirmToolCall` approval. Conversations, artifacts, and per-user memory facts persist in PostgreSQL, and every call is tenant-isolated via `resolve_identity_connect` plus RLS `tenant_session`.
