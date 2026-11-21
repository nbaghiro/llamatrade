import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useEffect, useRef, useState } from 'react';

/** Loads a strategy's latest run once its row scrolls near the screen. */
export function useLazyRun(strategyId: string) {
  const ref = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  const run = useStrategiesStore((s) => s.runs[strategyId]);
  const fetchStrategyRun = useStrategiesStore((s) => s.fetchStrategyRun);
  useEffect(() => {
    const el = ref.current;
    if (!el || seen) return;
    if (typeof IntersectionObserver === 'undefined') {
      setSeen(true);
      return;
    }
    const io = new IntersectionObserver((e) => e.some((x) => x.isIntersecting) && setSeen(true), {
      rootMargin: '160px',
    });
    io.observe(el);
    return () => io.disconnect();
  }, [seen]);
  useEffect(() => {
    if (seen) fetchStrategyRun(strategyId).catch(() => undefined);
  }, [seen, strategyId, fetchStrategyRun]);
  return { ref, run };
}
