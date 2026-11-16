/**
 * Agent Store - manages AI Copilot chat state.
 *
 * Handles:
 * - Session management (list real sessions, load a session's history, start new)
 * - Message streaming with tool execution visibility
 * - Pending artifact management
 * - Suggested prompts based on UI context
 * - Seed handoff (openSeededChat) from the New Strategy console / dashboard hero
 */

import { create as createMessage } from "@bufbuild/protobuf";
import { Code, ConnectError } from "@connectrpc/connect";
import { create } from "zustand";

import { agentClient, getTenantContext } from "../net";
import {
  AgentContextDataSchema,
  AgentMessage,
  AgentSession,
  AgentStreamEvent,
  MessageRole,
  PendingArtifact,
  StreamEventType,
} from "../proto/agent_pb";

interface ToolCallStatus {
  name: string;
  status: "running" | "complete" | "error";
  resultPreview?: string;
}

/** A write action the agent has proposed and is awaiting the user to approve. */
export interface PendingConfirmation {
  toolName: string;
  argumentsJson: string;
  confirmationId: string;
}

export type ConfirmationDecision = "approved" | "declined" | "change";

/** A proposal the user answered, kept so its card stays in the thread. */
export interface ResolvedConfirmation extends PendingConfirmation {
  decision: ConfirmationDecision;
  /** The message the card followed when it was answered; null at the top of the thread. */
  afterMessageId: string | null;
}

/** Composer text placed after "Change" so the user can say what to change. */
export const CHANGE_PROMPT = "Change the settings: ";

/** True when the Copilot service itself can't be reached, as opposed to a request failing. */
export function isServiceUnavailable(error: unknown): boolean {
  if (error instanceof ConnectError) {
    return (
      error.code === Code.Unavailable || /fetch|network/i.test(error.rawMessage)
    );
  }
  if (error instanceof TypeError) return /fetch|network/i.test(error.message);
  return (
    error instanceof Error &&
    /failed to fetch|networkerror/i.test(error.message)
  );
}

interface AgentState {
  // Active conversation
  currentSessionId: string | null;
  messages: AgentMessage[];
  pendingArtifacts: PendingArtifact[];

  // Conversation history (sidebar)
  sessions: AgentSession[];
  sessionsLoading: boolean;

  // Streaming state
  isStreaming: boolean;
  streamingContent: string;
  /** Curated reasoning streamed for the in-progress turn (shown in a collapsible block). */
  thinkingContent: string;
  currentToolCall: ToolCallStatus | null;
  /** Artifact IDs created during current streaming message */
  pendingArtifactIdsForCurrentMessage: string[];
  /** A proposed write action awaiting the user's approval (null when none). */
  pendingConfirmation: PendingConfirmation | null;
  /** Proposals answered in this thread, in order. */
  resolvedConfirmations: ResolvedConfirmation[];

  // UI state
  /** Prompt to prefill the composer with (e.g. from the New Strategy console). */
  seedPrompt: string;
  suggestedPrompts: string[];
  /** Overlay side-panel ("quick ask") visibility. Shares all conversation state
   *  with the full-page /copilot view. */
  panelOpen: boolean;

  // Error state
  error: string | null;
  loading: boolean;
  serviceUnavailable: boolean;

  // Actions
  /** Start a fresh conversation (used by "+ NEW"). */
  startNewChat: () => void;
  /** Alias of startNewChat kept for existing callers. */
  openChat: () => void;
  /** Start a fresh conversation with the composer prefilled by `seedPrompt`. */
  openSeededChat: (seedPrompt: string) => void;
  /** Clear the one-shot seed prompt once the composer has consumed it. */
  clearSeedPrompt: () => void;

  /** Open / close / toggle the overlay side-panel Copilot. */
  openPanel: () => void;
  closePanel: () => void;
  togglePanel: () => void;

  /** Fetch the tenant's real Copilot sessions for the sidebar. */
  loadSessions: () => Promise<void>;
  /** Load a session's message history + pending artifacts into the thread. */
  selectSession: (sessionId: string) => Promise<void>;
  /** Permanently delete a conversation (and its messages/artifacts). */
  deleteSession: (sessionId: string) => Promise<void>;

  sendMessage: (
    content: string,
    strategyDSL?: string,
    strategyName?: string,
    page?: string,
  ) => Promise<void>;
  dismissArtifact: (artifactId: string) => void;
  /** Commit a pending strategy artifact into a real strategy (server-side). Returns the new strategy id. */
  commitArtifact: (artifactId: string) => Promise<string | null>;
  /**
   * Approve or deny the pending proposed write action, resuming the agent turn. "change" declines
   * it and puts CHANGE_PROMPT in the composer so the user can say what to change.
   */
  confirmToolCall: (
    approved: boolean,
    decision?: ConfirmationDecision,
  ) => Promise<void>;

