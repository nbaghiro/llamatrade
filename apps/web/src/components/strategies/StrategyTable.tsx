import type { SortColumn, SortDirection } from '@llamatrade/core/stores/strategies';
import { ArrowDown, ArrowUp, ChevronsUpDown, Pencil, Play } from 'lucide-react';
import { Link } from 'react-router-dom';


import { MiniChart } from './MiniChart';
import {
  formatMoneyFull,
  formatMoneyShort,
  formatReturn,
  formatUpdated,
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

interface SortHeaderProps {
  label: string;
  column: SortColumn;
  active: boolean;
  direction: SortDirection;
  onSort: (column: SortColumn) => void;
}

function SortHeader({ label, column, active, direction, onSort }: SortHeaderProps) {
  const Arrow = !active ? ChevronsUpDown : direction === 'asc' ? ArrowUp : ArrowDown;
  return (
    <th
      onClick={() => onSort(column)}
      className={`px-3 py-3 text-right font-mono text-[9.5px] font-bold uppercase tracking-wider whitespace-nowrap cursor-pointer select-none border-b-2 border-ink ${
        active ? 'text-ink' : 'text-ink/50'
      }`}
    >
      <span className="inline-flex items-center gap-1 justify-end">
        {label}
        <Arrow className={`w-2.5 h-2.5 ${active ? 'text-orange-500' : 'text-ink/30'}`} />
      </span>
    </th>
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

  return (
    <div className="card-shadow">
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="px-3 py-3 text-left font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink/50 border-b-2 border-ink">
              Strategy
            </th>
            <th className="px-3 py-3 text-left font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink/50 border-b-2 border-ink">
              Status
            </th>
            <th className="px-3 py-3 text-center font-mono text-[9.5px] font-bold uppercase tracking-wider text-ink/50 border-b-2 border-ink">
              Trend
            </th>
            <SortHeader label="Return" column="return" active={sortColumn === 'return'} direction={sortDirection} onSort={onSort} />
            <SortHeader label="Sharpe" column="sharpe" active={sortColumn === 'sharpe'} direction={sortDirection} onSort={onSort} />
            <SortHeader label="Allocation" column="allocation" active={sortColumn === 'allocation'} direction={sortDirection} onSort={onSort} />
            <SortHeader label="Updated" column="updated" active={sortColumn === 'updated'} direction={sortDirection} onSort={onSort} />
            <th className="border-b-2 border-ink" />
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const selected = row.strategy.id === selectedId;
            const muted = row.pill === 'DRAFT' || row.pill === 'PAUSED' || row.pill === 'ARCHIVED';
            return (
              <tr
                key={row.strategy.id}
                onClick={() => onSelect(row.strategy.id)}
                className={`cursor-pointer border-b border-ink/10 ${
                  selected ? 'bg-orange-500/[0.06]' : 'hover:bg-ink/[0.03]'
                }`}
              >
                <td
                  className={`px-3 py-3 align-middle ${
                    selected ? 'shadow-[inset_4px_0_0_rgb(var(--lt-orange-500))]' : ''
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="w-[11px] h-[11px] flex-none border-2 border-ink"
                      style={{ background: row.color }}
                    />
                    <div className="min-w-0">
                      <div className="font-bold text-[13.5px] leading-tight truncate text-ink">
                        {row.strategy.name}
                      </div>
                      <div className="font-mono text-[9px] uppercase tracking-wide text-ink/50 mt-0.5 truncate">
                        {row.meta}
                      </div>
                    </div>
                  </div>
                </td>

                <td className="px-3 py-3 align-middle">
                  <span
                    className={`inline-flex items-center px-[7px] py-[3px] font-mono text-[9px] font-bold uppercase tracking-wide border-[1.5px] border-ink whitespace-nowrap ${pillClass(
                      row.pill
                    )}`}
                  >
                    {row.pill}
                  </span>
                </td>

                <td className="px-3 py-3 align-middle">
                  <div className="flex justify-center">
                    {row.equityCurve.length > 1 ? (
                      <MiniChart
                        data={row.equityCurve}
                        benchmarkData={row.benchmarkCurve}
                        positive={(row.returnPct ?? 0) >= 0}
                        width={72}
                        height={24}
                        showBenchmark={false}
                        showFill={false}
                        dashed={row.pill !== 'LIVE' && row.pill !== 'PAPER'}
                      />
                    ) : (
                      <span className="font-mono text-[9px] uppercase tracking-wide text-ink/30">no data</span>
                    )}
                  </div>
                </td>

                <td className="px-3 py-3 align-middle text-right font-mono font-bold text-[13px] tabular-nums">
                  {row.returnPct === null ? (
                    <span className="text-ink/40">—</span>
                  ) : (
                    <span className={row.returnPct >= 0 ? 'text-green-500' : 'text-red-500'}>
                      {formatReturn(row.returnPct)}
                      {row.returnIsBacktest && <span className="text-[8px] text-ink/40"> bt</span>}
                    </span>
                  )}
                </td>

                <td className="px-3 py-3 align-middle text-right font-mono font-bold text-[13px] tabular-nums text-ink">
                  {row.sharpe === null ? <span className="text-ink/40">—</span> : row.sharpe.toFixed(2)}
                </td>

                <td className="px-3 py-3 align-middle">
                  {row.allocation === null ? (
                    <div className="text-right font-mono text-[11px] text-ink/40">—</div>
                  ) : (
                    <div className="flex items-center justify-end gap-2">
                      <span className="w-[46px] h-1.5 flex-none border-[1.5px] border-ink bg-bone relative">
                        <span
                          className="absolute inset-y-0 left-0"
                          style={{
                            width: `${Math.min(100, (row.allocation / maxAllocation) * 100)}%`,
                            background: row.color,
                          }}
                        />
                      </span>
                      <span className="font-mono font-bold text-[13px] tabular-nums text-ink">
                        {formatMoneyShort(row.allocation)}
                      </span>
                    </div>
                  )}
                </td>

                <td
                  className={`px-3 py-3 align-middle text-right font-mono text-[11px] whitespace-nowrap ${
                    muted ? 'text-ink/50' : 'text-ink/55'
                  }`}
                >
                  {formatUpdated(row.strategy.updatedAt)}
                </td>

                <td className="px-3 py-3 align-middle">
                  <div className="flex gap-1.5 justify-end">
                    <Link
                      to={`/strategies/${row.strategy.id}`}
                      onClick={(e) => e.stopPropagation()}
                      title="Edit"
                      className="w-7 h-7 border-[1.5px] border-ink grid place-items-center bg-paper hover:bg-ink hover:text-bone transition-colors"
                    >
                      <Pencil className="w-3 h-3" />
                    </Link>
                    <Link
                      to={`/backtest?strategy=${row.strategy.id}`}
                      onClick={(e) => e.stopPropagation()}
                      title="Backtest"
                      className="w-7 h-7 border-[1.5px] border-ink grid place-items-center bg-paper hover:bg-ink hover:text-bone transition-colors"
                    >
                      <Play className="w-3 h-3" />
                    </Link>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="flex items-center justify-between px-4 py-3 font-mono text-[10.5px] font-bold uppercase tracking-wide text-ink/50 border-t-2 border-ink">
        <span>
          {rows.length} of {totalCount} {totalCount === 1 ? 'strategy' : 'strategies'}
        </span>
        <span>Total allocated · {formatMoneyFull(totalAllocated)}</span>
      </div>
    </div>
  );
}
