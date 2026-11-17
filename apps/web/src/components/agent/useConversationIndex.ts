import { agentClient, getTenantContext } from '@llamatrade/core/net';
import type { AgentMessage, AgentSession } from '@llamatrade/core/stores/agent';
import { useEffect, useState } from 'react';

const cache = new Map<string, { at: bigint; messages: AgentMessage[] }>();

/** How many recent conversations search reads; the agent service has no message search. */
export const SEARCH_DEPTH = 30;

/**
 * Loads the messages of the most recent conversations so search can read what was said. Each
 * conversation is fetched once per change in its last activity.
 */
export function useConversationIndex(sessions: readonly AgentSession[], enabled: boolean) {
  const [index, setIndex] = useState<Record<string, AgentMessage[]>>({});
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!enabled) return;
    const context = getTenantContext();
    if (!context) return;
    let cancelled = false;
    const recent = [...sessions]
      .sort((a, b) => Number((b.lastActivityAt?.seconds ?? 0n) - (a.lastActivityAt?.seconds ?? 0n)))
      .slice(0, SEARCH_DEPTH);
    const fresh = (s: AgentSession) => cache.get(s.id)?.at === (s.lastActivityAt?.seconds ?? 0n);
    const publish = () => {
      if (cancelled) return;
      const next: Record<string, AgentMessage[]> = {};
      for (const s of recent) {
        const hit = cache.get(s.id);
        if (hit) next[s.id] = hit.messages;
      }
      setIndex(next);
    };
    const missing = recent.filter((s) => !fresh(s));
    publish();
    if (!missing.length) return;
    setLoading(true);
    Promise.all(
      missing.map((s) =>
        agentClient
          .getSession({ context, sessionId: s.id, includeMessages: true, messageLimit: 200 })
          .then((r) =>
            cache.set(s.id, { at: s.lastActivityAt?.seconds ?? 0n, messages: r.messages })
          )
          .catch(() => undefined)
      )
    ).then(() => {
      publish();
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [sessions, enabled]);

  return { index, loading };
}
