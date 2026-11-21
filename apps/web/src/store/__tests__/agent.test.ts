/* eslint-disable import/order -- vi.mock must be hoisted above the mocked-module imports */
import { beforeEach, describe, expect, it, vi } from 'vitest';

// The shared agent store (in @llamatrade/core) reads agentClient + getTenantContext
// from @llamatrade/core/net; mock that one module for both.
const { commitArtifact, deleteSession, confirmToolCall, listSessions, getSession } = vi.hoisted(
  () => ({
    commitArtifact: vi.fn(),
    deleteSession: vi.fn(),
    confirmToolCall: vi.fn(),
    listSessions: vi.fn(),
    getSession: vi.fn(),
  })
);

vi.mock('@llamatrade/core/net', () => ({
  agentClient: { commitArtifact, deleteSession, confirmToolCall, listSessions, getSession },
  getTenantContext: () => ({ tenantId: 't1', userId: 'u1' }),
}));

import { Code, ConnectError } from '@connectrpc/connect';
import { describeConfirmation } from '@llamatrade/core/agent/confirmation';
import { dayBucket, groupSessionsByDay, sessionWhen } from '@llamatrade/core/agent/history';
import { fixedTargets, strategyStructure } from '@llamatrade/core/agent/structure';
import { StreamEventType } from '@llamatrade/core/proto/agent_pb';
import {
  CHANGE_PROMPT,
  isServiceUnavailable,
  useAgentStore,
  withStoredToolCalls,
  type AgentMessage,
} from '@llamatrade/core/stores/agent';

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
    commitArtifact.mockResolvedValue({
      success: true,
      resourceId: 'strat-1',
      resourceType: 'strategy',
    });

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
      resolvedConfirmations: [],
      seedPrompt: '',
      serviceUnavailable: false,
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

describe('answered approvals stay in the thread', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAgentStore.setState({
      currentSessionId: 's1',
      pendingConfirmation: {
        toolName: 'run_backtest',
        argumentsJson: '{"initial_capital":25000}',
        confirmationId: 'c1',
      },
      messages: [{ id: 'm9' }] as unknown as ReturnType<typeof useAgentStore.getState>['messages'],
      resolvedConfirmations: [],
      seedPrompt: '',
      serviceUnavailable: false,
      isStreaming: false,
      pendingArtifactIdsForCurrentMessage: [],
      error: null,
    });
  });

  it('records an approval after the message it followed', async () => {
    confirmToolCall.mockReturnValue(completeStream());
    await useAgentStore.getState().confirmToolCall(true);
    const [r] = useAgentStore.getState().resolvedConfirmations;
    expect(r).toMatchObject({ confirmationId: 'c1', decision: 'approved', afterMessageId: 'm9' });
  });

  it('records a decline without seeding the composer', async () => {
    confirmToolCall.mockReturnValue(completeStream());
    await useAgentStore.getState().confirmToolCall(false);
    expect(useAgentStore.getState().resolvedConfirmations[0].decision).toBe('declined');
    expect(useAgentStore.getState().seedPrompt).toBe('');
  });

  it('declines on "change" and puts the change prompt in the composer', async () => {
    confirmToolCall.mockReturnValue(completeStream());
    await useAgentStore.getState().confirmToolCall(false, 'change');
    expect(confirmToolCall).toHaveBeenCalledWith(expect.objectContaining({ approved: false }));
    expect(useAgentStore.getState().resolvedConfirmations[0].decision).toBe('change');
    expect(useAgentStore.getState().seedPrompt).toBe(CHANGE_PROMPT);
  });

  it('treats approved=true as an approval whatever decision is passed', async () => {
    confirmToolCall.mockReturnValue(completeStream());
    await useAgentStore.getState().confirmToolCall(true, 'change');
    expect(useAgentStore.getState().resolvedConfirmations[0].decision).toBe('approved');
  });

  it('marks the service unavailable when the confirm call cannot reach it', async () => {
    confirmToolCall.mockImplementation(() => {
      throw new ConnectError('upstream down', Code.Unavailable);
    });
    await useAgentStore.getState().confirmToolCall(true);
    expect(useAgentStore.getState().serviceUnavailable).toBe(true);
    expect(useAgentStore.getState().error).toBeNull();
  });

  it('starts a new chat with no answered approvals', () => {
    useAgentStore.setState({
      resolvedConfirmations: [
        {
          toolName: 't',
          argumentsJson: '{}',
          confirmationId: 'x',
          decision: 'declined',
          afterMessageId: null,
        },
      ],
    });
    useAgentStore.getState().startNewChat();
    expect(useAgentStore.getState().resolvedConfirmations).toEqual([]);
  });
});

