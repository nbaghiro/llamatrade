/**
 * Agent (Copilot) store — mirrors apps/web/src/store/agent.ts.
 *
 * Real backend: listSessions / getSession / createSession / streamMessage /
 * commitArtifact. Streaming events drive the thread:
 *   CONTENT_DELTA → live text · TOOL_CALL_* → tool trace ·
 *   ARTIFACT_CREATED → inline draft card · ERROR · COMPLETE → finalize message.
 *
 * Messages are kept as a lightweight view-model (ChatMessage) so rendering
 * doesn't fight proto $typeName; server AgentMessages are mapped on load.
 */
import { ConnectError } from '@connectrpc/connect';
import { create } from 'zustand';

import {
  AgentSessionStatus,
  MessageRole,
  StreamEventType,
  type AgentSession,
  type PendingArtifact,
} from '@llamatrade/core/proto/agent_pb';
import type { Timestamp } from '@llamatrade/core/proto/common_pb';
import { agentClient } from '../net/clients';
import { tenantContext } from './auth';

export { AgentSessionStatus };
export type { AgentSession, PendingArtifact };

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timeMs: number;
  artifactIds: string[];
}

export interface LiveToolCall {
  name: string;
  status: 'running' | 'complete' | 'error';
  resultPreview?: string;
}

function tsToMs(ts?: Timestamp): number {
  const s = ts?.seconds;
  return s ? Number(s) * 1000 : Date.now();
}

function errMsg(e: unknown): string {
  if (e instanceof ConnectError) return e.rawMessage || e.message;
  return e instanceof Error ? e.message : 'Something went wrong';
}

/** fetch-layer failures (backend unreachable) read differently from RPC errors. */
function isConnectivity(e: unknown): boolean {
  const m = e instanceof Error ? e.message : String(e);
  return m.includes('fetch') || m.includes('Failed to fetch') || m.toLowerCase().includes('network');
}

interface AgentState {
  currentSessionId: string | null;
  messages: ChatMessage[];
  pendingArtifacts: PendingArtifact[];

  sessions: AgentSession[];
  sessionsLoading: boolean;

  isStreaming: boolean;
  streamingContent: string;
  currentToolCall: LiveToolCall | null;
  artifactIdsForCurrent: string[];

  suggestedPrompts: string[];
  loading: boolean;
  error: string | null;
  serviceUnavailable: boolean;

  startNewChat: () => void;
  loadSessions: () => Promise<void>;
  selectSession: (id: string) => Promise<void>;
  sendMessage: (content: string, page?: string) => Promise<void>;
  commitArtifact: (id: string) => Promise<void>;
  dismissArtifact: (id: string) => void;
  getSuggestedPrompts: (page: string) => Promise<void>;
  clearError: () => void;
}