  getSuggestedPrompts: (uiContext: UIContext) => Promise<void>;

  clearError: () => void;
  reset: () => void;
}

interface UIContext {
  page?: string;
  strategyId?: string;
  backtestId?: string;
}

/** Fresh conversation state used whenever a new chat is started. */
function freshChatSession(seedPrompt: string): Partial<AgentState> {
  return {
    seedPrompt,
    messages: [],
    pendingArtifacts: [],
    currentSessionId: null,
    error: null,
    isStreaming: false,
    streamingContent: "",
    thinkingContent: "",
    currentToolCall: null,
    pendingArtifactIdsForCurrentMessage: [],
    pendingConfirmation: null,
    resolvedConfirmations: [],
  };
}

/**
 * Consume a server-streamed agent turn (from streamMessage or confirmToolCall),
 * driving streaming/tool/artifact/confirmation state and appending the final
 * assistant message on COMPLETE. Shared so both entry points behave identically.
 */
async function consumeAgentStream(
  stream: AsyncIterable<AgentStreamEvent>,
  sessionId: string,
): Promise<void> {
  const { setState, getState } = useAgentStore;
  let accumulatedContent = "";
  let accumulatedThinking = "";

  for await (const event of stream) {
    switch (event.eventType) {
      case StreamEventType.THINKING_DELTA:
        accumulatedThinking += event.thinkingDelta;
        setState({ thinkingContent: accumulatedThinking });
        break;

      case StreamEventType.CONTENT_DELTA:
        accumulatedContent += event.contentDelta;
        setState({ streamingContent: accumulatedContent });
        break;

      case StreamEventType.TOOL_CALL_START:
        setState({
          currentToolCall: { name: event.toolName, status: "running" },
        });
        break;

      case StreamEventType.TOOL_CALL_COMPLETE:
        setState({
          currentToolCall: {
            name: event.toolName,
            status: "complete",
            resultPreview: event.toolResultPreview,
          },
        });
        setTimeout(() => setState({ currentToolCall: null }), 1000);
        break;

      case StreamEventType.ARTIFACT_CREATED: {
        const artifact = event.artifact;
        if (artifact) {
          setState((state) => ({
            pendingArtifacts: [...state.pendingArtifacts, artifact],
            pendingArtifactIdsForCurrentMessage: [
              ...state.pendingArtifactIdsForCurrentMessage,
              artifact.id,
            ],
          }));
        }
        break;
      }

      case StreamEventType.TOOL_CONFIRMATION_REQUIRED:
        setState({
          pendingConfirmation: {
            toolName: event.toolName,
            argumentsJson: event.toolArgumentsJson,
            confirmationId: event.confirmationId,
          },
        });
        break;

      case StreamEventType.ERROR:
        setState({
          error: event.errorMessage || "An error occurred",
          isStreaming: false,
        });
        return;

      case StreamEventType.COMPLETE: {
        const artifactIds = getState().pendingArtifactIdsForCurrentMessage;
        const assistantMessage: AgentMessage = {
          $typeName: "llamatrade.AgentMessage",
          id: event.messageId || `assistant-${Date.now()}`,
          sessionId,
          role: MessageRole.ASSISTANT,
          content: accumulatedContent,
          toolCalls: [],
          createdAt: {
            $typeName: "llamatrade.Timestamp",
            seconds: BigInt(Math.floor(Date.now() / 1000)),
            nanos: 0,
          },
          inlineArtifactIds: artifactIds,
          thinking: accumulatedThinking,
        };
        setState((state) => ({
          messages: [...state.messages, assistantMessage],
          isStreaming: false,
          streamingContent: "",
          thinkingContent: "",
          currentToolCall: null,
          pendingArtifactIdsForCurrentMessage: [],
        }));
        break;
      }
    }
  }
}

