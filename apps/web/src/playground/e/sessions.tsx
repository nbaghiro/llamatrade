import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ACCOUNT, SESSIONS, strategyById, usd } from '../data';

import { useAsk } from './askContext';
import { Page, PageHead } from './frame';
import { sessionActivity } from './model';
import { accountRows, SESSION_COLS, sessionRows } from './rows';
import { modeScope, sessionScope, type Scope } from './scope';
import { ScopeSheet } from './sheet';
import { LedgerTree } from './tree';
import { Button, Foot, LinkButton, SectionHead } from './ui';

export function SessionsList() {
  const { proposals, setProposal } = useAsk();
  const rows = useMemo(
    () => accountRows({ proposals, setProposal }, { root: false, next: true }),
    [proposals, setProposal]
  );
  const [scope, setScope] = useState<Scope>(() => modeScope('live'));
  const running = SESSIONS.filter((s) => !s.stoppedOn);
  const total = running.reduce((a, s) => a + s.value, 0);
  return (
    <Page ask={false} art="live">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Sessions"
        meta={`${running.length} running · ${usd(total)} in running sessions · 1 stopped`}
      />
      <ScopeSheet scope={scope}>
        <LedgerTree
          label="Sessions"
          name="Session"
          rows={rows}
          cols={SESSION_COLS}
          selected={scope.key}
          onSelect={(r) => r.scope && setScope(r.scope)}
        />
      </ScopeSheet>
      <Foot
        items={['Sessions trade on your Alpaca account', 'paper sessions use its paper account']}
      />
    </Page>
  );
}

export function SessionPage() {
  const { id = '' } = useParams();
  const { proposals, setProposal, ask } = useAsk();
  const [scope, setScope] = useState<Scope | null>(null);
  const s = SESSIONS.find((x) => x.id === id);
  const st = s ? strategyById(s.strategyId) : undefined;
  const rows = useMemo(
    () =>
      s
        ? sessionRows(
            s,
            0,
            s.mode === 'live' ? ACCOUNT.live : ACCOUNT.paper,
            { proposals, setProposal },
            true
          ).map((r) => ({ ...r, to: undefined }))
        : [],
    [s, proposals, setProposal]
  );
  if (!s || !st)
    return (
      <Page ask={false}>
        <p className="text-fg-2">This session could not be found.</p>
      </Page>
    );
  const sc = scope && scope.path[2] === st.name ? scope : sessionScope(s);
  return (
    <Page ask={false} art="live">
      <PageHead
        eyebrow={
          <>
            <Link to="/e/sessions" className="hover:text-fg">
              Sessions
            </Link>{' '}
            / {s.mode}
          </>
        }
        title={st.name}
        meta={`Version ${s.version} · started ${s.started}${s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''} · ${s.next ?? 'not trading'}`}
        right={
          <>
            {!s.stoppedOn && <Button size="md">Pause</Button>}
            {!s.stoppedOn ? (
              <Button size="md">Stop</Button>
            ) : (
              <Button size="md" variant="primary">
                Restart
              </Button>
            )}
            <LinkButton to={`/e/strategies/${st.id}`} size="md">
              Open strategy
            </LinkButton>
          </>
        }
      />
      <ScopeSheet scope={sc}>
        <LedgerTree
          label={`${st.name} session`}
          name="What it holds and why"
          rows={rows}
          cols={SESSION_COLS.filter((c) => c.key !== 'next')}
          selected={sc.key}
          onSelect={(r) => r.scope && setScope(r.scope)}
        />
      </ScopeSheet>
      <div className="mt-12 grid gap-12 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div>
          <SectionHead
            title="Activity"
            meta="Newest first"
            right={
              <Button
                variant="quiet"
                onClick={() => ask(`Why does ${st.name} hold this today?`, st.id)}
              >
                Ask why
              </Button>
            }
          />
          <div className="border-t border-line">
            {sessionActivity(s).map((a, i) => (
              <div
                key={i}
                className="grid grid-cols-[56px_minmax(0,1fr)] gap-3 border-b border-line py-2.5"
              >
                <span className="font-mono text-[12px] text-fg-3">{a.when}</span>
                <span className="min-w-0">
                  <span className="block text-[13px] text-fg">{a.what}</span>
                  <span className="block truncate text-[12px] text-fg-3">{a.detail}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
        <div>
          <SectionHead title="Settings" meta="Change these from the strategy or by stopping" />
          <div className="border-t border-line text-[13px]">
            {[
              ['Mode', s.mode === 'live' ? 'Live, real money' : 'Paper'],
              ['Version', `v${s.version}`],
              ['Checks', st.cadence],
              ['Started', s.started],
              ['Next', s.next ?? 'Stopped'],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between border-b border-line py-2.5">
                <span className="text-fg-3">{k}</span>
                <span className="text-fg">{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      <Foot
        items={[
          `Version ${s.version}`,
          `started ${s.started}`,
          'values before Nov 19 are sample data',
        ]}
      />
    </Page>
  );
}