describe('service availability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAgentStore.setState({ serviceUnavailable: false, sessions: [], messages: [], error: null });
  });

  it('recognises an unreachable service and nothing else', () => {
    expect(isServiceUnavailable(new ConnectError('x', Code.Unavailable))).toBe(true);
    expect(isServiceUnavailable(new TypeError('Failed to fetch'))).toBe(true);
    expect(isServiceUnavailable(new ConnectError('Failed to fetch', Code.Unknown))).toBe(true);
    expect(isServiceUnavailable(new ConnectError('bad id', Code.InvalidArgument))).toBe(false);
    expect(isServiceUnavailable(new Error('quota exceeded'))).toBe(false);
    expect(isServiceUnavailable('nope')).toBe(false);
  });

  it('flags the outage from the history read and clears it once history loads', async () => {
    listSessions.mockRejectedValueOnce(new ConnectError('down', Code.Unavailable));
    await useAgentStore.getState().loadSessions();
    expect(useAgentStore.getState().serviceUnavailable).toBe(true);

    listSessions.mockResolvedValueOnce({ sessions: [session('a')] });
    await useAgentStore.getState().loadSessions();
    expect(useAgentStore.getState().serviceUnavailable).toBe(false);
  });

  it('keeps the thread already on screen when a conversation can’t be opened during an outage', async () => {
    const shown = [{ id: 'm1' }] as unknown as ReturnType<
      typeof useAgentStore.getState
    >['messages'];
    useAgentStore.setState({ currentSessionId: 's1', messages: shown });
    getSession.mockRejectedValueOnce(new ConnectError('down', Code.Unavailable));
    await useAgentStore.getState().selectSession('s2');
    const s = useAgentStore.getState();
    expect(s.serviceUnavailable).toBe(true);
    expect(s.messages).toBe(shown);
    expect(s.currentSessionId).toBe('s1');
    expect(s.error).toBeNull();
  });
});

describe('describeConfirmation', () => {
  it('labels a backtest’s arguments and says what it will and won’t do', () => {
    const v = describeConfirmation(
      'run_backtest',
      JSON.stringify({
        strategy_id: 'st-1',
        start_date: '2021-11-01',
        end_date: '2026-10-30',
        initial_capital: 25000,
        dsl_code: '',
      }),
      { 'st-1': 'Tech Momentum Defensive' }
    );
    expect(v.title).toBe('Run a backtest');
    expect(v.effect).toMatch(/historical data only/);
    expect(v.args).toEqual([
      { label: 'Strategy', value: 'Tech Momentum Defensive' },
      { label: 'From', value: '2021-11-01' },
      { label: 'To', value: '2026-10-30' },
      { label: 'Capital', value: '$25,000' },
    ]);
  });

  it('summarises inline code and shows an unknown strategy id as is', () => {
    const v = describeConfirmation(
      'run_backtest',
      JSON.stringify({ strategy_id: 'st-9', dsl_code: '(strategy "x"\n  (asset SPY))' })
    );
    expect(v.args).toEqual([
      { label: 'Strategy', value: 'st-9' },
      { label: 'Strategy', value: 'The draft in this conversation (2 lines)' },
    ]);
  });

  it('humanises an unknown tool and keeps its arguments', () => {
    const v = describeConfirmation('pause_session', '{"session_id":"s1","note":{"a":1}}');
    expect(v.title).toBe('Pause session');
    expect(v.args).toEqual([
      { label: 'Session id', value: 's1' },
      { label: 'Note', value: '{"a":1}' },
    ]);
  });

  it('shows unparseable or non-object arguments raw rather than hiding them', () => {
    expect(describeConfirmation('x', '{oops').args).toEqual([
      { label: 'Arguments', value: '{oops' },
    ]);
    expect(describeConfirmation('x', '[1]').args).toEqual([{ label: 'Arguments', value: '[1]' }]);
    expect(describeConfirmation('x', '').args).toEqual([]);
  });
});

