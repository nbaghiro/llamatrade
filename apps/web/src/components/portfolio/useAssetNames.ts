import { marketDataClient } from '@llamatrade/core/net';
import { useEffect, useState } from 'react';

/** Alpaca's name for each symbol, e.g. "iShares 20+ Year Treasury Bond ETF"; empty on failure. */
export function useAssetNames(symbols: readonly string[]): Readonly<Record<string, string>> {
  const key = [...new Set(symbols)].sort().join(',');
  const [names, setNames] = useState<Readonly<Record<string, string>>>({});
  useEffect(() => {
    if (!key) return;
    let live = true;
    marketDataClient
      .getAssets({ symbols: key.split(',') })
      .then((res) => {
        if (!live) return;
        const out: Record<string, string> = {};
        for (const [symbol, asset] of Object.entries(res.assets)) {
          if (asset.name) out[symbol] = asset.name;
        }
        setNames(out);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [key]);
  return names;
}
