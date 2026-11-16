import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';

import type { RunState } from '../ui';

/** A deployment's state for StatusMark. A frozen sleeve outranks whatever the execution reports. */
export function runStateOf(status: ExecutionStatus, frozen: boolean): RunState {
  if (frozen) return 'frozen';
  switch (status) {
    case ExecutionStatus.RUNNING:
      return 'running';
    case ExecutionStatus.PAUSED:
      return 'paused';
    case ExecutionStatus.ERROR:
      return 'error';
    case ExecutionStatus.PENDING:
      return 'waiting';
    default:
      return 'stopped';
  }
}