export const useAgentStore = create<AgentState>()((set, get) => ({
  // Initial state
  currentSessionId: null,
  messages: [],
  pendingArtifacts: [],

  sessions: [],
  sessionsLoading: false,

  isStreaming: false,
  streamingContent: "",
  thinkingContent: "",
  currentToolCall: null,
  pendingArtifactIdsForCurrentMessage: [],
  pendingConfirmation: null,
  resolvedConfirmations: [],

  seedPrompt: "",
  suggestedPrompts: [],
  panelOpen: false,

  error: null,
  loading: false,
  serviceUnavailable: false,

  // Conversation lifecycle
  startNewChat: () => set(freshChatSession("")),
  openChat: () => set(freshChatSession("")),
  openSeededChat: (seedPrompt: string) => set(freshChatSession(seedPrompt)),
  clearSeedPrompt: () => set({ seedPrompt: "" }),

  // Overlay side-panel visibility (conversation state is shared, untouched).
  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),
  togglePanel: () => set((state) => ({ panelOpen: !state.panelOpen })),

  loadSessions: async () => {
    const context = getTenantContext();
    if (!context) return;

    set({ sessionsLoading: true });
    try {
      const response = await agentClient.listSessions({ context });
      // Newest activity first.
      const sessions = [...response.sessions].sort(
        (a, b) =>
          Number(b.lastActivityAt?.seconds ?? 0n) -
          Number(a.lastActivityAt?.seconds ?? 0n),
      );
      set({ sessions, sessionsLoading: false, serviceUnavailable: false });
    } catch (error) {
      set({
        sessionsLoading: false,
        serviceUnavailable: isServiceUnavailable(error),
      });
    }
  },

  selectSession: async (sessionId: string) => {
    const context = getTenantContext();
    if (!context) return;

    if (get().currentSessionId === sessionId && get().messages.length > 0)
      return;

    set({
      loading: true,
      error: null,
      seedPrompt: "",
      streamingContent: "",
      thinkingContent: "",
      currentToolCall: null,
      isStreaming: false,
    });
    try {
      const response = await agentClient.getSession({
        context,
        sessionId,
        includeMessages: true,
        messageLimit: 200,
      });
      set({
        currentSessionId: sessionId,
        messages: response.messages,
        pendingArtifacts: response.pendingArtifacts,
        pendingArtifactIdsForCurrentMessage: [],
        pendingConfirmation: null,
        resolvedConfirmations: [],
        loading: false,
        serviceUnavailable: false,
      });
    } catch (error) {
      if (isServiceUnavailable(error)) {
        set({ serviceUnavailable: true, loading: false });
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load conversation";
      set({ error: message, loading: false });
    }
  },

  deleteSession: async (sessionId: string) => {
    const context = getTenantContext();
    if (!context) return;

    // Optimistically drop from the sidebar; if it was open, reset the thread.
    const previousSessions = get().sessions;
    const wasActive = get().currentSessionId === sessionId;
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== sessionId),
      ...(wasActive ? freshChatSession("") : {}),
    }));

    try {
      await agentClient.deleteSession({ context, sessionId });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Failed to delete conversation";
      set({ sessions: previousSessions, error: message });
    }
  },

  // Messaging - each message creates/uses a session (persisted server-side).
  sendMessage: async (
    content: string,
    strategyDSL?: string,
    strategyName?: string,
    page?: string,
  ) => {
    let { currentSessionId } = get();
    const context = getTenantContext();

    if (!context) {
      set({ error: "Please log in to use Copilot" });
      return;
    }

    // Create session if none exists (fresh conversation).
    if (!currentSessionId) {
      try {
        const response = await agentClient.createSession({
          context,
          initialMessage: "",
          uiContext: createMessage(AgentContextDataSchema, {
            page: page || "",
            strategyId: "",
            backtestId: "",
          }),
        });

        const session = response.session;
        if (!session) {
          set({ error: "Failed to create session", loading: false });
          return;
        }
        currentSessionId = session.id;
        set({ currentSessionId: session.id });
      } catch (error) {
        if (isServiceUnavailable(error)) {
          set({ serviceUnavailable: true, loading: false, error: null });
        } else {
          const message =
            error instanceof Error ? error.message : "Failed to create session";
          set({ error: message, loading: false });
        }
        return;
      }
    }

    // Add user message optimistically
    const userMessage: AgentMessage = {
      $typeName: "llamatrade.AgentMessage",
      id: `temp-${Date.now()}`,
      sessionId: currentSessionId,
      role: MessageRole.USER,
      content,
      toolCalls: [],
      createdAt: {
        $typeName: "llamatrade.Timestamp",
        seconds: BigInt(Math.floor(Date.now() / 1000)),
        nanos: 0,
      },
      inlineArtifactIds: [],
      thinking: "",
    };

    set((state) => ({
      messages: [...state.messages, userMessage],
      isStreaming: true,
      streamingContent: "",
      thinkingContent: "",
      currentToolCall: null,
      pendingArtifactIdsForCurrentMessage: [],
      pendingConfirmation: null,
      error: null,
    }));

    try {
      // Use streaming API with strategy context
      const stream = agentClient.streamMessage({
        context,
        sessionId: currentSessionId,
        content,
        strategyDsl: strategyDSL || "",
        strategyName: strategyName || "",
        uiContext: createMessage(AgentContextDataSchema, {
          page: page || "",
          strategyId: "",
          backtestId: "",
        }),
      });

      await consumeAgentStream(stream, currentSessionId);
    } catch (error) {
      const unavailable = isServiceUnavailable(error);
      const message =
        error instanceof Error ? error.message : "Failed to send message";
      set({
        error: unavailable ? null : message,
        serviceUnavailable: unavailable || get().serviceUnavailable,
        isStreaming: false,
        streamingContent: "",
        thinkingContent: "",
        currentToolCall: null,
      });
    }
  },

  dismissArtifact: (artifactId: string) => {
    set((state) => ({
      pendingArtifacts: state.pendingArtifacts.filter(
        (a) => a.id !== artifactId,
      ),
    }));
  },

  commitArtifact: async (artifactId: string) => {
    const context = getTenantContext();
    if (!context) {
      set({ error: "Please log in to save strategies" });
      return null;
    }

    try {
      const response = await agentClient.commitArtifact({
        context,
        artifactId,
      });
      if (!response.success) return null;

      // Flip the local artifact to committed so its card shows "Saved" and
      // the Backtest action can target the real strategy.
      set((state) => ({
        pendingArtifacts: state.pendingArtifacts.map((a) =>
          a.id === artifactId
            ? {
                ...a,
                isCommitted: true,
                committedResourceId: response.resourceId,
              }
            : a,
        ),
      }));
      return response.resourceId;
    } catch {
      // Failure is surfaced contextually on the artifact card (retry), not
      // as a global conversation-level error.
      return null;
    }
  },

  confirmToolCall: async (
    approved: boolean,
    decision: ConfirmationDecision = approved ? "approved" : "declined",
  ) => {
    const context = getTenantContext();
    const pending = get().pendingConfirmation;
    const sessionId = get().currentSessionId;
    if (!context || !pending || !sessionId) return;

    const messages = get().messages;
    const resolved: ResolvedConfirmation = {
      ...pending,
      decision: approved ? "approved" : decision,
      afterMessageId: messages.length ? messages[messages.length - 1].id : null,
    };
    set((state) => ({
      resolvedConfirmations: [...state.resolvedConfirmations, resolved],
      seedPrompt:
        resolved.decision === "change" ? CHANGE_PROMPT : state.seedPrompt,
    }));

    set({
      pendingConfirmation: null,
      isStreaming: true,
      streamingContent: "",
      thinkingContent: "",
      currentToolCall: null,
      pendingArtifactIdsForCurrentMessage: [],
      error: null,
    });

    try {
      const stream = agentClient.confirmToolCall({
        context,
        sessionId,
        confirmationId: pending.confirmationId,
        toolName: pending.toolName,
        toolArgumentsJson: pending.argumentsJson,
        approved,
      });
      await consumeAgentStream(stream, sessionId);
    } catch (error) {
      const unavailable = isServiceUnavailable(error);
      const message =
        error instanceof Error ? error.message : "Failed to confirm action";
      set({
        error: unavailable ? null : message,
        serviceUnavailable: unavailable || get().serviceUnavailable,
        isStreaming: false,
        streamingContent: "",
        thinkingContent: "",
        currentToolCall: null,
      });
    }
  },

  // Suggestions
  getSuggestedPrompts: async (uiContext: UIContext) => {
    const context = getTenantContext();
    if (!context) return;

    try {
      const response = await agentClient.getSuggestedPrompts({
        context,
        uiContext: createMessage(AgentContextDataSchema, {
          page: uiContext.page || "",
          strategyId: uiContext.strategyId || "",
          backtestId: uiContext.backtestId || "",
        }),
      });

      set({ suggestedPrompts: response.prompts });
    } catch {
      // Silently fail - suggestions are not critical
      set({ suggestedPrompts: [] });
    }
  },

  // Utility
  clearError: () => set({ error: null }),

  reset: () =>
    set({
      currentSessionId: null,
      messages: [],
      pendingArtifacts: [],
      isStreaming: false,
      streamingContent: "",
      thinkingContent: "",
      currentToolCall: null,
      pendingArtifactIdsForCurrentMessage: [],
      pendingConfirmation: null,
      resolvedConfirmations: [],
      seedPrompt: "",
      suggestedPrompts: [],
      error: null,
      loading: false,
    }),
}));

export {
  MessageRole,
  StreamEventType,
  ArtifactType,
  AgentSessionStatus,
} from "../proto/agent_pb";
export type {
  AgentMessage,
  AgentSession,
  PendingArtifact,
} from "../proto/agent_pb";
