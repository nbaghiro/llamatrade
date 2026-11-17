import type { ConditionExpression } from '@llamatrade/core/strategy/types';
import { Sparkles } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { CATEGORY_LABELS } from '../../../data/strategy-templates';
import { isValidSymbol, normaliseSymbol } from '../../../lib/outline';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { FEATURED_TEMPLATES, pickTemplates } from '../../strategies/templateModel';
import { useTemplates } from '../../strategies/useTemplates';
import { Skeleton } from '../../ui';

const DEFAULT_CONDITION: ConditionExpression = {
  left: { type: 'indicator', indicator: 'rsi', period: 14, symbol: 'SPY' },
  comparator: 'gt',
  right: { type: 'number', value: 70 },
};

interface StartWaysProps {
  onDescribe: (text: string) => void;
  onTemplate: (templateId: string) => void;
  /** False on a phone, where adding rules one by one is left to the web. */
  blocks?: boolean;
}

function Way({
  n,
  title,
  rim = false,
  children,
}: {
  n: string;
  title: string;
  rim?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div
      className={`flex min-w-0 flex-col gap-3 rounded-panel border bg-panel p-4 ${
        rim ? 'border-accent/50 shadow-[0_0_0_3px_var(--accent-soft)]' : 'border-line'
      }`}
    >
      <span className="font-mono text-[11px] text-fg-3">{n}</span>
      <b className="text-[15px] font-semibold leading-snug text-fg">{title}</b>
      {children}
    </div>
  );
}

