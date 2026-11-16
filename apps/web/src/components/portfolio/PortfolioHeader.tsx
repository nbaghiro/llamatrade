import { Plus } from 'lucide-react';
import { Link } from 'react-router-dom';

import { accountLine } from './sleeveView';

interface PortfolioHeaderProps {
  /** Open positions across sleeves; null when unknown. */
  openPositions: number | null;
  loading: boolean;
  onAddFunds: () => void;
  onDeploy: () => void;
}

/** Title, the account line and the page's three actions. Phones shorten the labels to keep one row. */
export function PortfolioHeader({
  openPositions,
  loading,
  onAddFunds,
  onDeploy,
}: PortfolioHeaderProps) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <h1 className="m-0 text-[22px] font-semibold tracking-[-0.02em] max-md:text-[26px]">
          Portfolio
        </h1>
        <div className="mt-0.5 text-[13px] text-fg-3">{accountLine(openPositions, loading)}</div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Link to="/portfolio/activity" className="btn btn-secondary">
          Activity
        </Link>
        <button type="button" className="btn btn-secondary" onClick={onAddFunds}>
          <Plus className="h-3.5 w-3.5" />
          <span className="md:hidden">Add funds</span>
          <span className="max-md:hidden">Add paper funds</span>
        </button>
        <button type="button" className="btn btn-primary" onClick={onDeploy}>
          <span className="md:hidden">Deploy</span>
          <span className="max-md:hidden">Deploy a strategy</span>
        </button>
      </div>
    </div>
  );
}
