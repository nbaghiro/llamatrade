import type { StrategyTemplate } from '@llamatrade/core/proto/strategy_pb';
import { ChevronRight } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { CATEGORY_LABELS } from '../../data/strategy-templates';
import { listTemplates } from '../../services/strategy';
import { EmptyState, PanelError, SkeletonRows } from '../ui';

import { rankTemplates, templateMeta } from './templates';

const SHOWN = 3;

/** Three beginner templates, each opening the onboarding preview. */
export function StarterTemplates() {
  const [templates, setTemplates] = useState<StrategyTemplate[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    setFailed(false);
    setTemplates(null);
    listTemplates()
      .then((r) => setTemplates(rankTemplates(r.templates)))
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  return (
    <section
      aria-label="Templates to start from"
      className="overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-2.5 text-[12.5px]">
        <b className="font-semibold">Templates to start from</b>
        {templates && templates.length > 0 && (
          <Link to="/strategies/templates" className="text-accent hover:underline">
            All {templates.length}
          </Link>
        )}
      </div>
      {failed ? (
        <PanelError
          title="Templates couldn't be loaded"
          cause="The strategy service didn't answer."
          onRetry={load}
        />
      ) : !templates ? (
        <SkeletonRows rows={SHOWN} cols={2} />
      ) : templates.length === 0 ? (
        <EmptyState
          title="No templates yet"
          body="You can start from a blank strategy in the editor."
          actions={
            <Link to="/strategies/builder" className="btn btn-secondary">
              Open the editor
            </Link>
          }
        />
      ) : (
        <ul className="m-0 list-none p-0">
          {templates.slice(0, SHOWN).map((t) => (
            <li key={t.id} className="border-b border-line last:border-b-0">
              <Link
                to={`/welcome/template/${encodeURIComponent(t.id)}`}
                className="flex items-center gap-3 px-3.5 py-[9px] text-[12.5px] hover:bg-sunk"
              >
                <span className="min-w-0 flex-1">
                  <b className="block truncate font-semibold text-fg">{t.name}</b>
                  <span className="block truncate text-[11.5px] text-fg-3">{templateMeta(t)}</span>
                </span>
                <span className="badge hidden uppercase tracking-[0.05em] sm:inline-flex">
                  {CATEGORY_LABELS[t.category]}
                </span>
                <span className="btn btn-secondary btn-sm hidden md:inline-flex">Preview</span>
                <ChevronRight aria-hidden="true" className="h-4 w-4 text-fg-3 md:hidden" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