describe('strategyStructure', () => {
  const DSL = `(strategy "Tech Momentum Defensive"
  :rebalance monthly :benchmark QQQ
  (if (< (price QQQ) (sma QQQ 200))
    (asset IEF)
    (else
      (weight :method equal
        (asset QQQ) (asset XLK) (asset SMH)))))`;

  it('reads the schedule, benchmark, funds and rules as written', () => {
    const s = strategyStructure(DSL);
    expect(s).not.toBeNull();
    expect(s?.name).toBe('Tech Momentum Defensive');
    expect(s?.rebalance).toBe('monthly');
    expect(s?.benchmark).toBe('QQQ');
    expect(s?.symbols).toEqual(['IEF', 'QQQ', 'XLK', 'SMH']);
    expect(s?.lines.map((l) => [l.depth, l.kind])).toEqual([
      [0, 'rule'],
      [1, 'funds'],
      [0, 'otherwise'],
      [1, 'weight'],
      [2, 'funds'],
    ]);
    expect(s?.lines[0].text).toMatch(/^If .*QQQ/);
    expect(s?.lines[3].text).toBe('Equal weight');
    expect(s?.lines[4].text).toBe('QQQ · XLK · SMH');
  });

  it('carries fixed weights onto each fund', () => {
    const s = strategyStructure(
      '(strategy "60/40" :rebalance quarterly (weight :method specified (asset VTI :weight 60) (asset BND :weight 40)))'
    );
    expect(s?.lines[0].text).toBe('Fixed weights');
    expect(s?.lines[1].funds).toEqual([
      { symbol: 'VTI', weight: 60 },
      { symbol: 'BND', weight: 40 },
    ]);
  });

  it('returns null for empty or unparseable code', () => {
    expect(strategyStructure('')).toBeNull();
    expect(strategyStructure('(not-a-strategy)')).toBeNull();
  });
});

describe('fixedTargets', () => {
  it('multiplies nested fixed and equal weights down to each fund', () => {
    const t = fixedTargets(`(strategy "All-Weather Portfolio"
  (weight :method specified
    (group "Equities" :weight 30 (weight :method equal (asset VTI) (asset VEA) (asset VWO)))
    (group "Long Bonds" :weight 40 (weight :method specified (asset TLT :weight 60) (asset EDV :weight 40)))
    (group "Intermediate" :weight 15 (weight :method equal (asset IEF) (asset VGIT)))
    (group "Commodities" :weight 15 (weight :method equal (asset GLD) (asset DBC) (asset PDBC)))))`);
    expect(t?.VTI).toBeCloseTo(0.1);
    expect(t?.TLT).toBeCloseTo(0.24);
    expect(t?.EDV).toBeCloseTo(0.16);
    expect(t?.IEF).toBeCloseTo(0.075);
    expect(t?.PDBC).toBeCloseTo(0.05);
    const sum = Object.values(t ?? {}).reduce((a, b) => a + b, 0);
    expect(sum).toBeCloseTo(1);
  });

  it('normalises specified weights that do not add to 100', () => {
    const t = fixedTargets(
      '(strategy "S" (weight :method specified (asset VTI :weight 3) (asset BND :weight 1)))'
    );
    expect(t).toEqual({ VTI: 0.75, BND: 0.25 });
  });

  it('is null when a rule, filter or computed weighting decides the holdings', () => {
    expect(
      fixedTargets(
        '(strategy "M" (if (> (price SPY) (sma SPY 200)) (asset SPY) (else (asset IEF))))'
      )
    ).toBeNull();
    expect(
      fixedTargets(
        '(strategy "R" (weight :method inverse-volatility :lookback 60 (asset SPY) (asset TLT)))'
      )
    ).toBeNull();
    expect(fixedTargets('')).toBeNull();
    expect(fixedTargets('(nonsense')).toBeNull();
  });
});

