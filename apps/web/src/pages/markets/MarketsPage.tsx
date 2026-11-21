import { ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

import { MarketsListView } from '../../components/markets/MarketsListView';
import { AddSymbol, QuoteTable } from '../../components/markets/QuoteTable';
import { useMarketsModel } from '../../components/markets/useMarketsModel';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { PageHead } from '../../components/ui';
import { etClock } from '../../lib/marketClock';

/** Markets: a quote table whose rows open (markets2 D), and one symbol's full chart. */
export default function MarketsPage() {
  const m = useMarketsModel();
  const compact = useMediaQuery('(max-width: 767px)');

  if (m.view === 'chart') {
    return (
      <div className="page relative isolate">
        <PageHead
          title="Markets"
          sub={
            <Link
              to={`/markets?symbol=${encodeURIComponent(m.symbol)}`}
              className="inline-flex items-center gap-1 hover:text-fg"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              Back to the quote table
            </Link>
          }
        />
        <MarketsListView m={m} />
      </div>
    );
  }

  const count = m.heldSymbols.length + m.watchOnly.length;
  return (
    <div className="page relative isolate">
      <PageHead
        title="Markets"
        sub={`${count} ${count === 1 ? 'symbol' : 'symbols'} · prices at ${etClock(m.now)} ET from Alpaca's IEX feed`}
        actions={<AddSymbol m={m} />}
      />
      <QuoteTable m={m} compact={compact} />
    </div>
  );
}
