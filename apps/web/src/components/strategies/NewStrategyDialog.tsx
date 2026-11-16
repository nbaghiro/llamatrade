import { Blocks, Code2 } from 'lucide-react';
import { Link } from 'react-router-dom';

import { Dialog, PanelError, Skeleton } from '../ui';

import { DescribeBox } from './DescribeBox';
import { TemplateCard } from './TemplateCard';
import { FEATURED_TEMPLATES, pickTemplates } from './templateModel';
import { useStartDraft } from './useStartDraft';
import { useTemplates } from './useTemplates';

const EXAMPLES = [
  '60/40 with a 10% gold sleeve',
  'RSI mean reversion on QQQ',
  'Dividend growth, low turnover',
  'Dual momentum, stocks or bonds',
];

const FEATURED = 6;

interface NewStrategyDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

/** Every way into a new strategy: describe it, pick a template, or start blank as an outline or as code. */
export default function NewStrategyDialog({ isOpen, onClose }: NewStrategyDialogProps) {
  const templates = useTemplates();
  const { fromTemplate, blank, describe } = useStartDraft();

  return (
    <Dialog
      open={isOpen}
      onClose={onClose}
      width={820}
      title={
        <span className="grid">
          New strategy
          <span className="text-[12px] font-normal text-fg-3">
            Describe it, or pick a template to start from.
          </span>
        </span>
      }
      footer={
        <div className="flex w-full flex-wrap items-center gap-2">
          <span className="mr-auto min-w-0 flex-1 basis-[240px] text-[12px] text-fg-3">
            Copilot writes the strategy language. Nothing runs until you save and backtest.
          </span>
          <button type="button" onClick={() => blank('tree')} className="btn btn-ghost">
            <Blocks className="h-4 w-4" />
            Blank, as blocks
          </button>
          <button type="button" onClick={() => blank('code')} className="btn btn-ghost">
            <Code2 className="h-4 w-4" />
            Blank, as code
          </button>
          <Link to="/strategies/templates" onClick={onClose} className="btn btn-secondary">
            Browse all templates
          </Link>
        </div>
      }
    >
      <DescribeBox
        autoFocus
        onSubmit={describe}
        placeholder="Momentum rotation across the 11 sector ETFs, monthly"
      />
      <div className="flex flex-wrap gap-1.5">
        {EXAMPLES.map((e) => (
          <button
            key={e}
            type="button"
            onClick={() => describe(e)}
            className="inline-flex h-[24px] items-center rounded-full px-2.5 text-[12px] text-fg-2 shadow-[inset_0_0_0_1px_rgb(var(--line-strong))] hover:text-fg"
          >
            {e}
          </button>
        ))}
      </div>
      <span className="label mt-1">Or start from a template</span>
      {templates.status === 'error' ? (
        <PanelError title="Templates couldn’t be loaded" onRetry={templates.retry} />
      ) : (
        <div className="grid gap-2.5 sm:grid-cols-3">
          {templates.status === 'loading'
            ? Array.from({ length: FEATURED }, (_, i) => (
                <Skeleton key={i} className="h-[86px] w-full" />
              ))
            : pickTemplates(templates.templates, FEATURED_TEMPLATES, FEATURED).map((t) => (
                <TemplateCard key={t.id} template={t} onUse={fromTemplate} variant="compact" />
              ))}
        </div>
      )}
    </Dialog>
  );
}