export const useAgentStore = create<AgentState>((set, get) => ({
  currentSessionId: null,
  messages: [],
  pendingArtifacts: [],
  sessions: [],
  sessionsLoading: false,
  isStreaming: false,
  streamingContent: '',
  currentToolCall: null,
  artifactIdsForCurrent: [],
  suggestedPrompts: [],
  loading: false,
  error: null,
  serviceUnavailable: false,

  startNewChat: () =>
    set({
      currentSessionId: null,
      messages: [],
      pendingArtifacts: [],
      isStreaming: false,
      streamingContent: '',
      currentToolCall: null,
      artifactIdsForCurrent: [],
      error: null,
    }),

  loadSessions: async () => {
    const context = tenantContext();
    if (!context) return;
    set({ sessionsLoading: true });
    try {
      const res = await agentClient.listSessions({ context });
      const sessions = [...res.sessions].sort(
        (a, b) => tsToMs(b.lastActivityAt) - tsToMs(a.lastActivityAt),
      );
      set({ sessions, sessionsLoading: false, serviceUnavailable: false });
    } catch (e) {
      set({ sessionsLoading: false, serviceUnavailable: isConnectivity(e) });
    }
  },

  selectSession: async (sessionId) => {
    const context = tenantContext();
    if (!context) return;
    if (get().currentSessionId === sessionId && get().messages.length > 0) return;

    set({ loading: true, error: null, streamingContent: '', currentToolCall: null, isStreaming: false });
    try {
      const res = await agentClient.getSession({
        context,
        sessionId,
        includeMessages: true,
        messageLimit: 200,
      });
      set({
        currentSessionId: sessionId,
        messages: res.messages.map((m) => ({
          id: m.id,
          role: m.role === MessageRole.USER ? 'user' : 'assistant',
          content: m.content,
          timeMs: tsToMs(m.createdAt),
          artifactIds: m.inlineArtifactIds,
        })),
        pendingArtifacts: res.pendingArtifacts,
        artifactIdsForCurrent: [],
        loading: false,
        serviceUnavailable: false,
      });
    } catch (e) {
      set({ error: errMsg(e), loading: false });
    }
  },

  sendMessage: async (content, page) => {
    let { currentSessionId } = get();
    const context = tenantContext();
    if (!context) {
      set({ error: 'Please sign in to use Copilot' });
      return;
    }

    // Create the session on first message.
    if (!currentSessionId) {
      try {
        const res = await agentClient.createSession({
          context,
          initialMessage: '',
          uiContext: { page: page ?? '', strategyId: '', backtestId: '' },
        });
        if (!res.session) {
          set({ error: 'Failed to create session' });
          return;
        }
        currentSessionId = res.session.id;
        set({ currentSessionId });
      } catch (e) {
        if (isConnectivity(e)) set({ serviceUnavailable: true });
        else set({ error: errMsg(e) });
        return;
      }
    }

    const userMsg: ChatMessage = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content,
      timeMs: Date.now(),
      artifactIds: [],
    };
    set((s) => ({
      messages: [...s.messages, userMsg],
      isStreaming: true,
      streamingContent: '',
      currentToolCall: null,
      artifactIdsForCurrent: [],
      error: null,
    }));

    try {
      const stream = agentClient.streamMessage({
        context,
        sessionId: currentSessionId,
        content,
        strategyDsl: '',
        strategyName: '',
        uiContext: { page: page ?? '', strategyId: '', backtestId: '' },
      });

      let acc = '';
      for await (const ev of stream) {
        switch (ev.eventType) {
          case StreamEventType.CONTENT_DELTA:
            acc += ev.contentDelta;
            set({ streamingContent: acc });
            break;
          case StreamEventType.TOOL_CALL_START:
            set({ currentToolCall: { name: ev.toolName, status: 'running' } });
            break;
          case StreamEventType.TOOL_CALL_COMPLETE:
            set({ currentToolCall: { name: ev.toolName, status: 'complete', resultPreview: ev.toolResultPreview } });
            setTimeout(() => {
              if (get().currentToolCall?.name === ev.toolName) set({ currentToolCall: null });
            }, 1200);
            break;
          case StreamEventType.ARTIFACT_CREATED:
            if (ev.artifact) {
              const artifact = ev.artifact;
              set((s) => ({
                pendingArtifacts: [...s.pendingArtifacts, artifact],
                artifactIdsForCurrent: [...s.artifactIdsForCurrent, artifact.id],
              }));
            }
            break;
          case StreamEventType.ERROR:
            set({ error: ev.errorMessage || 'The Copilot hit an error', isStreaming: false, streamingContent: '' });
            return;
          case StreamEventType.COMPLETE: {
            const artifactIds = get().artifactIdsForCurrent;
            const assistant: ChatMessage = {
              id: ev.messageId || `assistant-${Date.now()}`,
              role: 'assistant',
              content: acc,
              timeMs: Date.now(),
              artifactIds,
            };
            set((s) => ({
              messages: [...s.messages, assistant],
              isStreaming: false,
              streamingContent: '',
              currentToolCall: null,
              artifactIdsForCurrent: [],
            }));
            break;
          }
        }
      }
    } catch (e) {
      set({ error: errMsg(e), isStreaming: false, streamingContent: '', currentToolCall: null });
    }
  },

  commitArtifact: async (artifactId) => {
    const context = tenantContext();
    if (!context) return;
    try {
      const res = await agentClient.commitArtifact({ context, artifactId, overrides: {} });
      if (res.success) {
        set((s) => ({
          pendingArtifacts: s.pendingArtifacts.map((a) =>
            a.id === artifactId ? { ...a, isCommitted: true, committedResourceId: res.resourceId } : a,
          ),
        }));
      }
    } catch (e) {
      set({ error: errMsg(e) });
    }
  },

  dismissArtifact: (id) =>
    set((s) => ({ pendingArtifacts: s.pendingArtifacts.filter((a) => a.id !== id) })),

  getSuggestedPrompts: async (page) => {
    const context = tenantContext();
    if (!context) return;
    try {
      const res = await agentClient.getSuggestedPrompts({
        context,
        uiContext: { page, strategyId: '', backtestId: '' },
      });
      set({ suggestedPrompts: res.prompts });
    } catch {
      set({ suggestedPrompts: [] });
    }
  },

  clearError: () => set({ error: null }),
}));
