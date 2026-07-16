import { beforeEach, describe, expect, it, vi } from 'vitest';

// The agent store uses zustand `persist`; provide an in-memory localStorage
// (node test env has none) before the store module is imported.
vi.hoisted(() => {
  const mem = new Map<string, string>();
  const storage: Storage = {
    getItem: (key) => mem.get(key) ?? null,
    setItem: (key, value) => {
      mem.set(key, value);
    },
    removeItem: (key) => {
      mem.delete(key);
    },
    clear: () => {
      mem.clear();
    },
    key: (index) => Array.from(mem.keys())[index] ?? null,
    get length() {
      return mem.size;
    },
  };
  globalThis.localStorage = storage;
});

const { commitArtifact, deleteSession, confirmToolCall } = vi.hoisted(() => ({
  commitArtifact: vi.fn(),
  deleteSession: vi.fn(),
  confirmToolCall: vi.fn(),
}));

vi.mock('../../services/grpc-client', () => ({
  agentClient: { commitArtifact, deleteSession, confirmToolCall },
}));

vi.mock('../auth', () => ({
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

// eslint-disable-next-line import/order -- resolver misclassifies the gitignored generated/ path
import { StreamEventType } from '../../generated/proto/agent_pb';
import { useAgentStore } from '../agent';

async function* completeStream() {
  yield { eventType: StreamEventType.COMPLETE, messageId: 'm1', contentDelta: '' } as never;
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
});
