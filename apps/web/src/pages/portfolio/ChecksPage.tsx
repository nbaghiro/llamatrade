import { num } from '@llamatrade/core/format';
import { getTenantContext, ledgerClient } from '@llamatrade/core/net';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { usePortfolioStore, type SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { CheckCircle2, AlertTriangle } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { ledgerBySymbol, type LedgerCount } from '../../components/portfolio/checks';
import {
  LoadingLabel,
  ModeBadge,
  Num,
  PageHead,
  PanelError,
  SkeletonRows,
} from '../../components/ui';
import { causeSentence } from '../../lib/portfolioView';

type Counts = Record<string, Record<string, number>>;

/** Open ledger quantity per symbol for each sleeve, keyed by ledger sleeve id. */
function useLedgerCounts(sleeves: readonly SleeveSummary[]) {
  const ids = sleeves.map((s) => s.sleeveId).filter((id): id is string => id !== null);
  const key = ids.join(',');
  const [state, setState] = useState<{ key: string; counts: Counts; failed: boolean }>({
    key: '',
    counts: {},
    failed: false,
  });

  useEffect(() => {
    let live = true;
    const list = key ? key.split(',') : [];
    Promise.all(
      list.map((sleeveId) =>
        ledgerClient.getSleeve({ context: getTenantContext(), sleeveId }).then((res) => {
          const out: Record<string, number> = {};
          for (const lot of res.lots) {
            if (lot.isOpen) out[lot.symbol] = (out[lot.symbol] ?? 0) + num(lot.qty);
          }
          return out;
        })
      )
    )
      .then((all) => {
        if (!live) return;
        const counts: Counts = {};
        list.forEach((id, i) => {
          counts[id] = all[i];
        });
        setState({ key, counts, failed: false });
      })
      .catch(() => {
        if (live) setState({ key, counts: {}, failed: true });
      });
    return () => {
      live = false;
    };
  }, [key]);

  return { counts: state.counts, loading: state.key !== key, failed: state.failed };
}

const TH =
  'border-b border-line px-3 py-2.5 text-left font-mono text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3';
const TD = 'border-b border-line px-3 py-2.5';

function CountsTable({ rows }: { rows: readonly LedgerCount[] }) {
  if (rows.length === 0) {
    return <p className="m-0 px-4 py-4 text-[12.5px] text-fg-3">The ledger holds no open lots.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[480px] border-collapse text-[13px]">
        <thead>
          <tr>
            <th className={TH}>Symbol</th>
            <th className={TH}>Ledger, by sleeve</th>
            <th className={`${TH} text-right`}>Ledger</th>
            <th className={TH}>Sleeve status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className={r.frozen ? 'text-risk' : ''}>
              <td className={`${TD} font-mono font-semibold`}>{r.symbol}</td>
              <td className={`${TD} ${r.frozen ? '' : 'text-fg-2'}`}>
                {r.bySleeve
                  .map((b) => `${b.name} ${b.qty % 1 ? b.qty.toFixed(4) : b.qty}`)
                  .join(', ')}
              </td>
              <td className={`${TD} text-right`}>
                <Num value={r.total} dp={r.total % 1 ? 4 : 0} />
              </td>
              <td className={TD}>
                {r.frozen ? (
                  <span className="inline-flex items-center gap-1.5">
                    <i aria-hidden="true" className="h-1.5 w-1.5 rounded-[1px] bg-risk" />
                    In a frozen sleeve
                  </span>
                ) : (
                  <span className="text-fg-3">Trading</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Step({
  n,
  title,
  body,
  built = true,
}: {
  n: number;
  title: string;
  body: string;
  built?: boolean;
}) {
  return (
    <li className={`flex items-start gap-3 ${built ? '' : 'opacity-60'}`}>
      <span
        className={`grid h-5 w-5 flex-none place-items-center rounded-full font-mono text-[11px] ${
          built ? 'bg-accent text-canvas' : 'border border-line-strong text-fg-3'
        }`}
      >
        {n}
      </span>
      <div className="text-[13px]">
        <b className="font-semibold">{title}</b> <span className="text-fg-2">{body}</span>
        {!built && (
          <span className="ml-1.5 inline-block rounded-full border border-line-strong px-1.5 text-[11px] text-fg-3">
            Not built yet
          </span>
        )}
      </div>
    </li>
  );
}

/** Each account's verdict against Alpaca, and what the ledger counts on the paper side (reconciliation2 A). */
export default function ChecksPage() {
  const { sleeves, loaded, loading, error, fetchPortfolio } = usePortfolioStore();
  const credentials = useBrokerStore((s) => s.credentials);
  const brokerLoaded = useBrokerStore((s) => s.loaded);
  const fetchCredentials = useBrokerStore((s) => s.fetch);

  useEffect(() => {
    fetchPortfolio();
  }, [fetchPortfolio]);
  useEffect(() => {
    if (!brokerLoaded) fetchCredentials().catch(() => undefined);
  }, [brokerLoaded, fetchCredentials]);

  const paper = sleeves.filter((s) => !s.live);
  const { counts, loading: countsLoading, failed } = useLedgerCounts(paper);
  const rows = ledgerBySymbol(paper, counts);
  const frozen = paper.filter((s) => s.frozen);
  const hasLive = credentials.some((c) => c.isActive && !c.isPaper);
  const liveSleeves = sleeves.filter((s) => s.live);

  return (
    <div className="page">
      <PageHead
        crumbs={[{ label: 'Portfolio', to: '/portfolio' }, { label: 'Checks' }]}
        title="Checks against Alpaca"
        sub="The ledger's holdings are compared with the positions Alpaca reports. A sleeve whose counts Alpaca contradicts is frozen until it's reviewed."
      />

      <section className="panel mb-4 flex flex-wrap items-center gap-3 px-4 py-3 text-[13px]">
        <ModeBadge mode="live" size="sm" />
        {hasLive ? (
          <span>
            <b className="font-semibold">
              {liveSleeves.some((s) => s.frozen) ? 'Live differs.' : 'No live sleeve is frozen.'}
            </b>{' '}
            <span className="text-fg-2">
              The ledger&apos;s live counts aren&apos;t listed on this page yet.
            </span>
          </span>
        ) : (
          <span className="text-fg-2">
            No live account is connected.{' '}
            <Link to="/settings/broker" className="text-accent hover:underline">
              Connect one in Settings
            </Link>
          </span>
        )}
      </section>

      <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className={`panel overflow-hidden ${frozen.length ? 'border-risk-line' : ''}`}>
          <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
            <ModeBadge mode="paper" size="sm" />
            {frozen.length ? (
              <>
                <b className="font-semibold">Paper differs</b>
                <span className="inline-flex items-center gap-1.5 text-[13px] text-risk">
                  <AlertTriangle aria-hidden="true" className="h-3.5 w-3.5" />
                  {frozen.map((s) => s.name).join(', ')} {frozen.length === 1 ? 'is' : 'are'} frozen
                </span>
              </>
            ) : (
              <span className="inline-flex items-center gap-2">
                <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-accent" />
                <b className="font-semibold">No paper sleeve is frozen.</b>
                <span className="text-[13px] text-fg-2">
                  The latest check found no difference that stops trading.
                </span>
              </span>
            )}
          </div>
          {!loaded || (loading && sleeves.length === 0) || countsLoading ? (
            <div aria-busy="true">
              <LoadingLabel>Loading the ledger&apos;s counts</LoadingLabel>
              <SkeletonRows rows={5} cols={4} />
            </div>
          ) : error && sleeves.length === 0 ? (
            <PanelError
              title="The ledger couldn't be read"
              cause={causeSentence(error)}
              onRetry={() => fetchPortfolio()}
              retrying={loading}
            />
          ) : failed ? (
            <PanelError
              title="The ledger's counts couldn't be loaded"
              onRetry={() => fetchPortfolio()}
              retrying={loading}
            />
          ) : (
            <CountsTable rows={rows} />
          )}
          <p className="m-0 border-t border-line px-4 py-3 text-[12px] text-fg-3">
            Alpaca&apos;s own counts, and the order that caused a difference, aren&apos;t shown here
            yet. Compare with the positions in your Alpaca paper dashboard.
          </p>
        </section>

        <section className="panel">
          <div className="border-b border-line px-4 py-3">
            <b className="font-semibold">
              {frozen.length ? 'What you can do' : 'How the check works'}
            </b>
          </div>
          {frozen.length ? (
            <div className="grid gap-3 p-4">
              <ol className="m-0 grid list-none gap-3 p-0">
                <Step
                  n={1}
                  title="Check the symbol in Alpaca."
                  body="The ledger counts shares Alpaca doesn't show, or a different number of them. A sale made outside LlamaTrade, or a fill that didn't reach the ledger, would explain it."
                />
                <Step
                  n={2}
                  title="Leave the holdings in place."
                  body="Nothing is adjusted automatically, and the positions stay as they are while the sleeve is frozen."
                />
                <Step
                  n={3}
                  title="Correct the ledger and resume the sleeve."
                  body="Unfreezing happens after a review outside the app for now."
                  built={false}
                />
              </ol>
              <p className="m-0 border-t border-line pt-3 text-[12px] text-fg-3">
                {paper.length > frozen.length
                  ? `${paper
                      .filter((s) => !s.frozen)
                      .map((s) => s.name)
                      .join(', ')} keep trading. `
                  : ''}
                New orders for a frozen sleeve, including its next rebalance, are rejected while it
                stays frozen.
              </p>
            </div>
          ) : (
            <p className="m-0 p-4 text-[13px] text-fg-2">
              Each sleeve&apos;s open lots are added up per symbol and compared with what Alpaca
              holds. Shares Alpaca holds that no sleeve knows about are recorded in the Unmanaged
              sleeve. When the ledger counts more shares than Alpaca, or a different number, every
              sleeve holding that symbol is frozen and nothing is adjusted automatically.
            </p>
          )}
        </section>
      </div>
    </div>
  );
}
