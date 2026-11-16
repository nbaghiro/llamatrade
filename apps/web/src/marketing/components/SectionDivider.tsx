import { useWidth } from '../../components/charts/useWidth';
import { AXIS_HEIGHT, AXIS_TICK_HEIGHT, axisTicks } from '../lib/dividers';

/** The price-axis divider above a section heading: "▸ 02 backtest" and a ticked rule. */
export function SectionDivider({ label }: { label: string }) {
  const [ref, width] = useWidth<HTMLSpanElement>(0);
  return (
    <div className="sdiv" aria-hidden="true">
      <span className="ax">
        <b>
          <em>▸</em>
          {label}
        </b>
        <span ref={ref} className="rule">
          {width > 0 && (
            <svg width={width} height={AXIS_HEIGHT} viewBox={`0 0 ${width} ${AXIS_HEIGHT}`}>
              <line x1={0} x2={width} y1={AXIS_HEIGHT - 0.5} y2={AXIS_HEIGHT - 0.5} />
              {axisTicks(width).map((x) => (
                <line
                  key={x}
                  x1={x + 0.5}
                  x2={x + 0.5}
                  y1={AXIS_HEIGHT - AXIS_TICK_HEIGHT}
                  y2={AXIS_HEIGHT}
                />
              ))}
            </svg>
          )}
        </span>
      </span>
    </div>
  );
}
