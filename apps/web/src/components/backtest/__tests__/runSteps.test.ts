import { describe, expect, it } from 'vitest';

import { runSteps, stoppedStage } from '../runSteps';

const states = (steps: ReturnType<typeof runSteps>) => steps.map((s) => s.state);

describe('runSteps', () => {
  it('waits on every stage while queued', () => {
    expect(states(runSteps(0, 'pending', ''))).toEqual(['todo', 'todo', 'todo', 'todo', 'todo']);
  });

  it('marks the stage in progress and names the simulated date', () => {
    const steps = runSteps(57, 'running', '2023-04-14');
    expect(states(steps)).toEqual(['done', 'done', 'done', 'now', 'todo']);
    expect(steps[3].label).toBe('Simulating · 57% · through Apr 14, 2023');
  });

  it('ticks everything once completed', () => {
    expect(states(runSteps(40, 'completed', ''))).toEqual(['done', 'done', 'done', 'done', 'done']);
  });

  it('marks where a failed run stopped', () => {
    expect(states(runSteps(30, 'failed', ''))).toEqual(['done', 'done', 'stopped', 'todo', 'todo']);
  });

  it('names the stopped stage for a sentence', () => {
    expect(stoppedStage(68)).toBe('while simulating');
    expect(stoppedStage(5)).toBe('while loading the strategy');
    expect(stoppedStage(100)).toBe('at the end');
  });
});
