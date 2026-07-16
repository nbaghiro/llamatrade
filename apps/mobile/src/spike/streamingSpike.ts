/**
 * CONNECT SERVER-STREAMING SPIKE
 * ------------------------------------------------------------------
 * The one thing that must pass before committing Phase 2 (Copilot).
 *
 * React Native's built-in fetch buffers the whole response body, so
 * server-streaming RPCs never deliver incrementally. This harness proves that
 * `expo/fetch` (wired in net/clients.ts) yields a streaming body and that the
 * existing `for await` consumption pattern works UNCHANGED in RN.
 *
 * Run it from the Spike screen (app/spike.tsx). PASS criteria live in each fn.
 */
import { StreamEventType } from '@llamatrade/core/proto/agent_pb';
import { BacktestStatus } from '@llamatrade/core/proto/backtest_pb';
import { agentClient, backtestClient } from '../net/clients';
import { tenantContext } from '../stores/auth';

export interface SpikeLog {
  atMs: number;
  line: string;
}

export interface SpikeResult {
  name: string;
  pass: boolean;
  firstEventMs: number | null;
  eventCount: number;
  /** CONTENT_DELTA count (copilot) or progress-update count (backtest). */
  deltaCount: number;
  logs: SpikeLog[];
  error?: string;
}

/**
 * Spike A — Copilot. PASS = ≥2 CONTENT_DELTA events arrive before COMPLETE and
 * the first event lands < 1.5s. That proves incremental (not buffered) delivery.
 */
export async function runCopilotStreamSpike(
  input: { content?: string; sessionId?: string; signal?: AbortSignal } = {},
): Promise<SpikeResult> {
  const t0 = Date.now();
  const logs: SpikeLog[] = [];
  const log = (line: string) => logs.push({ atMs: Date.now() - t0, line });

  const ctx = tenantContext();
  let eventCount = 0;
  let deltaCount = 0;
  let firstEventMs: number | null = null;

  if (!ctx) {
    return { name: 'copilot-stream', pass: false, firstEventMs: null, eventCount: 0, deltaCount: 0, logs, error: 'Not authenticated — set a dev session first.' };
  }

  try {
    log('opening StreamMessage…');
    const stream = agentClient.streamMessage(
      {
        context: { tenantId: ctx.tenantId, userId: ctx.userId, roles: ctx.roles },
        sessionId: input.sessionId ?? '',
        content: input.content ?? 'Build a momentum rotation across the 11 sector ETFs, monthly.',
      },
      input.signal ? { signal: input.signal } : {},
    );

    for await (const ev of stream) {
      eventCount += 1;
      if (firstEventMs === null) firstEventMs = Date.now() - t0;
      switch (ev.eventType) {
        case StreamEventType.CONTENT_DELTA:
          deltaCount += 1;
          log(`Δ delta #${deltaCount} (+${ev.contentDelta.length} chars)`);
          break;
        case StreamEventType.TOOL_CALL_START:
          log(`⚙ tool start · ${ev.toolName}`);
          break;
        case StreamEventType.TOOL_CALL_COMPLETE:
          log(`✓ tool done · ${ev.toolName} (${ev.toolStatus})`);
          break;
        case StreamEventType.ARTIFACT_CREATED:
          log(`✦ artifact · ${ev.artifact?.name ?? '?'}`);
          break;
        case StreamEventType.ERROR:
          log(`✗ error · ${ev.errorMessage}`);
          break;
        case StreamEventType.COMPLETE:
          log('■ complete');
          break;
        default:
          log(`? event type ${ev.eventType}`);
      }
    }

    const pass = deltaCount >= 2 && firstEventMs !== null && firstEventMs < 1500;
    log(`RESULT · pass=${pass} · ${deltaCount} deltas · first @ ${firstEventMs}ms`);
    return { name: 'copilot-stream', pass, firstEventMs, eventCount, deltaCount, logs };
  } catch (err) {
    log(`threw · ${String(err)}`);
    return { name: 'copilot-stream', pass: false, firstEventMs, eventCount, deltaCount, logs, error: String(err) };
  }
}

/**
 * Spike B — Backtest progress. PASS = ≥2 progress updates arrive and the stream
 * reaches a terminal status (COMPLETED / FAILED / CANCELLED).
 */
export async function runBacktestProgressSpike(
  backtestId: string,
  signal?: AbortSignal,
): Promise<SpikeResult> {
  const t0 = Date.now();
  const logs: SpikeLog[] = [];
  const log = (line: string) => logs.push({ atMs: Date.now() - t0, line });

  const ctx = tenantContext();
  let eventCount = 0;
  let firstEventMs: number | null = null;
  let reachedTerminal = false;

  if (!ctx) {
    return { name: 'backtest-progress', pass: false, firstEventMs: null, eventCount: 0, deltaCount: 0, logs, error: 'Not authenticated — set a dev session first.' };
  }

  try {
    log(`streaming progress · ${backtestId}`);
    const stream = backtestClient.streamBacktestProgress(
      { context: { tenantId: ctx.tenantId, userId: ctx.userId, roles: ctx.roles }, backtestId },
      signal ? { signal } : {},
    );

    for await (const u of stream) {
      eventCount += 1;
      if (firstEventMs === null) firstEventMs = Date.now() - t0;
      log(`${u.progressPercent}% · ${u.message || u.currentDate || `status ${u.status}`}`);
      if (
        u.status === BacktestStatus.COMPLETED ||
        u.status === BacktestStatus.FAILED ||
        u.status === BacktestStatus.CANCELLED
      ) {
        reachedTerminal = true;
      }
    }

    const pass = eventCount >= 2 && reachedTerminal;
    log(`RESULT · pass=${pass} · ${eventCount} updates · terminal=${reachedTerminal}`);
    return { name: 'backtest-progress', pass, firstEventMs, eventCount, deltaCount: eventCount, logs };
  } catch (err) {
    log(`threw · ${String(err)}`);
    return { name: 'backtest-progress', pass: false, firstEventMs, eventCount, deltaCount: 0, logs, error: String(err) };
  }
}
