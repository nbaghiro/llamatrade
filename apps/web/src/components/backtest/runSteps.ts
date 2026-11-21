import { longDate, type RunPhase } from '../../lib/backtestView';

export type StepState = 'done' | 'now' | 'todo' | 'stopped';

export interface RunStep {
  label: string;
  state: StepState;
}

/** Where each stage ends in the service's progress percent (backtest_service publish_phase). */
const STAGES: readonly { label: string; doneAt: number }[] = [
  { label: 'Strategy loaded', doneAt: 11 },
  { label: 'Compiled', doneAt: 20 },
  { label: 'Price history fetched', doneAt: 40 },
  { label: 'Simulating', doneAt: 85 },
  { label: 'Metrics and benchmark', doneAt: 100 },
];

/**
 * The run's stages from its progress percent: done ones ticked, the current one named with how
 * far it has got, and for a run that stopped, the stage it stopped in.
 */
export function runSteps(percent: number, phase: RunPhase, currentDate: string): RunStep[] {
  const p = phase === 'completed' ? 100 : Math.max(0, Math.min(100, percent));
  const stopped = phase === 'failed' || phase === 'cancelled';
  let current = STAGES.findIndex((s) => p < s.doneAt);
  if (current < 0) current = STAGES.length;
  return STAGES.map((s, i) => {
    if (i < current) return { label: s.label, state: 'done' };
    if (i > current || phase === 'pending') return { label: s.label, state: 'todo' };
    const date = currentDate ? ` · through ${longDate(new Date(`${currentDate}T00:00:00Z`))}` : '';
    const label = s.label === 'Simulating' ? `Simulating · ${Math.round(p)}%${date}` : s.label;
    return { label, state: stopped ? 'stopped' : 'now' };
  });
}

/** The stage a stopped run was in, in lower case for a sentence: "while simulating". */
export function stoppedStage(percent: number): string {
  const i = STAGES.findIndex((s) => percent < s.doneAt);
  const words = [
    'while loading the strategy',
    'while compiling',
    'while fetching price history',
    'while simulating',
    'while working out the metrics',
  ];
  return i < 0 ? 'at the end' : words[i];
}