describe('conversation history by day', () => {
  const now = new Date(2026, 10, 16, 12, 0);
  const at = (d: Date) => ({ seconds: BigInt(Math.floor(d.getTime() / 1000)) });
  const s = (id: string, title: string, d?: Date) => ({
    id,
    title,
    lastActivityAt: d ? at(d) : undefined,
  });

  const rows = [
    s('old', 'Dual momentum, stocks vs bonds', new Date(2026, 10, 5, 9, 0)),
    s('y', 'Bond hedge below the 200-day', new Date(2026, 10, 15, 15, 2)),
    s('t1', 'How is my portfolio doing?', new Date(2026, 10, 16, 9, 48)),
    s('t2', 'Tech momentum with a 200-day exit', new Date(2026, 10, 16, 10, 31)),
    s('none', 'No timestamp'),
  ];

  it('groups by local day, newest first, leaving empty groups out', () => {
    const groups = groupSessionsByDay(rows, '', now);
    expect(groups.map((g) => [g.label, g.sessions.map((x) => x.id)])).toEqual([
      ['Today', ['t2', 't1']],
      ['Yesterday', ['y']],
      ['Earlier', ['old', 'none']],
    ]);
  });

  it('filters titles by a case-insensitive query', () => {
    const groups = groupSessionsByDay(rows, '  200-DAY ', now);
    expect(groups.map((g) => [g.label, g.sessions.map((x) => x.id)])).toEqual([
      ['Today', ['t2']],
      ['Yesterday', ['y']],
    ]);
    expect(groupSessionsByDay(rows, 'zzz', now)).toEqual([]);
  });

  it('puts the first minute of today in Today and the last minute of yesterday in Yesterday', () => {
    expect(dayBucket(at(new Date(2026, 10, 16, 0, 0)).seconds, now)).toBe('Today');
    expect(dayBucket(at(new Date(2026, 10, 15, 23, 59)).seconds, now)).toBe('Yesterday');
    expect(dayBucket(at(new Date(2026, 10, 14, 23, 59)).seconds, now)).toBe('Earlier');
    expect(dayBucket(undefined, now)).toBe('Earlier');
  });

  it('shows a time for recent conversations and a date for older ones', () => {
    expect(sessionWhen(at(new Date(2026, 10, 16, 10, 31)).seconds, now)).toBe('10:31');
    expect(sessionWhen(at(new Date(2026, 10, 8, 10, 31)).seconds, now)).toBe('Nov 8');
    expect(sessionWhen(undefined, now)).toBe('');
  });
});

describe('withStoredToolCalls', () => {
  const msg = (id: string, tools: string[]): AgentMessage =>
    ({
      id,
      content: '',
      toolCalls: tools.map((name) => ({ id: name, name })),
    }) as unknown as AgentMessage;

  it('fills tool calls a streamed message lacks from its stored copy', () => {
    const out = withStoredToolCalls([msg('a', []), msg('b', [])], [msg('b', ['get_positions'])]);
    expect(out[0].toolCalls).toHaveLength(0);
    expect(out[1].toolCalls.map((t) => t.name)).toEqual(['get_positions']);
  });

  it('keeps tool calls a message already has and ignores unknown ids', () => {
    const local = [msg('a', ['get_strategy'])];
    const out = withStoredToolCalls(local, [msg('a', ['get_positions']), msg('z', ['x'])]);
    expect(out[0]).toBe(local[0]);
  });
});
