import { formatDSL, parsePreview } from '@llamatrade/core/agent/artifact';
import { strategyStructure } from '@llamatrade/core/agent/structure';
import { ArtifactType, PendingArtifact, useAgentStore } from '@llamatrade/core/stores/agent';
import { Check, Code2, FlaskConical, PenLine } from 'lucide-react';
import { lazy, Suspense, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Pill, Skeleton } from '../ui';

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

  return (
    <section
      aria-label={`${isStrategy ? 'Strategy draft' : 'Draft'}: ${name}`}
      className="min-w-0 overflow-hidden rounded-panel border border-line-strong bg-panel"
    >
      <div className="flex items-center justify-between gap-2.5 border-b border-line px-3.5 py-[11px]">
        <span className="flex min-w-0 items-center gap-2.5">
          <span className="kicker flex-none">{isStrategy ? 'Strategy draft' : 'Draft'}</span>
          <b className="truncate font-semibold">{name}</b>
        </span>
        {saved ? (
          <Pill tone="accent">
            <Check className="h-3 w-3" />
            Saved
          </Pill>
        ) : (
          <Pill>Not saved</Pill>
        )}
      </div>

      <div className="grid gap-3 px-3.5 py-3">
        {(meta || structure) && (
          <div className="flex flex-wrap justify-between gap-x-3 gap-y-1 text-[12.5px] text-fg-3">
            <span>{meta}</span>
            {structure && <span>The structure as written</span>}
          </div>
        )}
        {structure && structure.lines.length > 0 ? (
          <ol className="m-0 grid list-none gap-1.5 p-0 text-[13px]">
            {structure.lines.map((line, i) => (
              <li
                key={i}
                className={line.kind === 'funds' ? 'flex flex-wrap gap-1.5' : 'text-fg-2'}
                style={{ paddingLeft: line.depth * 16 }}
              >
                {line.kind === 'funds'
                  ? line.funds?.map((f) => (
                      <span
                        key={f.symbol}
                        className="rounded-[5px] border border-line px-1.5 py-px font-mono text-[12px] font-semibold text-fg"
                      >
                        {f.symbol}
                        {f.weight !== undefined && (
                          <span className="ml-1 font-normal text-fg-3">{f.weight}%</span>
                        )}
                      </span>
                    ))
                  : line.text}
              </li>
            ))}
          </ol>
        ) : (
          artifact.description && (
            <p className="m-0 text-[13px] text-fg-2">{artifact.description}</p>
          )
        )}
        {dsl && !structure && (
          <p className="m-0 text-[12.5px] text-fg-3">
            The structure couldn&apos;t be read from this code. Open the code to check it.
          </p>
        )}
        {showCode && dsl && (
          <Suspense fallback={<Skeleton className="h-24 w-full" />}>
            <DslCodeBlock code={dsl} className="rounded-[8px] border border-line" />
          </Suspense>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-sunk px-3.5 py-2.5">
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => navigate(`/strategies/builder?artifact=${artifact.id}`)}
          disabled={!dsl}
        >
          <PenLine className="h-3.5 w-3.5" />
          Open in the builder
        </button>
        <button
          type="button"
          className="btn btn-secondary"
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
        <button
          type="button"
          className="btn btn-secondary"
          onClick={backtest}
          disabled={!dsl || saving}
        >
          <FlaskConical className="h-3.5 w-3.5" />
          Backtest
        </button>
        {dsl && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() => setShowCode(!showCode)}
            aria-expanded={showCode}
          >
            <Code2 className="h-3.5 w-3.5" />
            {showCode ? 'Hide code' : 'Show code'}
          </button>
        )}
      </div>
      {failed && (
        <p role="alert" className="m-0 border-t border-line px-3.5 py-2 text-[12.5px] text-risk">
          The draft couldn&apos;t be saved. Your conversation is unaffected; please try again.
        </p>
      )}
    </section>
  );
}
