import { formatDSL, parsePreview } from '@llamatrade/core/agent/artifact';
import { strategyStructure } from '@llamatrade/core/agent/structure';
import { ArtifactType, PendingArtifact, useAgentStore } from '@llamatrade/core/stores/agent';
import { Check, Code2, FlaskConical, PenLine } from 'lucide-react';
import { lazy, Suspense, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Skeleton } from '../ui';

const DslCodeBlock = lazy(() => import('../strategies/DslCodeBlock'));

interface PendingArtifactCardProps {
  artifact: PendingArtifact;
}

function structureMeta(rebalance: string, benchmark: string, funds: number): string {
  const parts: string[] = [];
  if (rebalance) parts.push(rebalance[0].toUpperCase() + rebalance.slice(1));
  if (benchmark) parts.push(`benchmark ${benchmark}`);
  if (funds) parts.push(`${funds} ${funds === 1 ? 'fund' : 'funds'}`);
  return parts.join(' · ');
}

/** A strategy draft from Copilot: its structure as written, its code folded, and its actions. */
export function PendingArtifactCard({ artifact }: PendingArtifactCardProps) {
  const navigate = useNavigate();
  const commitArtifact = useAgentStore((s) => s.commitArtifact);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);
  const [showCode, setShowCode] = useState(false);

  const preview = useMemo(() => parsePreview(artifact), [artifact]);
  const dsl = useMemo(() => (preview?.dsl_code ? formatDSL(preview.dsl_code) : ''), [preview]);
  const structure = useMemo(() => (dsl ? strategyStructure(dsl) : null), [dsl]);

  const isStrategy = artifact.artifactType === ArtifactType.STRATEGY;
  const saved = artifact.isCommitted;
  const name = artifact.name || structure?.name || 'Strategy';
  const meta = structure
    ? structureMeta(structure.rebalance, structure.benchmark, structure.symbols.length)
    : '';

  const save = async (): Promise<string | null> => {
    if (saved) return artifact.committedResourceId || null;
    if (saving) return null;
    setSaving(true);
    setFailed(false);
    const id = await commitArtifact(artifact.id);
    setSaving(false);
    if (!id) setFailed(true);
    return id;
  };

  const backtest = async () => {
    const id = await save();
    if (id) navigate(`/backtest?strategy=${id}`);
  };

  const pill =
    'inline-flex h-8 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-[13px] font-medium transition-opacity disabled:opacity-45';
  return (
    <section
      aria-label={`${isStrategy ? 'Strategy draft' : 'Draft'}: ${name}`}
      className="min-w-0 rounded-[12px] border border-line bg-panel px-5 pb-4 pt-[18px] shadow-[0_1px_2px_rgb(0_0_0/0.04)] motion-safe:animate-rise"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h4 className="m-0 min-w-0 truncate text-[16px] font-semibold tracking-[-0.01em]">
          {name}
        </h4>
        <span className="flex items-center gap-2 text-[12px] text-fg-3">
          {meta}
          {saved && (
            <span className="inline-flex items-center gap-1 text-fg-2">
              <Check className="h-3 w-3" />
              Saved
            </span>
          )}
        </span>
      </div>

      {structure && structure.lines.length > 0 ? (
        <ol className="m-0 mb-4 mt-3.5 grid list-none gap-0.5 p-0">
          {structure.lines.map((line, i) => {
            const n = structure.lines.slice(0, i + 1).filter((l) => l.kind !== 'funds').length;
            return (
              <li
                key={i}
                className="flex gap-3 py-1.5 text-[14px]"
                style={{ paddingLeft: line.depth * 18 }}
              >
                {line.kind === 'funds' ? (
                  <>
                    <span aria-hidden="true" className="w-[18px] flex-none" />
                    <span className="flex flex-wrap gap-1.5">
                      {line.funds?.map((f) => (
                        <span
                          key={f.symbol}
                          className="rounded-[5px] bg-sunk px-1.5 py-px font-mono text-[12px] font-medium text-fg"
                        >
                          {f.symbol}
                          {f.weight !== undefined && (
                            <span className="ml-1 font-normal text-fg-3">{f.weight}%</span>
                          )}
                        </span>
                      ))}
                    </span>
                  </>
                ) : (
                  <>
                    <span className="mt-0.5 grid h-[18px] w-[18px] flex-none place-items-center rounded-full border border-line-strong font-mono text-[10px] text-fg-3">
                      {n}
                    </span>
                    <span className="text-fg-2">{line.text}</span>
                  </>
                )}
              </li>
            );
          })}
        </ol>
      ) : (
        artifact.description && (
          <p className="m-0 mb-4 mt-3 text-[14px] text-fg-2">{artifact.description}</p>
        )
      )}
      {dsl && !structure && (
        <p className="m-0 mb-4 text-[12.5px] text-fg-3">
          The structure couldn&apos;t be read from this code. Open the code to check it.
        </p>
      )}
      {showCode && dsl && (
        <div className="mb-4">
          <Suspense fallback={<Skeleton className="h-24 w-full" />}>
            <DslCodeBlock code={dsl} className="rounded-[8px] border border-line" />
          </Suspense>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-1.5 border-t border-line pt-3.5">
        <button
          type="button"
          className={`${pill} bg-fg text-canvas hover:opacity-90`}
          onClick={() => navigate(`/strategies/builder?artifact=${artifact.id}`)}
          disabled={!dsl}
        >
          <PenLine className="h-3.5 w-3.5" />
          Open in the builder
        </button>
        <button
          type="button"
          className={`${pill} border border-line-strong text-fg hover:border-fg-3`}
          onClick={backtest}
          disabled={!dsl || saving}
        >
          <FlaskConical className="h-3.5 w-3.5" />
          Backtest
        </button>
        <button
          type="button"
          className={`${pill} px-2 text-fg-2 hover:text-fg`}
          onClick={save}
          disabled={saved || saving || !dsl}
        >
          {saving
            ? 'Saving…'
            : saved
              ? 'Saved as draft'
              : failed
                ? 'Try saving again'
                : 'Save as draft'}
        </button>
        {dsl && (
          <button
            type="button"
            className={`${pill} px-2 text-fg-2 hover:text-fg`}
            onClick={() => setShowCode(!showCode)}
            aria-expanded={showCode}
          >
            <Code2 className="h-3.5 w-3.5" />
            {showCode ? 'Hide code' : 'Show code'}
          </button>
        )}
      </div>
      {failed && (
        <p role="alert" className="m-0 mt-2 text-[12.5px] text-risk">
          The draft couldn&apos;t be saved. Your conversation is unaffected. Please try again.
        </p>
      )}
    </section>
  );
}
