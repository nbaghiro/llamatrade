import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { describe, expect, it } from 'vitest';

import { runStateOf } from '../runState';

describe('runStateOf', () => {
  it('maps execution statuses to run states', () => {
    expect(runStateOf(ExecutionStatus.RUNNING, false)).toBe('running');
    expect(runStateOf(ExecutionStatus.PAUSED, false)).toBe('paused');
    expect(runStateOf(ExecutionStatus.ERROR, false)).toBe('error');
    expect(runStateOf(ExecutionStatus.PENDING, false)).toBe('waiting');
    expect(runStateOf(ExecutionStatus.STOPPED, false)).toBe('stopped');
    expect(runStateOf(ExecutionStatus.UNSPECIFIED, false)).toBe('stopped');
  });

  it('shows a frozen sleeve as frozen whatever the execution reports', () => {
    expect(runStateOf(ExecutionStatus.RUNNING, true)).toBe('frozen');
  });
});