/** start2 A: the empty rules area holds the three ways to start, side by side. */
export function StartWays({ onDescribe, onTemplate, blocks = true }: StartWaysProps) {
  const store = useStrategyBuilderStoreWithContext();
  const templates = useTemplates();
  const [text, setText] = useState('');
  const [asset, setAsset] = useState<string | null>(null);
  const [assetError, setAssetError] = useState<string | null>(null);
  const root = store.tree.rootId;

  const describe = (e: FormEvent) => {
    e.preventDefault();
    if (text.trim()) onDescribe(text.trim());
  };

  const addAsset = (e: FormEvent) => {
    e.preventDefault();
    if (!asset || !isValidSymbol(asset)) {
      setAssetError('Enter a ticker, for example VTI.');
      return;
    }
    const symbol = normaliseSymbol(asset);
    const weight = store.addWeight(root, 'equal');
    store.addAsset(weight, symbol, '', symbol);
  };

  const shown =
    templates.status === 'ready' ? pickTemplates(templates.templates, FEATURED_TEMPLATES, 4) : [];
  const blockButton =
    'flex h-9 items-center gap-2.5 rounded-[6px] border border-dashed border-line-strong px-3 text-left font-mono text-[12.5px] text-fg hover:border-accent hover:bg-sunk';

  return (
    <div className={`grid gap-3 p-4 ${blocks ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
      <Way n="1 · Describe it" title="Tell Copilot what it should do" rim>
        <form onSubmit={describe} className="flex flex-1 flex-col gap-3">
          <label className="sr-only" htmlFor="describe-strategy">
            Describe the strategy
          </label>
          <textarea
            id="describe-strategy"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder="For example: hold the strongest of a few stock ETFs, and move to bonds and gold when the market looks overbought."
            className="input min-h-[140px] flex-1 resize-none py-2 leading-relaxed"
          />
          <span className="flex items-center gap-2">
            <span className="flex items-center gap-1.5 text-[12px] text-fg-2">
              <Sparkles className="h-3.5 w-3.5 text-accent" aria-hidden="true" />
              Asks first, then drafts
            </span>
            <button
              type="submit"
              disabled={!text.trim()}
              className="btn btn-primary btn-sm ml-auto"
            >
              Draft it
            </button>
          </span>
        </form>
      </Way>

      <Way n="2 · Copy a template" title="Start from a strategy that already runs">
        <div className="grid gap-1.5">
          {templates.status === 'loading' &&
            [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9 w-full" />)}
          {templates.status === 'error' && (
            <p className="m-0 text-[12.5px] text-fg-2">
              Templates couldn’t be loaded.{' '}
              <button type="button" onClick={templates.retry} className="text-accent">
                Try again
              </button>
            </p>
          )}
          {shown.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => onTemplate(t.id)}
              className="flex h-9 items-center justify-between gap-2 rounded-[6px] border border-line px-3 text-left text-[13px] text-fg hover:border-line-strong hover:bg-sunk"
            >
              <span className="truncate">{t.name}</span>
              <span className="flex-none text-[11.5px] text-fg-3">
                {CATEGORY_LABELS[t.category]}
              </span>
            </button>
          ))}
        </div>
        <Link to="/strategies/templates" className="text-[12.5px] text-accent hover:underline">
          {templates.status === 'ready'
            ? `Browse ${templates.templates.length} templates`
            : 'Browse templates'}
        </Link>
      </Way>

      {blocks && (
        <Way n="3 · Add the first block" title="Build it rule by rule">
          <p className="m-0 text-[12.5px] text-fg-2">
            Most strategies start with a condition or a set of weights.
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            <button
              type="button"
              className={blockButton}
              onClick={() => store.addCondition(root, DEFAULT_CONDITION)}
            >
              if
            </button>
            <button
              type="button"
              className={blockButton}
              onClick={() => store.addWeight(root, 'specified')}
            >
              weight
            </button>
            <button
              type="button"
              className={blockButton}
              onClick={() =>
                store.addFilter(root, {
                  selection: 'top',
                  count: 3,
                  universe: 'custom',
                  sortBy: 'momentum',
                  period: '3m',
                  lookbackDays: 90,
                })
              }
            >
              filter
            </button>
            <button
              type="button"
              className={blockButton}
              onClick={() => {
                const weight = store.addWeight(root, 'specified');
                store.addGroup(weight, 'Group');
              }}
            >
              group
            </button>
            <button type="button" className={blockButton} onClick={() => setAsset('')}>
              asset
            </button>
            <button
              type="button"
              onClick={() => store.setViewMode('code')}
              className="flex h-9 items-center rounded-[6px] border border-line px-3 text-left text-[12.5px] text-fg hover:bg-sunk"
            >
              Paste code
            </button>
          </div>
          {asset !== null && (
            <form onSubmit={addAsset} className="grid gap-1.5">
              <label className="text-[12px] text-fg-2" htmlFor="first-asset">
                Ticker to hold
              </label>
              <span className="flex gap-1.5">
                <input
                  id="first-asset"
                  autoFocus
                  value={asset}
                  placeholder="VTI"
                  onChange={(e) => {
                    setAssetError(null);
                    setAsset(e.target.value.toUpperCase());
                  }}
                  className={`input h-8 font-mono ${assetError ? 'input-error' : ''}`}
                />
                <button type="submit" className="btn btn-primary btn-sm">
                  Add
                </button>
              </span>
              {assetError && <span className="text-[12px] text-risk">{assetError}</span>}
            </form>
          )}
        </Way>
      )}
    </div>
  );
}

/** The faint shape of rules under the three ways, so the empty area says what will appear. */
export function EmptyRulesHint() {
  return (
    <div aria-hidden="true" className="grid gap-3 border-t border-line px-5 py-4">
      {['When', 'Otherwise'].map((k) => (
        <div key={k} className="grid grid-cols-[80px_minmax(0,1fr)] items-center gap-3">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.06em] text-fg-3">{k}</span>
          <span className="grid gap-2">
            <i className="block h-2 w-48 max-w-full rounded-full bg-sunk" />
            <i className="block h-2 w-64 max-w-full rounded-full bg-sunk" />
          </span>
        </div>
      ))}
      <p className="m-0 text-[12px] text-fg-3">
        Your rules appear here as sentences, with each value editable in place.
      </p>
    </div>
  );
}
