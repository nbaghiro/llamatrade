import { useDashboardStore } from '../../store/dashboard';

import { colorForSign, fmtCurrency, fmtSignedCurrency, fmtSignedPercent } from './format';

const EYEBROW = 'font-mono text-[9px] font-bold uppercase tracking-[0.13em]';

function Tile({
  label,
  value,
  meta,
  valueColor,
  metaColor,
}: {
  label: string;
  value: string;
  meta: string;
  valueColor?: string;
  metaColor?: string;
}) {
  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d] px-3.5 py-3">
      <div className={`${EYEBROW} text-ink/50`}>{label}</div>
      <div
        className="font-mono font-bold text-[18px] mt-1.5 tabular-nums tracking-[-0.01em]"
        style={valueColor ? { color: valueColor } : undefined}
      >
        {value}
      </div>
      <div
        className="font-mono text-[10.5px] font-bold mt-0.5 text-ink/50"
        style={metaColor ? { color: metaColor } : undefined}
      >
        {meta}
      </div>
    </div>
  );
}

export default function KpiRail() {
  const {
    totalEquity,
    dayPnl,
    dayPnlPercent,
    totalReturn,
    totalReturnPercent,
    freeCash,
    freeCashPercent,
    liveStrategiesCount,
    openPositionsCount,
    atAllTimeHigh,
  } = useDashboardStore();

  return (
    <div className="flex flex-col gap-3">
      {/* Total Equity — the one ink/dark-ground tile: orange offset shadow. */}
      <div className="bg-ink text-bone border-2 border-ink shadow-[4px_4px_0_#ff4d1c] px-3.5 py-3">
        <div className={`${EYEBROW} text-bone/50`}>Total Equity</div>
        <div className="font-mono font-bold text-[23px] mt-1.5 tabular-nums tracking-[-0.01em]">
          {fmtCurrency(totalEquity)}
        </div>
        <div className="font-mono text-[10.5px] font-bold mt-0.5" style={{ color: '#7fe0a0' }}>
          {atAllTimeHigh ? '↗ all-time high' : 'paper account'}
        </div>
      </div>

      <Tile
        label="Day P&L"
        value={fmtSignedCurrency(dayPnl)}
        valueColor={colorForSign(dayPnl)}
        meta={fmtSignedPercent(dayPnlPercent)}
        metaColor={colorForSign(dayPnl)}
      />
      <Tile
        label="Total Return"
        value={fmtSignedCurrency(totalReturn)}
        valueColor={colorForSign(totalReturn)}
        meta={fmtSignedPercent(totalReturnPercent)}
        metaColor={colorForSign(totalReturn)}
      />
      <Tile
        label="Free Cash"
        value={fmtCurrency(freeCash)}
        meta={`${freeCashPercent.toFixed(1)}% of book`}
      />
      <Tile
        label="Deployed"
        value={`${liveStrategiesCount} active`}
        meta={`${openPositionsCount} open position${openPositionsCount === 1 ? '' : 's'}`}
      />
    </div>
  );
}
