/**
 * Agent Store - manages AI Copilot chat state.
 *
 * Handles:
 * - Session management (create, load, list, delete)
 * - Message streaming with tool execution visibility
 * - Pending artifact management and commit
 * - Suggested prompts based on UI context
 */

import { create as createMessage } from '@bufbuild/protobuf';
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import {
  AgentContextDataSchema,
  AgentMessage,
  MessageRole,
  PendingArtifact,
  StreamEventType,
} from '../generated/proto/agent_pb';
import { agentClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

// =============================================================================
// Types
// =============================================================================

interface ToolCallStatus {
  name: string;
  status: 'running' | 'complete' | 'error';
  resultPreview?: string;
}

interface AgentState {
  // Current session (for analytics - not loaded from history)
  currentSessionId: string | null;
  messages: AgentMessage[];
  pendingArtifacts: PendingArtifact[];

  // Streaming state
  isStreaming: boolean;
  streamingContent: string;
  currentToolCall: ToolCallStatus | null;
  /** Artifact IDs created during current streaming message */
  pendingArtifactIdsForCurrentMessage: string[];

  // UI state
  isOpen: boolean;
  suggestedPrompts: string[];

  // Error state
  error: string | null;
  loading: boolean;
  serviceUnavailable: boolean;

  // Actions
  openChat: () => void;
  closeChat: () => void;
  toggleChat: () => void;

  sendMessage: (content: string, strategyDSL?: string, strategyName?: string, page?: string) => Promise<void>;
  dismissArtifact: (artifactId: string) => void;

  getSuggestedPrompts: (uiContext: UIContext) => Promise<void>;

  clearError: () => void;
  reset: () => void;
}

interface UIContext {
  page?: string;
  strategyId?: string;
  backtestId?: string;
}

// =============================================================================
// Store
// =============================================================================

export const useAgentStore = create<AgentState>()(
  persist(
    (set, get) => ({
      // Initial state
      currentSessionId: null,
      messages: [],
      pendingArtifacts: [],

      isStreaming: false,
      streamingContent: '',
      currentToolCall: null,
      pendingArtifactIdsForCurrentMessage: [],

      isOpen: false,
      suggestedPrompts: [],

      error: null,
      loading: false,
      serviceUnavailable: false,

      // UI actions
      openChat: () => {
        // Start fresh each time dialog opens
        set({
          isOpen: true,
          messages: [],
          pendingArtifacts: [],
          currentSessionId: null,
          error: null,
          streamingContent: '',
          currentToolCall: null,
        });
      },
      closeChat: () => set({ isOpen: false }),
      toggleChat: () => {
        const { isOpen } = get();
        if (!isOpen) {
          // Opening - start fresh
          set({
            isOpen: true,
            messages: [],
            pendingArtifacts: [],
            currentSessionId: null,
            error: null,
            streamingContent: '',
            currentToolCall: null,
          });
        } else {
          set({ isOpen: false });
        }
      },

      // Messaging - each message creates/uses a session for analytics (but no history loading)
      sendMessage: async (content: string, strategyDSL?: string, strategyName?: string, page?: string) => {
        let { currentSessionId } = get();
        const context = getTenantContext();

        if (!context) {
          set({ error: 'Please log in to use Copilot' });
          return;
        }

        // Create session if none exists (for analytics tracking)
        if (!currentSessionId) {
          try {
            const response = await agentClient.createSession({
              context,
              initialMessage: '',
              uiContext: createMessage(AgentContextDataSchema, {
                page: page || '',
                strategyId: '',
                backtestId: '',
              }),
            });

            const session = response.session;
            if (!session) {
              set({ error: 'Failed to create session', loading: false });
              return;
            }
            currentSessionId = session.id;
            set({ currentSessionId: session.id });
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Failed to create session';
            if (message.includes('Failed to fetch') || message.includes('fetch')) {
              set({ serviceUnavailable: true, loading: false, error: null });
            } else {
              set({ error: message, loading: false });
            }
            return;
          }
        }

        // Add user message optimistically
        const userMessage: AgentMessage = {
          $typeName: 'llamatrade.AgentMessage',
          id: `temp-${Date.now()}`,
          sessionId: currentSessionId,
          role: MessageRole.USER,
          content,
          toolCalls: [],
          createdAt: { $typeName: 'llamatrade.Timestamp', seconds: BigInt(Math.floor(Date.now() / 1000)), nanos: 0 },
          inlineArtifactIds: [],
        };

        set((state) => ({
          messages: [...state.messages, userMessage],
          isStreaming: true,
          streamingContent: '',
          currentToolCall: null,
          pendingArtifactIdsForCurrentMessage: [],
          error: null,
        }));

        try {
          // Use streaming API with strategy context
          const stream = agentClient.streamMessage({
            context,
            sessionId: currentSessionId,
            content,
            strategyDsl: strategyDSL || '',
            strategyName: strategyName || '',
            uiContext: createMessage(AgentContextDataSchema, {
              page: page || '',
              strategyId: '',
              backtestId: '',
            }),
          });

          let accumulatedContent = '';

          for await (const event of stream) {
            switch (event.eventType) {
              case StreamEventType.CONTENT_DELTA:
                accumulatedContent += event.contentDelta;
                set({ streamingContent: accumulatedContent });
                break;

              case StreamEventType.TOOL_CALL_START:
                set({
                  currentToolCall: {
                    name: event.toolName,
                    status: 'running',
                  },
                });
                break;

              case StreamEventType.TOOL_CALL_COMPLETE:
                set({
                  currentToolCall: {
                    name: event.toolName,
                    status: 'complete',
                    resultPreview: event.toolResultPreview,
                  },
                });
                // Clear after a brief moment
                setTimeout(() => {
                  set({ currentToolCall: null });
                }, 1000);
                break;

              case StreamEventType.ARTIFACT_CREATED: {
                const artifact = event.artifact;
                if (artifact) {
                  set((state) => ({
                    pendingArtifacts: [...state.pendingArtifacts, artifact],
                    // Track artifact ID for linking to the current message
                    pendingArtifactIdsForCurrentMessage: [
                      ...state.pendingArtifactIdsForCurrentMessage,
                      artifact.id,
                    ],
                  }));
                }
                break;
              }

              case StreamEventType.ERROR:
                set({
                  error: event.errorMessage || 'An error occurred',
                  isStreaming: false,
                });
                return;

              case StreamEventType.COMPLETE: {
                // Get artifact IDs collected during this message's streaming
                const artifactIds = get().pendingArtifactIdsForCurrentMessage;

                // Add the complete assistant message with linked artifacts
                // sessionId is guaranteed to exist - we create one at the start if needed
                const sessionIdForMessage = currentSessionId ?? '';
                const assistantMessage: AgentMessage = {
                  $typeName: 'llamatrade.AgentMessage',
                  id: event.messageId || `assistant-${Date.now()}`,
                  sessionId: sessionIdForMessage,
                  role: MessageRole.ASSISTANT,
                  content: accumulatedContent,
                  toolCalls: [],
                  createdAt: { $typeName: 'llamatrade.Timestamp', seconds: BigInt(Math.floor(Date.now() / 1000)), nanos: 0 },
                  inlineArtifactIds: artifactIds,
                };

                set({
                  messages: [...get().messages, assistantMessage],
                  isStreaming: false,
                  streamingContent: '',
                  currentToolCall: null,
                  pendingArtifactIdsForCurrentMessage: [],
                });
                break;
              }
            }
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Failed to send message';
          set({
            error: message,
            isStreaming: false,
            streamingContent: '',
            currentToolCall: null,
          });
        }
      },

      dismissArtifact: (artifactId: string) => {
        set((state) => ({
          pendingArtifacts: state.pendingArtifacts.filter((a) => a.id !== artifactId),
        }));
      },

      // Suggestions
      getSuggestedPrompts: async (uiContext: UIContext) => {
        const context = getTenantContext();
        if (!context) return;

        try {
          const response = await agentClient.getSuggestedPrompts({
            context,
            uiContext: createMessage(AgentContextDataSchema, {
              page: uiContext.page || '',
              strategyId: uiContext.strategyId || '',
              backtestId: uiContext.backtestId || '',
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
          streamingContent: '',
          currentToolCall: null,
          pendingArtifactIdsForCurrentMessage: [],
          suggestedPrompts: [],
          error: null,
          loading: false,
        }),
    }),
    {
      name: 'llamatrade-agent',
      partialize: () => ({
        // Don't persist anything - each dialog open starts fresh
      }),
    }
  )
);

// =============================================================================
// Re-exports for convenience
// =============================================================================

export { MessageRole, StreamEventType, ArtifactType } from '../generated/proto/agent_pb';
export type { AgentMessage, PendingArtifact } from '../generated/proto/agent_pb';
