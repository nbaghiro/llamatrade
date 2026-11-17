import { ArrowLeft } from 'lucide-react';
import { useEffect, useRef } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';

import { readLocalDraft } from '../../components/strategy-builder/draft/localDraft';
import { StrategyBuilder } from '../../components/strategy-builder/StrategyBuilder';
import { PanelError, Skeleton, SkeletonRows } from '../../components/ui';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

/** The editor for a saved strategy (/strategies/:id/edit) or a new draft (/strategies/builder). */
export default function StrategyEditorPage() {
  const { id } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();
  const templateId = searchParams.get('template');
  const artifactId = searchParams.get('artifact');
  const mode = searchParams.get('mode');
  const loadedKey = useRef<string | null>(null);

  const {
    loadStrategy,
    loadTemplate,
    loadFromArtifact,
    createNew,
    loadFromDSL,
    setViewMode,
    strategyId,
    lastSavedAt,
    loading,
    error,
    tree,
    isDirty,
  } = useStrategyBuilderStore();

  const key = `${id ?? ''}|${templateId ?? ''}|${artifactId ?? ''}|${mode ?? ''}`;
  const load = () => {
    if (id) {
      // Saving a new draft moves to its own address; the store already holds it.
      if (strategyId === id && lastSavedAt && Date.now() - lastSavedAt < 10_000) return;
      loadStrategy(id).catch(() => undefined);
    } else if (artifactId) {
      loadFromArtifact(artifactId).catch(() => undefined);
    } else if (templateId) {
      loadTemplate(templateId).catch(() => undefined);
    } else {
      createNew();
      const local = readLocalDraft();
      if (local) loadFromDSL(local.dsl, local.name);
      if (mode === 'code') setViewMode('code');
    }
  };

  useEffect(() => {
    if (loadedKey.current === key) return;
    loadedKey.current = key;
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      if (!isDirty) return;
      e.preventDefault();
      e.returnValue = '';
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  if (loading) {
    return (
      <div className="page max-w-[1400px]" aria-busy="true">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="mt-3 h-6 w-64" />
        <Skeleton className="mt-2 h-3 w-80" />
        <div className="mt-6 grid gap-9 lg:grid-cols-[minmax(0,1fr)_330px]">
          <div className="panel">
            <SkeletonRows rows={7} cols={2} />
          </div>
          <Skeleton className="h-56 w-full" />
        </div>
      </div>
    );
  }

  if (error && Object.keys(tree.blocks).length <= 1) {
    return (
      <div className="page">
        <Link
          to="/strategies"
          className="inline-flex items-center gap-1 text-[12.5px] text-fg-3 hover:text-fg"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Strategies
        </Link>
        <div className="panel mt-4">
          <PanelError
            title={
              id
                ? 'This strategy couldn’t be opened'
                : templateId
                  ? 'This template couldn’t be opened'
                  : 'This draft couldn’t be opened'
            }
            cause={error}
            unaffected="Your saved strategies aren’t affected."
            onRetry={load}
          />
        </div>
      </div>
    );
  }

  return <StrategyBuilder />;
}
