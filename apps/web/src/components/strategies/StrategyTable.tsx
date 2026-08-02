import type { SortColumn, SortDirection } from '@llamatrade/core/stores/strategies';
import { ArrowDown, ArrowUp, ChevronsUpDown, Pencil, Play } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useRunConsole } from '../../store/runConsole';

import { MiniChart } from './MiniChart';
import {
  formatMoneyFull,
  formatMoneyShort,
  formatReturn,
  pillClass,
  type StrategyRowView,
} from './strategyRow';

interface StrategyTableProps {
  rows: StrategyRowView[];
  totalCount: number;
  totalAllocated: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
  sortColumn: SortColumn;
  sortDirection: SortDirection;
  onSort: (column: SortColumn) => void;
}

// Shared column template so the header labels line up with every row's cells.
const GRID = 'minmax(0,1fr) 108px 92px 60px 132px 72px';

interface HeaderCellProps {
  label: string;
  column: SortColumn;
  active: boolean;
  direction: SortDirection;
  onSort: (column: SortColumn) => void;
}

function SortHead({ label, column, active, direction, onSort }: HeaderCellProps) {
  const Arrow = !active ? ChevronsUpDown : direction === 'asc' ? ArrowUp : ArrowDown;
  return (
    <button
      onClick={() => onSort(column)}
      className={`flex items-center justify-end gap-1 font-mono text-[9.5px] font-bold uppercase tracking-wider transition-colors ${
        active ? 'text-ink' : 'text-ink/50 hover:text-ink'
      }`}
    >
      {label}
      <Arrow className={`h-2.5 w-2.5 ${active ? 'text-orange-500' : 'text-ink/30'}`} />
    </button>
  );
}

function Chip({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap border-[1.5px] border-ink px-1.5 py-[2px] font-mono text-[9px] font-bold uppercase tracking-wide ${className}`}
    >
      {children}
    </span>
  );
}

export function StrategyTable({
  rows,
  totalCount,
  totalAllocated,
  selectedId,
  onSelect,
  sortColumn,
  sortDirection,
  onSort,
}: StrategyTableProps) {
  const maxAllocation = Math.max(1, ...rows.map((r) => r.allocation ?? 0));
  const openRunConsole = useRunConsole((s) => s.openRunConsole);

  return (
    <div className="min-w-0">
      {/* Column header — transparent 2px border mirrors the rows' frame so columns align. */}
      <div
        className="grid items-center gap-x-4 border-2 border-transparent pb-1.5 pl-4 pr-3"
        style={{ gridTemplateColumns: GRID }}
      >
        <span className="font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink/50">Strategy</span>
        <span className="text-center font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink/50">Trend</span>
        <SortHead label="Return" column="return" active={sortColumn === 'return'} direction={sortDirection} onSort={onSort} />
        <SortHead label="Sharpe" column="sharpe" active={sortColumn === 'sharpe'} direction={sortDirection} onSort={onSort} />
        <SortHead label="Allocation" column="allocation" active={sortColumn === 'allocation'} direction={sortDirection} onSort={onSort} />
        <span />
      </div>

      {/* Rows */}
      <div className="flex flex-col gap-2.5">
        {rows.map((row) => {
          const selected = row.strategy.id === selectedId;
          const rebalance = (row.strategy.rebalance || 'daily').toUpperCase();
          const positions = row.strategy.symbols.length;
          const deployed = row.pill === 'LIVE' || row.pill === 'PAPER';
          return (
            <div
              key={row.strategy.id}
              onClick={() => onSelect(row.strategy.id)}
              className={`relative grid cursor-pointer items-center gap-x-4 border-2 bg-paper pl-4 pr-3 transition-colors ${
                selected
                  ? 'border-orange-500 bg-orange-500/[0.04]'
                  : 'border-ink hover:bg-ink/[0.02]'
              }`}
              style={{ gridTemplateColumns: GRID }}
            >
              {/* Status rail */}
              <span
                aria-hidden="true"
                className="absolute inset-y-0 left-0 w-[5px]"
                style={{ background: row.color }}
              />

              {/* Name + chips */}
              <div className="min-w-0 py-3">
                <div className="truncate text-[14.5px] font-bold leading-tight text-ink">{row.strategy.name}</div>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Chip className={pillClass(row.pill)}>{row.pill}</Chip>
                  <Chip className="text-ink/70">{rebalance}</Chip>
                  <Chip className="text-ink/70">{positions} pos</Chip>
                </div>
              </div>

              {/* Trend */}
              <div className="flex justify-center">
                {row.equityCurve.length > 1 ? (
                  <MiniChart
                    data={row.equityCurve}
                    benchmarkData={row.benchmarkCurve}
                    positive={(row.returnPct ?? 0) >= 0}
                    width={80}
                    height={26}
                    showBenchmark={false}
                    showFill={false}
                    dashed={!deployed}
                  />
                ) : (
                  <span className="font-mono text-[9px] uppercase tracking-wide text-ink/30">no data</span>
                )}
              </div>

              {/* Return */}
              <div className="text-right font-mono text-[13px] font-bold tabular-nums">
                {row.returnPct === null ? (
                  <span className="text-ink/35">—</span>
                ) : (
                  <span className={row.returnPct >= 0 ? 'text-green-500' : 'text-red-500'}>
                    {formatReturn(row.returnPct)}
                    {row.returnIsBacktest && <span className="text-[8px] text-ink/40"> bt</span>}
                  </span>
                )}
              </div>

              {/* Sharpe */}
              <div className="text-right font-mono text-[13px] font-bold tabular-nums text-ink">
                {row.sharpe === null ? <span className="text-ink/35">—</span> : row.sharpe.toFixed(2)}
              </div>

              {/* Allocation — only where it exists */}
              <div className="text-right">
                {row.allocation === null ? (
                  <span className="font-mono text-[10px] uppercase tracking-wide text-ink/35">
                    {row.pill === 'DRAFT' ? 'not deployed' : '—'}
                  </span>
                ) : (
                  <div className="inline-flex flex-col items-end gap-1">
                    <span className="font-mono text-[13px] font-bold tabular-nums text-ink">
                      {formatMoneyShort(row.allocation)}
                    </span>
                    <span className="relative h-1.5 w-[72px] border-[1.5px] border-ink bg-bone">
                      <span
                        className="absolute inset-y-0 left-0"
                        style={{
                          width: `${Math.min(100, (row.allocation / maxAllocation) * 100)}%`,
                          background: row.color,
                        }}
                      />
                    </span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="flex justify-end gap-1.5">
                <Link
                  to={`/strategies/${row.strategy.id}`}
                  onClick={(e) => e.stopPropagation()}
                  title="Edit"
                  className="grid h-7 w-7 place-items-center border-[1.5px] border-ink bg-paper transition-colors hover:bg-ink hover:text-bone"
                >
                  <Pencil className="h-3 w-3" />
                </Link>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    openRunConsole(row.strategy.id, row.strategy.name);
                  }}
                  title="Backtest"
                  className="grid h-7 w-7 place-items-center border-[1.5px] border-ink bg-paper transition-colors hover:bg-ink hover:text-bone"
                >
                  <Play className="h-3 w-3" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer */}
      <div className="mt-3 flex items-center justify-between border-t-2 border-ink px-1 pt-3 font-mono text-[10.5px] font-bold uppercase tracking-wide text-ink/50">
        <span>
          {rows.length} of {totalCount} {totalCount === 1 ? 'strategy' : 'strategies'}
        </span>
        <span>Total allocated · {formatMoneyFull(totalAllocated)}</span>
      </div>
    </div>
  );
}
