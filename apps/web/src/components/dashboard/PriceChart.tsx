import {
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { useEffect, useRef } from 'react';

import type { Candle, ChartType } from '@llamatrade/core/stores/markets';

import { DOWN, UP } from './format';

interface PriceChartProps {
  candles: Candle[];
  type: ChartType;
}

const INK = '#0d0d0d';
const HAIRLINE = 'rgba(13,13,13,0.08)';
const AXIS = 'rgba(13,13,13,0.15)';
const TEXT = 'rgba(13,13,13,0.55)';
const MONO = "'Space Mono', ui-monospace, monospace";
const VOL_UP = 'rgba(15,122,52,0.28)';
const VOL_DOWN = 'rgba(200,30,30,0.28)';

/** Monolith-themed candlestick/line price chart with a volume histogram. Fills its parent. */
export default function PriceChart({ candles, type }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const priceRef = useRef<ISeriesApi<'Candlestick'> | ISeriesApi<'Line'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);

  // Chart + series lifecycle. Rebuilt only when the series type changes.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight,
      autoSize: false,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: TEXT,
        fontFamily: MONO,
        fontSize: 10,
      },
      grid: { vertLines: { color: HAIRLINE }, horzLines: { color: HAIRLINE } },
      rightPriceScale: { borderColor: AXIS },
      timeScale: { borderColor: AXIS, timeVisible: true, secondsVisible: false },
      crosshair: {
        vertLine: { color: INK, width: 1, style: 3, labelBackgroundColor: INK },
        horzLine: { color: INK, width: 1, style: 3, labelBackgroundColor: INK },
      },
      handleScroll: false,
      handleScale: false,
    });

    const price =
      type === 'candlestick'
        ? chart.addCandlestickSeries({
            upColor: UP,
            downColor: DOWN,
            borderUpColor: UP,
            borderDownColor: DOWN,
            wickUpColor: UP,
            wickDownColor: DOWN,
          })
        : chart.addLineSeries({ color: INK, lineWidth: 2 });

    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
      priceLineVisible: false,
      lastValueVisible: false,
    });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });

    chartRef.current = chart;
    priceRef.current = price;
    volumeRef.current = volume;

    // Fill the container in both dimensions; the parent's flex layout drives the height.
    const resize = () => chart.applyOptions({ width: el.clientWidth, height: el.clientHeight });
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(el);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      priceRef.current = null;
      volumeRef.current = null;
    };
  }, [type]);

  // Data. Re-applied when candles change, or after a type rebuild.
  useEffect(() => {
    const price = priceRef.current;
    const volume = volumeRef.current;
    const chart = chartRef.current;
    if (!price || !volume || !chart) return;

    if (type === 'candlestick') {
      (price as ISeriesApi<'Candlestick'>).setData(
        candles.map((c) => ({
          time: c.time as UTCTimestamp,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }))
      );
    } else {
      (price as ISeriesApi<'Line'>).setData(
        candles.map((c) => ({ time: c.time as UTCTimestamp, value: c.close }))
      );
    }

    volume.setData(
      candles.map((c) => ({
        time: c.time as UTCTimestamp,
        value: c.volume,
        color: c.close >= c.open ? VOL_UP : VOL_DOWN,
      }))
    );

    chart.timeScale().fitContent();
  }, [candles, type]);

  return <div ref={containerRef} className="flex-1 min-h-0 w-full" />;
}
