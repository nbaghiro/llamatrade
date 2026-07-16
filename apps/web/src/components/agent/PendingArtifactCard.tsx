/** Inline strategy artifact card: dark-terminal DSL + open/backtest/save actions. */

import { AlertTriangle, Check, FlaskConical, LayoutGrid, Loader2, Play, Sparkles } from 'lucide-react';
import { lazy, Suspense, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ArtifactType, PendingArtifact, useAgentStore } from '../../store/agent';

// Lazy so the shared viewer stays in one chunk (the drawer lazy-loads it too).
const DslCodeBlock = lazy(() => import('../strategies/DslCodeBlock'));

interface StrategyPreview {
  name?: string;
  description?: string;
  dsl_code?: string;
  symbols?: string[];
  timeframe?: string;
}

interface PendingArtifactCardProps {
  artifact: PendingArtifact;
}

/**
 * Pretty-print DSL from scratch, since the agent stores the LLM's raw (often
 * inconsistently indented) text. Each nested list starts on its own line at its
 * paren depth; the list head and its inline atoms/`:params` stay on that line.
 * Depth tracks every paren (open + close), so indentation can't drift.
 */
function formatDSL(code: string): string {
  const tokens = code.match(/"(?:[^"\\]|\\.)*"|;[^\n]*|[()]|[^\s()]+/g);
  if (!tokens) return code.trim();

  let out = '';
  let depth = 0;
  let prevWasOpen = false;

  for (const tok of tokens) {
    if (tok === '(') {
      if (out !== '') out += '\n' + '  '.repeat(depth);
      out += '(';
      depth++;
      prevWasOpen = true;
    } else if (tok === ')') {
      depth = Math.max(0, depth - 1);
      out += ')';
      prevWasOpen = false;
    } else {
      out += prevWasOpen ? tok : ` ${tok}`;
      prevWasOpen = false;
    }
  }
  return out.trim();
}

/** Build the "REBALANCE MONTHLY · BENCHMARK SPY · N ASSETS" meta line from real data. */
function buildMeta(dsl: string, preview: StrategyPreview | null): string {
  const parts: string[] = [];
  const rebalance = dsl.match(/:rebalance\s+([A-Za-z-]+)/)?.[1];
  const benchmark = dsl.match(/:benchmark\s+([A-Za-z0-9]+)/)?.[1];
  if (rebalance) parts.push(`rebalance ${rebalance}`);
  if (benchmark) parts.push(`benchmark ${benchmark}`);
  const assetCount = (dsl.match(/\(asset\b/g) || []).length || preview?.symbols?.length || 0;
  if (assetCount > 0) parts.push(`${assetCount} assets`);
  if (parts.length === 0 && preview?.timeframe) parts.push(preview.timeframe);
  return parts.join(' · ');
}

export function PendingArtifactCard({ artifact }: PendingArtifactCardProps) {
  const navigate = useNavigate();
  const commitArtifact = useAgentStore((s) => s.commitArtifact);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  const preview = useMemo<StrategyPreview | null>(() => {
    try {
      return JSON.parse(artifact.previewJson) as StrategyPreview;
    } catch {
      return null;
    }
  }, [artifact.previewJson]);

  const formattedDSL = useMemo(() => (preview?.dsl_code ? formatDSL(preview.dsl_code) : ''), [preview?.dsl_code]);
  const meta = useMemo(() => buildMeta(formattedDSL, preview), [formattedDSL, preview]);

  const isStrategy = artifact.artifactType === ArtifactType.STRATEGY;
  const isSaved = artifact.isCommitted || saved;

  const handleOpenInBuilder = () => {
    if (!preview?.dsl_code) return;
    navigate(`/strategies/builder?artifact=${artifact.id}`);
  };

  const handleBacktest = () => {
    if (artifact.committedResourceId) {
      navigate(`/backtest?strategy=${artifact.committedResourceId}`);
    } else {
      navigate('/backtest');
    }
  };

  // Commit the draft into a real strategy server-side (single source of truth).
  const handleSave = async () => {
    if (isSaved || saving) return;
    setSaving(true);
    setFailed(false);
    const id = await commitArtifact(artifact.id);
    setSaving(false);
    if (id) setSaved(true);
    else setFailed(true);
  };

  return (
    <div className="w-full min-w-0 max-w-full border-2 border-ink bg-paper shadow-[4px_4px_0_rgb(var(--lt-ink))]">
      {/* Header */}
      <div className="flex items-center gap-2.5 border-b-2 border-ink bg-bone px-3.5 py-2.5">
        <span className="flex items-center gap-1.5 font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-ink/50">
          <Sparkles className="h-3 w-3 text-orange-500" />
          {isStrategy ? 'Strategy' : 'Artifact'}
        </span>
        <span className="text-sm font-black tracking-tight text-ink">{artifact.name || 'Strategy'}</span>
        <span
          className={`ml-auto border-2 border-ink px-2 py-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.08em] ${
            isSaved ? 'bg-green-600 text-bone' : 'bg-orange-500 text-ink'
          }`}
        >
          {isSaved ? 'Saved' : 'Draft'}
        </span>
      </div>

      {/* Meta line */}
      {meta && (
        <div className="px-3.5 pt-2.5 font-mono text-[10.5px] uppercase tracking-[0.03em] text-ink/55">{meta}</div>
      )}

      {/* Dark-terminal DSL — shared read-only viewer (same highlighter as the builder/drawer) */}
      {formattedDSL ? (
        <Suspense fallback={<div className="mx-3.5 mb-3.5 mt-2.5 h-24 border-2 border-ink bg-ink" />}>
          <DslCodeBlock code={formattedDSL} className="mx-3.5 mb-3.5 mt-2.5 border-2 border-ink" />
        </Suspense>
      ) : (
        artifact.description && <p className="px-3.5 py-3 text-sm text-ink/70">{artifact.description}</p>
      )}

      {/* Actions */}
      <div className="flex flex-wrap gap-2.5 border-t-2 border-ink px-3.5 py-3">
        <button
          onClick={handleOpenInBuilder}
          disabled={!preview?.dsl_code}
          className="flex items-center gap-1.5 border-2 border-ink bg-orange-500 px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.04em] text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-all hover:bg-orange-600 disabled:opacity-40 disabled:shadow-none"
        >
          <LayoutGrid className="h-3.5 w-3.5" />
          Open in builder
        </button>
        <button
          onClick={handleBacktest}
          className="flex items-center gap-1.5 border-2 border-ink bg-paper px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.04em] text-ink shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-all hover:bg-bone"
        >
          <Play className="h-3.5 w-3.5" />
          Backtest
        </button>
        <button
          onClick={handleSave}
          disabled={isSaved || saving || !preview?.dsl_code}
          title={failed ? 'Saving failed — click to retry' : undefined}
          className={`flex items-center gap-1.5 border-2 px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.04em] shadow-[3px_3px_0_rgb(var(--lt-ink))] transition-all disabled:opacity-40 disabled:shadow-none ${
            failed && !saving && !isSaved
              ? 'border-red-600 bg-red-50 text-red-700 hover:bg-red-100'
              : 'border-ink bg-paper text-ink hover:bg-bone'
          }`}
        >
          {saving ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : isSaved ? (
            <Check className="h-3.5 w-3.5" />
          ) : failed ? (
            <AlertTriangle className="h-3.5 w-3.5" />
          ) : (
            <FlaskConical className="h-3.5 w-3.5" />
          )}
          {isSaved ? 'Saved' : saving ? 'Saving…' : failed ? 'Retry save' : 'Save'}
        </button>
      </div>
    </div>
  );
}
