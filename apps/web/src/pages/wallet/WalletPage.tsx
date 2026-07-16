/**
 * Wallet — the funding home: what the account holds, how it splits between
 * deployed sleeves and free cash, and where paper capital is added.
 */

import { Loader2, Receipt } from 'lucide-react';
import { useEffect, useState } from 'react';

import { AddFundsForm } from '../../components/funding/AddFundsForm';
import { WalletActivityDrawer } from '../../components/funding/WalletActivityDrawer';
import { useActivityStore } from '../../store/activity';
import { useFundingStore } from '../../store/funding';
import { usePortfolioStore } from '../../store/portfolio';

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);
}

export default function WalletPage() {
  const { totalEquity, totalReturn, liveStrategiesCount, loading, error, fetchPortfolio } =
    usePortfolioStore();
  const { credentials, resolveAccount, resolved, accountId, unallocatedCash } = useFundingStore();
  const fetchActivity = useActivityStore((s) => s.fetch);
  const [activityOpen, setActivityOpen] = useState(false);

  useEffect(() => {
    void fetchPortfolio();
    void resolveAccount();
    void fetchActivity();
  }, [fetchPortfolio, resolveAccount, fetchActivity]);

  const handleFunded = () => {
    void fetchPortfolio();
    void fetchActivity();
  };

  const paper = credentials.find((c) => c.isPaper && c.isActive) ?? credentials[0];
  // Funding view: capital committed to sleeves vs still-allocatable (residual sleeve cash counts as committed).
  const committed = Math.max(0, totalEquity - unallocatedCash);
  const freePercent = totalEquity > 0 ? (unallocatedCash / totalEquity) * 100 : 0;
  const committedPercent = Math.max(0, Math.min(100, 100 - freePercent));

  if (loading) {
    return (
      <div className="flex h-[calc(100vh-56px)] items-center justify-center bg-bone bg-grid">
        <Loader2 className="h-5 w-5 animate-spin text-ink/40" />
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-56px)] overflow-y-auto bg-bone bg-grid">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-[18px] px-6 py-7 lg:px-8">
        {/* Header */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="font-display text-3xl uppercase tracking-tight text-ink">Wallet</h1>
            <p className="mt-1 text-[13px] text-ink/55">
              Capital available to your strategies. Funding credits free cash — the pool every
              deployment allocates from.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setActivityOpen(true)}
              className="flex items-center gap-1.5 border-2 border-ink bg-paper px-2.5 py-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.07em] text-ink shadow-[2px_2px_0_rgb(var(--lt-ink))] transition-transform hover:-translate-y-0.5"
            >
              <Receipt className="h-3.5 w-3.5" />
              Activity
            </button>
            <span className="flex items-center gap-1.5 border-2 border-ink bg-paper px-2 py-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.07em] text-ink">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-600" />
              Paper account
            </span>
          </div>
        </div>

        {error && (
          <div className="border-2 border-red-600 bg-red-50 px-3 py-2 font-mono text-[11px] font-bold text-red-700">
            {error}
          </div>
        )}

        <div className="grid grid-cols-1 items-start gap-[18px] lg:grid-cols-[1.15fr_0.85fr]">
          {/* Balance + split */}
          <div className="flex flex-col gap-[18px]">
            <div className="border-2 border-ink bg-ink p-5 text-bone shadow-[4px_4px_0_#ff4d1c]">
              <div className="font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-bone/55">
                Total equity · paper
              </div>
              <div className="mt-2 font-mono text-[40px] font-bold tabular-nums tracking-tight">
                {formatCurrency(totalEquity)}
                <span
                  className={`ml-2 text-base ${totalReturn >= 0 ? 'text-green-500' : 'text-red-500'}`}
                >
                  {totalReturn >= 0 ? '+' : '−'}
                  {formatCurrency(Math.abs(totalReturn))} lifetime
                </span>
              </div>

              <div className="mt-4 flex h-4 border-2 border-bone" aria-hidden="true">
                <span className="block bg-bone" style={{ width: `${committedPercent}%` }} />
                <span className="block bg-orange-500" style={{ width: `${freePercent}%` }} />
              </div>
              <div className="mt-2 flex justify-between font-mono text-[9.5px] font-bold uppercase tracking-[0.1em]">
                <span className="text-bone/55">
                  {formatCurrency(committed)} deployed · {liveStrategiesCount} live
                </span>
                <span className="text-orange-500">
                  {formatCurrency(unallocatedCash)} free to allocate
                </span>
              </div>
            </div>

            {/* Connected account */}
            <div className="border-2 border-ink bg-paper shadow">
              <div className="border-b-2 border-ink px-4 py-2.5 font-mono text-[9.5px] font-bold uppercase tracking-[0.13em] text-ink/50">
                Connected account
              </div>
              {resolved && !paper ? (
                <p className="px-4 py-4 text-[13px] text-ink/60">
                  No broker connected. Add Alpaca paper keys to open an account.
                </p>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5">
                  <div>
                    <div className="font-mono text-[13px] font-bold text-ink">
                      {paper?.name ?? 'Alpaca Paper'}
                    </div>
                    <div className="mt-0.5 font-mono text-[11px] text-ink/50">
                      Key {paper?.apiKeyPrefix ?? '········'}··· ·{' '}
                      {accountId ? `Account ${accountId.slice(0, 8)}` : 'Resolving…'}
                    </div>
                  </div>
                  <span className="border-2 border-green-700 px-2 py-0.5 font-mono text-[9.5px] font-bold uppercase tracking-[0.07em] text-green-700">
                    Active
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Add funds */}
          <div className="flex flex-col gap-[18px]">
            <div className="border-2 border-ink bg-paper p-4 shadow">
              <div className="mb-3.5 font-display text-lg uppercase tracking-tight text-ink">
                Add funds
              </div>
              <AddFundsForm onFunded={handleFunded} />
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-center justify-between border-2 border-ink bg-paper px-3 py-2.5">
                <span className="font-mono text-[11px] font-bold text-ink">◉ Paper credit</span>
                <span className="border-2 border-green-700 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.07em] text-green-700">
                  Instant
                </span>
              </div>
              <div className="flex items-center justify-between border-2 border-ink bg-paper px-3 py-2.5 opacity-50">
                <span className="font-mono text-[11px] font-bold text-ink">
                  ▢ Bank transfer (ACH)
                </span>
                <span className="border-2 border-ink/40 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.07em] text-ink/50">
                  Coming soon
                </span>
              </div>
              <p className="mt-1 text-[11.5px] leading-relaxed text-ink/55">
                Simulated capital for paper trading. Connecting a real broker to trade live money is
                separate setup.
              </p>
            </div>
          </div>
        </div>
      </div>

      <WalletActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} />
    </div>
  );
}
