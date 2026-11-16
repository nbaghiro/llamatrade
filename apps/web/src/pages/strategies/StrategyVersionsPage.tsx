import { ArrowLeft } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';

import { useStrategyDetail } from '../../components/strategies/useStrategyDetail';
import { VersionsView } from '../../components/strategies/versions/VersionsView';
import { Skeleton } from '../../components/ui';

export default function StrategyVersionsPage() {
  const { id = '' } = useParams<{ id: string }>();
  const detail = useStrategyDetail(id);
  const name = detail.strategy?.name;
  return (
    <div className="page grid grid-cols-[minmax(0,1fr)] gap-4">
      <div>
        <Link
          to={`/strategies/${id}`}
          className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          {name ?? 'Strategy'}
        </Link>
        <h1 className="m-0 mt-1 text-[22px] font-semibold tracking-[-0.015em]">Versions</h1>
      </div>
      {name === undefined && detail.status === 'loading' ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <VersionsView
          strategyId={id}
          strategyName={name ?? 'Strategy'}
          sessionVersion={detail.session.version}
        />
      )}
    </div>
  );
}
