import { Search, TrendingUp } from 'lucide-react';
import { useState, useMemo } from 'react';

import { useStrategyBuilderStore } from '../../../store/strategy-builder';
import type { BlockId } from '../../../types/strategy-builder';

// Stubbed asset data - in production this would come from an API
const STUB_ASSETS = [
  { symbol: 'AAPL', exchange: 'NASDAQ', displayName: 'Apple Inc.' },
  { symbol: 'MSFT', exchange: 'NASDAQ', displayName: 'Microsoft Corp.' },
  { symbol: 'GOOGL', exchange: 'NASDAQ', displayName: 'Alphabet Inc.' },
  { symbol: 'AMZN', exchange: 'NASDAQ', displayName: 'Amazon.com Inc.' },
  { symbol: 'META', exchange: 'NASDAQ', displayName: 'Meta Platforms Inc.' },
  { symbol: 'NVDA', exchange: 'NASDAQ', displayName: 'NVIDIA Corp.' },
  { symbol: 'TSLA', exchange: 'NASDAQ', displayName: 'Tesla Inc.' },
  { symbol: 'JPM', exchange: 'NYSE', displayName: 'JPMorgan Chase & Co.' },
  { symbol: 'V', exchange: 'NYSE', displayName: 'Visa Inc.' },
  { symbol: 'JNJ', exchange: 'NYSE', displayName: 'Johnson & Johnson' },
  { symbol: 'SPY', exchange: 'NYSE', displayName: 'SPDR S&P 500 ETF' },
  { symbol: 'QQQ', exchange: 'NASDAQ', displayName: 'Invesco QQQ Trust' },
  { symbol: 'VTI', exchange: 'NYSE', displayName: 'Vanguard Total Stock Market ETF' },
  { symbol: 'IWM', exchange: 'NYSE', displayName: 'iShares Russell 2000 ETF' },
  { symbol: 'GLD', exchange: 'NYSE', displayName: 'SPDR Gold Trust' },
  { symbol: 'BTC', exchange: 'CRYPTO', displayName: 'Bitcoin' },
  { symbol: 'ETH', exchange: 'CRYPTO', displayName: 'Ethereum' },
];

interface AssetPickerProps {
  parentId: BlockId;
  onClose: () => void;
}

export function AssetPicker({ parentId, onClose }: AssetPickerProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const addAsset = useStrategyBuilderStore((s) => s.addAsset);

  const filteredAssets = useMemo(() => {
    if (!searchQuery.trim()) {
      return STUB_ASSETS.slice(0, 8);
    }
    const query = searchQuery.toLowerCase();
    return STUB_ASSETS.filter(
      (asset) =>
        asset.symbol.toLowerCase().includes(query) ||
        asset.displayName.toLowerCase().includes(query)
    ).slice(0, 8);
  }, [searchQuery]);

  const handleSelect = (asset: (typeof STUB_ASSETS)[0]) => {
    addAsset(parentId, asset.symbol, asset.exchange, asset.displayName);
    onClose();
  };

  return (
    <div className="p-2">
      <div className="relative mb-2">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
        <input
          type="text"
          placeholder="Search symbols..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          autoFocus
          className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder:text-gray-400 outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400"
        />
      </div>

      <div className="max-h-[240px] overflow-y-auto">
        {filteredAssets.length === 0 ? (
          <div className="px-3 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
            No assets found
          </div>
        ) : (
          filteredAssets.map((asset) => (
            <button
              key={asset.symbol}
              onClick={() => handleSelect(asset)}
              className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <div className="p-1 bg-emerald-100 dark:bg-emerald-900/30 rounded">
                <TrendingUp className="w-3 h-3 text-emerald-600 dark:text-emerald-400" />
              </div>
              <div className="flex-1 text-left">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                    {asset.symbol}
                  </span>
                  <span className="px-1.5 py-0.5 text-[10px] font-medium bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 rounded">
                    {asset.exchange}
                  </span>
                </div>
                <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                  {asset.displayName}
                </div>
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
