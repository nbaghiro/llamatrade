import { useMemo } from 'react';

import { MarketsListView } from '../../components/markets/MarketsListView';
import { MarketsMapView } from '../../components/markets/MarketsMapView';
import { dayMoves, mapTiles, moveClass } from '../../components/markets/marketsView';
import {
  useMarketsModel,
  type MarketsModel,
  type MarketsView,
} from '../../components/markets/useMarketsModel';
import { useMediaQuery } from '../../components/strategies/useMediaQuery';
import { PageArt, PageHead, Segmented } from '../../components/ui';
import { formatMoney } from '../../lib/format';

const VIEWS: readonly { key: MarketsView; label: string }[] = [
  { key: 'list', label: 'List' },
  { key: 'map', label: 'Map' },
];

function PhoneSub({ m }: { m: MarketsModel }) {
  const moves = useMemo(
    () => dayMoves(mapTiles(m.held, m.quotes, m.equity)),
    [m.held, m.quotes, m.equity]
  );
  if (!m.loaded || moves.held <= 0) return null;
  return (
    <>
      <span className={`num ${moveClass(moves.total)}`}>
        {formatMoney(moves.total, { signed: true })}
      </span>{' '}
      on <span className="num">{formatMoney(moves.held, { dp: 0 })}</span> held
    </>
  );
}

/** Markets, the second area: a map of what you hold, or the three-column list (markets E). */
export default function MarketsPage() {
  const m = useMarketsModel();
  const compact = useMediaQuery('(max-width: 767px)');
  const map = m.view === 'map';

  return (
    <div className="page relative isolate">
      <PageArt shape="top" />
      <PageHead
        title="Markets"
        sub={
          compact && map ? (
            <PhoneSub m={m} />
          ) : map ? (
            "Tiles are sized by your dollars in each symbol and coloured by today's move"
          ) : (
            'Prices for what your sleeves hold and the symbols you watch'
          )
        }
        actions={<Segmented label="View" options={VIEWS} value={m.view} onChange={m.setView} />}
      />
      {map ? <MarketsMapView m={m} compact={compact} /> : <MarketsListView m={m} />}
    </div>
  );
}
