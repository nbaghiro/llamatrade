import { STAGES, TRACK_COLS } from './stageModel';
import { StageTrackHead } from './StageTrackTable';
import { ThreeWays } from './ThreeWays';

/** No strategies yet (empty2 A): the three ways in, over the stage track with nothing on it. */
export function StrategiesEmpty() {
  return (
    <div className="grid gap-5">
      <ThreeWays />
      <section
        aria-label="Where your strategies will appear"
        className="panel overflow-hidden max-lg:hidden"
      >
        <div role="table" aria-label="Strategy stages">
          <StageTrackHead next={false} />
          <div role="row" className={`grid ${TRACK_COLS} items-center border-b border-line`}>
            <div role="cell" className="px-5 py-4">
              <span className="block h-2 w-36 rounded-full bg-sunk" />
            </div>
            {STAGES.map((s, i) => (
              <div role="cell" key={s} className="relative px-3 py-4">
                {i < STAGES.length - 1 && (
                  <i className="absolute left-[18px] right-[-12px] top-1/2 border-t border-dashed border-fg-3/40" />
                )}
                <i
                  className={`relative block rounded-full ${
                    i === 0
                      ? 'h-[11px] w-[11px] border-[1.5px] border-dashed border-fg-3 bg-panel'
                      : 'ml-[3px] h-[5px] w-[5px] bg-fg-3/40'
                  }`}
                />
              </div>
            ))}
            <div role="cell" />
          </div>
          <div className="flex items-center justify-center px-5 py-3.5">
            <span className="rounded-full border border-line-strong bg-panel px-3.5 py-1.5 text-[12.5px] text-fg-2">
              Your first strategy appears here as a draft, then moves right as you test it.
            </span>
          </div>
        </div>
      </section>
    </div>
  );
}
