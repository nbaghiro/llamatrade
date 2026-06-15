/**
 * Connect RPC telemetry interceptor.
 *
 * For every RPC it:
 *   - injects a W3C `traceparent` header so the backend server span links to the
 *     originating browser call,
 *   - measures client-side latency,
 *   - emits an `rpc` event with status (`ok`/`error`) and Connect code on failure.
 *
 * It never swallows the call result/error — it only observes and re-throws.
 */

import { Code, ConnectError, type Interceptor } from '@connectrpc/connect';

import { emit } from './sink';
import { createTraceContext } from './trace';

function roundMs(value: number): number {
  return Math.round(value * 100) / 100;
}

export const telemetryInterceptor: Interceptor = (next) => async (req) => {
  const trace = createTraceContext();
  req.header.set('traceparent', trace.traceparent);

  const method = `${req.service.typeName}/${req.method.name}`;
  const start = performance.now();

  try {
    const res = await next(req);
    emit({
      type: 'rpc',
      name: method,
      timestamp: Date.now(),
      attributes: {
        'rpc.duration_ms': roundMs(performance.now() - start),
        'rpc.status': 'ok',
        'trace.id': trace.traceId,
      },
    });
    return res;
  } catch (err) {
    const code = Code[ConnectError.from(err).code];
    emit({
      type: 'rpc',
      name: method,
      timestamp: Date.now(),
      attributes: {
        'rpc.duration_ms': roundMs(performance.now() - start),
        'rpc.status': 'error',
        'rpc.code': code,
        'trace.id': trace.traceId,
      },
    });
    throw err;
  }
};
