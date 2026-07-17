/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The shared agent store (in @llamatrade/core) reads agentClient + getTenantContext
// from @llamatrade/core/net; mock that one module for both.
const { commitArtifact, deleteSession, confirmToolCall } = vi.hoisted(() => ({
  commitArtifact: vi.fn(),
  deleteSession: vi.fn(),
  confirmToolCall: vi.fn(),
}));

vi.mock('@llamatrade/core/net', () => ({
  agentClient: { commitArtifact, deleteSession, confirmToolCall },
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

import { StreamEventType } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';

async function* completeStream() {
  yield { eventType: StreamEventType.COMPLETE, messageId: 'm1', contentDelta: '' } as never;
}

async function* thinkingStream() {
  yield { eventType: StreamEventType.THINKING_DELTA, thinkingDelta: 'Weighing ' } as never;
  yield { eventType: StreamEventType.THINKING_DELTA, thinkingDelta: 'the tradeoff.' } as never;
  yield { eventType: StreamEventType.CONTENT_DELTA, contentDelta: 'Here is the plan.' } as never;
  yield { eventType: StreamEventType.COMPLETE, messageId: 'm2', contentDelta: '' } as never;
}

type Artifact = ReturnType<typeof useAgentStore.getState>['pendingArtifacts'][number];
type Session = ReturnType<typeof useAgentStore.getState>['sessions'][number];

function artifact(id: string): Artifact {
  return { id, isCommitted: false } as unknown as Artifact;
}

function session(id: string): Session {
  return { id } as unknown as Session;
}

const CONTEXT = { context: { tenantId: 't1', userId: 'u1' } };

describe('commitArtifact', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAgentStore.setState({ pendingArtifacts: [artifact('a1')], error: null });
  });

  it('flips the artifact to committed and returns the new strategy id', async () => {
    commitArtifact.mockResolvedValue({ success: true, resourceId: 'strat-1', resourceType: 'strategy' });

    const id = await useAgentStore.getState().commitArtifact('a1');

    expect(commitArtifact).toHaveBeenCalledWith({ ...CONTEXT, artifactId: 'a1' });
    expect(id).toBe('strat-1');
    const updated = useAgentStore.getState().pendingArtifacts[0];
    expect(updated.isCommitted).toBe(true);
    expect(updated.committedResourceId).toBe('strat-1');
  });

  it('returns null on failure without setting a global error or committing', async () => {
    commitArtifact.mockRejectedValue(new Error('boom'));

    const id = await useAgentStore.getState().commitArtifact('a1');

    expect(id).toBeNull();
    // Failure is surfaced contextually on the card, not as a global banner.
    expect(useAgentStore.getState().error).toBeNull();
    expect(useAgentStore.getState().pendingArtifacts[0].isCommitted).toBe(false);
  });
});

describe('deleteSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAgentStore.setState({
      sessions: [session('s1'), session('s2')],
      currentSessionId: null,
      error: null,
    });
  });

  it('optimistically removes the session and calls the API', async () => {
    deleteSession.mockResolvedValue({ success: true });

    await useAgentStore.getState().deleteSession('s1');

    expect(deleteSession).toHaveBeenCalledWith({ ...CONTEXT, sessionId: 's1' });
    expect(useAgentStore.getState().sessions.map((s) => s.id)).toEqual(['s2']);
  });

  it('restores the session list if the delete fails', async () => {
    deleteSession.mockRejectedValue(new Error('boom'));

    await useAgentStore.getState().deleteSession('s1');

    expect(useAgentStore.getState().sessions.map((s) => s.id)).toEqual(['s1', 's2']);
  });
});

describe('confirmToolCall', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAgentStore.setState({
      currentSessionId: 's1',
      pendingConfirmation: {
        toolName: 'run_backtest',
        argumentsJson: '{"strategy_id":"x"}',
        confirmationId: 'c1',
      },
      messages: [],
      isStreaming: false,
      pendingArtifactIdsForCurrentMessage: [],
      error: null,
    });
  });

  it('echoes the proposal to the API and clears the pending confirmation', async () => {
    confirmToolCall.mockReturnValue(completeStream());

    await useAgentStore.getState().confirmToolCall(true);

    expect(confirmToolCall).toHaveBeenCalledWith({
      ...CONTEXT,
      sessionId: 's1',
      confirmationId: 'c1',
      toolName: 'run_backtest',
      toolArgumentsJson: '{"strategy_id":"x"}',
      approved: true,
    });
    expect(useAgentStore.getState().pendingConfirmation).toBeNull();
    expect(useAgentStore.getState().isStreaming).toBe(false);
  });

  it('sends approved=false on decline', async () => {
    confirmToolCall.mockReturnValue(completeStream());

    await useAgentStore.getState().confirmToolCall(false);

    expect(confirmToolCall).toHaveBeenCalledWith(expect.objectContaining({ approved: false }));
  });

  it('is a no-op when there is no pending confirmation', async () => {
    useAgentStore.setState({ pendingConfirmation: null });

    await useAgentStore.getState().confirmToolCall(true);

    expect(confirmToolCall).not.toHaveBeenCalled();
  });

  it('accumulates thinking deltas onto the message and clears the live thinking', async () => {
    confirmToolCall.mockReturnValue(thinkingStream());
    useAgentStore.setState({ thinkingContent: '', streamingContent: '' });

    await useAgentStore.getState().confirmToolCall(true);

    const msgs = useAgentStore.getState().messages;
    const last = msgs[msgs.length - 1];
    expect(last.thinking).toBe('Weighing the tradeoff.');
    expect(last.content).toBe('Here is the plan.');
    // Live thinking buffer is reset once the turn completes.
    expect(useAgentStore.getState().thinkingContent).toBe('');
  });
});
