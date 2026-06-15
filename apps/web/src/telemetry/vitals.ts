/**
 * Core Web Vitals capture.
 *
 * Uses the `web-vitals` library (LCP / INP / CLS / TTFB). Each metric is emitted
 * as a `web_vital` telemetry event with its value and rating.
 */

import { onCLS, onINP, onLCP, onTTFB, type Metric } from 'web-vitals';

import { emit } from './sink';

function report(metric: Metric): void {
  emit({
    type: 'web_vital',
    name: metric.name,
    timestamp: Date.now(),
    attributes: {
      value: Math.round(metric.value * 1000) / 1000,
      rating: metric.rating,
      'metric.id': metric.id,
      'metric.delta': Math.round(metric.delta * 1000) / 1000,
    },
  });
}

let installed = false;

/**
 * Begin observing Core Web Vitals. Idempotent and safe outside the browser.
 */
export function initWebVitals(): void {
  if (installed || typeof window === 'undefined') return;
  installed = true;
  onLCP(report);
  onINP(report);
  onCLS(report);
  onTTFB(report);
}
