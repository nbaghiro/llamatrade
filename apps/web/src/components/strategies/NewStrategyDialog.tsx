/**
 * New Strategy — catalog + live preview.
 *
 * A single surface with three grounded paths that never compete:
 *  1. Copilot command bar (header) — describe a strategy; hands off to the
 *     seeded full-page Copilot.
 *  2. Template list (left) — filterable/searchable rows; selecting one updates…
 *  3. Preview panel (right) — the selected template's real composition
 *     (allocation, symbols, cadence, benchmark) + its DSL, derived from the
 *     template definition. No fabricated performance — a template has none until
 *     it's backtested, which is the next step after "Use this template".
 */

import { ArrowLeft, ArrowRight, Loader2, Maximize2, Plus, Search, Sparkles, X } from 'lucide-react';
import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { CopilotConversation } from '../../components/agent/CopilotConversation';
import {
  ALL_CATEGORIES,
  ALL_DIFFICULTIES,
  CATEGORY_LABELS,
  DIFFICULTY_LABELS,
  TemplateCategory,
  TemplateDifficulty,
  type StrategyTemplate,
} from '../../data/strategy-templates';
import { listTemplates } from '../../services/strategy';
import { useAgentStore } from '../../store/agent';
import { useStrategyBuilderStore } from '../../store/strategy-builder';

const DslCodeBlock = lazy(() => import('./DslCodeBlock'));

const EXAMPLE_PROMPTS: readonly string[] = [
  '60/40 with a 10% gold sleeve',
  'RSI mean-reversion on QQQ',
  'Dividend growth, low turnover',
  'Dual momentum, stocks vs. bonds',
];

const DIFFICULTY_BADGE: Record<TemplateDifficulty, string> = {
  [TemplateDifficulty.UNSPECIFIED]: 'bg-ink/10 text-ink',
  [TemplateDifficulty.BEGINNER]: 'bg-blue-500 text-bone',
  [TemplateDifficulty.INTERMEDIATE]: 'bg-orange-500 text-ink',
  [TemplateDifficulty.ADVANCED]: 'bg-red-500 text-bone',
};

/** Alternating fills for the allocation bar (ink / orange / muted grays). */
const ALLOC_FILLS = ['bg-ink', 'bg-orange-500', 'bg-ink/45', 'bg-ink/70', 'bg-orange-400', 'bg-ink/25'];

interface Composition {
  rebalance: string | null;
  benchmark: string | null;
  method: string | null;
  /** Top-level allocation groups (name + weight%), when they sum to ~100. */
  groups: { name: string; weight: number }[];
  symbols: string[];
}

/** Derive a human composition from a template's S-expression (display only). */
function parseComposition(sexpr: string): Composition {
  const rebalance = sexpr.match(/:rebalance\s+([a-zA-Z]+)/)?.[1] ?? null;
  const benchmark = sexpr.match(/:benchmark\s+([A-Z][A-Z0-9.]*)/)?.[1] ?? null;
  const method = sexpr.match(/:method\s+([a-zA-Z]+)/)?.[1] ?? null;

  const groups: { name: string; weight: number }[] = [];
  const groupRe = /\(group\s+"([^"]+)"\s+:weight\s+(\d+(?:\.\d+)?)/g;
  let g: RegExpExecArray | null;
  while ((g = groupRe.exec(sexpr)) !== null) {
    groups.push({ name: g[1], weight: parseFloat(g[2]) });
  }
  // Keep group allocation only when the top-level weights read as a 100% split;
  // nested/partial groups (sum ≠ 100) would mislead, so we drop to symbols then.
  const groupSum = groups.reduce((s, x) => s + x.weight, 0);
  const usableGroups = groups.length >= 2 && Math.abs(groupSum - 100) <= 5 ? groups : [];

  const symbols = Array.from(
    new Set(Array.from(sexpr.matchAll(/\(asset\s+([A-Z][A-Z0-9.]*)/g), (m) => m[1]))
  );

  return { rebalance, benchmark, method, groups: usableGroups, symbols };
}

interface MetaProps {
  k: string;
  v: string;
}
function Meta({ k, v }: MetaProps) {
  return (
    <div>
      <div className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-ink/45">{k}</div>
      <div className="mt-0.5 font-mono text-[12px] font-bold text-ink">{v}</div>
    </div>
  );
}

interface NewStrategyDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function NewStrategyDialog({ isOpen, onClose }: NewStrategyDialogProps) {
  const navigate = useNavigate();
  const { createNew } = useStrategyBuilderStore();
  const startNewChat = useAgentStore((s) => s.startNewChat);
  const sendMessage = useAgentStore((s) => s.sendMessage);

  const [chatMode, setChatMode] = useState(false);
  const [prompt, setPrompt] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<TemplateCategory | 'all'>('all');
  const [selectedDifficulty, setSelectedDifficulty] = useState<TemplateDifficulty | 'all'>('all');

  const [templates, setTemplates] = useState<StrategyTemplate[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;
    async function fetchTemplates() {
      try {
        setLoading(true);
        setError(null);
        const response = await listTemplates();
        setTemplates(
          response.templates.map((t) => ({
            id: t.id,
            name: t.name,
            description: t.description,
            category: t.category,
            asset_class: t.assetClass,
            config_sexpr: t.configSexpr,
            config_json: {},
            tags: [...t.tags],
            difficulty: t.difficulty,
          }))
        );
      } catch {
        setError('Failed to load templates. Please try again.');
      } finally {
        setLoading(false);
      }
    }
    void fetchTemplates();
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  // Reset to the template browser whenever the modal closes.
  useEffect(() => {
    if (!isOpen) setChatMode(false);
  }, [isOpen]);

  const filteredTemplates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return templates.filter((t) => {
      const matchesSearch =
        q === '' || t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q);
      const matchesCategory = selectedCategory === 'all' || t.category === selectedCategory;
      const matchesDifficulty = selectedDifficulty === 'all' || t.difficulty === selectedDifficulty;
      return matchesSearch && matchesCategory && matchesDifficulty;
    });
  }, [templates, searchQuery, selectedCategory, selectedDifficulty]);

  // Keep a valid selection: default to the first match, and re-anchor when the
  // current selection filters out — so the preview panel is never empty.
  useEffect(() => {
    if (filteredTemplates.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filteredTemplates.some((t) => t.id === selectedId)) {
      setSelectedId(filteredTemplates[0].id);
    }
  }, [filteredTemplates, selectedId]);

  const selected = useMemo(
    () => filteredTemplates.find((t) => t.id === selectedId) ?? null,
    [filteredTemplates, selectedId]
  );
  const composition = useMemo(
    () => (selected ? parseComposition(selected.config_sexpr) : null),
    [selected]
  );

  // AI generation now happens inside this modal: start a fresh conversation and
  // stream the reply in the embedded Copilot instead of navigating away.
  const enterChat = (message: string) => {
    startNewChat();
    setChatMode(true);
    void sendMessage(message, undefined, undefined, 'new-strategy');
  };

  const handleGenerate = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    enterChat(trimmed);
  };

  const handleUseTemplate = (template: StrategyTemplate) => {
    onClose();
    navigate(`/strategies/builder?template=${template.id}`);
  };

  const handleCustomizeWithAI = (template: StrategyTemplate) => {
    enterChat(`Customize the "${template.name}" strategy template for me. ${template.description}`);
  };

  // Expand the in-modal conversation to the full /copilot page — conversation
  // state is shared in the agent store, so it continues seamlessly.
  const handleExpandChat = () => {
    onClose();
    navigate('/copilot');
  };

  const handleStartBlank = () => {
    createNew();
    onClose();
    navigate('/strategies/builder');
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      <div
        className={`relative mx-4 flex w-full flex-col overflow-hidden border-2 border-ink bg-paper shadow-2xl ${
          chatMode ? 'h-[85vh] max-w-[900px]' : 'max-h-[90vh] max-w-[1180px]'
        }`}
      >
        {/* Header */}
        <div className="flex flex-shrink-0 items-center justify-between border-b-2 border-ink px-6 py-4">
          <div>
            <h2 className="font-display text-lg uppercase tracking-tight text-ink">New Strategy</h2>
            <p className="font-mono text-sm text-ink/50">
              {chatMode
                ? 'Copilot is drafting — refine it in the chat'
                : 'Describe it, or pick a template to preview'}
            </p>
          </div>
          <button onClick={onClose} className="p-2 transition-colors hover:bg-ink/5" title="Close">
            <X className="h-5 w-5 text-ink/60" />
          </button>
        </div>

        {chatMode ? (
          <>
            {/* AI-mode toolbar */}
            <div className="flex flex-none items-center justify-between border-b-2 border-ink bg-ink/[0.04] px-6 py-2">
              <button
                onClick={() => setChatMode(false)}
                className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-ink/60 transition-colors hover:text-ink"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Templates
              </button>
              <button
                onClick={handleExpandChat}
                title="Open in full Copilot page"
                className="flex items-center gap-1.5 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-ink/60 transition-colors hover:text-ink"
              >
                <Maximize2 className="h-3.5 w-3.5" />
                Expand
              </button>
            </div>
            <CopilotConversation
              variant="modal"
              page="new-strategy"
              fallbackPrompts={[...EXAMPLE_PROMPTS]}
              footerNote="Copilot writes real DSL · runs on your paper account"
              placeholder="Refine — e.g. 'make it monthly' or 'add a 10% gold sleeve'"
              emptyState={
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <div className="grid h-12 w-12 place-items-center border-2 border-ink bg-orange-500 shadow-[3px_3px_0_rgb(var(--lt-ink))]">
                    <Sparkles className="h-6 w-6 text-ink" />
                  </div>
                  <h3 className="mt-4 font-display text-lg uppercase tracking-tight text-ink">
                    Drafting your strategy
                  </h3>
                  <p className="mt-2 max-w-sm text-[13px] text-ink/60">
                    Copilot is turning your description into real DSL. Ask follow-ups to refine it.
                  </p>
                </div>
              }
            />
          </>
        ) : (
          <>
        {/* Copilot command bar */}
        <div className="flex-shrink-0 border-b-2 border-ink bg-ink/[0.04] px-6 py-3.5">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-blue-600" />
            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleGenerate(prompt);
                }
              }}
              placeholder='Describe a strategy — e.g. "momentum rotation across the 11 sector ETFs, monthly"'
              className="input flex-1 font-mono text-sm"
            />
            <button
              onClick={() => handleGenerate(prompt)}
              disabled={!prompt.trim()}
              className="btn btn-primary flex-shrink-0"
            >
              Generate
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {EXAMPLE_PROMPTS.map((example) => (
              <button
                key={example}
                onClick={() => handleGenerate(example)}
                className="border border-ink/20 px-2 py-1 font-mono text-[11px] text-ink/60 transition-colors hover:border-blue-600 hover:text-ink"
              >
                <span className="text-blue-600">↳</span> {example}
              </button>
            ))}
          </div>
        </div>

        {/* Body: facets · list · preview */}
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {/* Facet rail */}
          <aside className="hidden w-48 flex-shrink-0 space-y-5 overflow-y-auto border-r-2 border-ink bg-ink/[0.04] p-4 lg:block">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink/40" />
              <input
                type="text"
                placeholder="Search…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="input pl-9 text-sm"
              />
            </div>
            <div>
              <span className="mb-2 block font-mono text-[11px] font-bold uppercase tracking-wide text-ink/50">
                Category
              </span>
              <div className="flex flex-col gap-1.5">
                <FacetButton label="All" active={selectedCategory === 'all'} onClick={() => setSelectedCategory('all')} />
                {ALL_CATEGORIES.map((c) => (
                  <FacetButton
                    key={c}
                    label={CATEGORY_LABELS[c]}
                    active={selectedCategory === c}
                    onClick={() => setSelectedCategory(selectedCategory === c ? 'all' : c)}
                  />
                ))}
              </div>
            </div>
            <div>
              <span className="mb-2 block font-mono text-[11px] font-bold uppercase tracking-wide text-ink/50">
                Level
              </span>
              <div className="flex flex-col gap-1.5">
                {ALL_DIFFICULTIES.map((d) => (
                  <FacetButton
                    key={d}
                    label={DIFFICULTY_LABELS[d]}
                    active={selectedDifficulty === d}
                    activeClass={
                      d === TemplateDifficulty.BEGINNER
                        ? 'bg-blue-500 text-bone'
                        : d === TemplateDifficulty.INTERMEDIATE
                          ? 'bg-orange-500 text-ink'
                          : 'bg-red-500 text-bone'
                    }
                    onClick={() => setSelectedDifficulty(selectedDifficulty === d ? 'all' : d)}
                  />
                ))}
              </div>
            </div>
          </aside>

          {/* Template list */}
          <div className="flex w-full flex-shrink-0 flex-col border-r-2 border-ink md:w-[340px]">
            {loading ? (
              <div className="flex flex-1 items-center justify-center">
                <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
              </div>
            ) : error ? (
              <div className="p-6 text-center">
                <p className="text-sm text-red-600">{error}</p>
              </div>
            ) : filteredTemplates.length === 0 ? (
              <div className="p-6 text-center font-mono text-sm text-ink/50">
                No templates match your filters.
              </div>
            ) : (
              <div className="min-h-0 flex-1 overflow-y-auto">
                {filteredTemplates.map((t) => {
                  const active = t.id === selectedId;
                  const count = new Set(
                    Array.from(t.config_sexpr.matchAll(/\(asset\s+([A-Z][A-Z0-9.]*)/g), (m) => m[1])
                  ).size;
                  return (
                    <button
                      key={t.id}
                      onClick={() => setSelectedId(t.id)}
                      className={`flex w-full flex-col gap-1 border-b border-ink/10 px-4 py-3 text-left transition-colors ${
                        active
                          ? 'border-l-4 border-l-orange-500 bg-orange-500/[0.07]'
                          : 'hover:bg-ink/[0.03]'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`truncate font-display text-[15px] uppercase tracking-tight ${active ? 'text-orange-600' : 'text-ink'}`}
                        >
                          {t.name}
                        </span>
                        <span
                          className={`flex-shrink-0 border border-ink px-1.5 py-0.5 font-mono text-[8.5px] font-bold uppercase tracking-wide ${DIFFICULTY_BADGE[t.difficulty]}`}
                        >
                          {DIFFICULTY_LABELS[t.difficulty]}
                        </span>
                      </div>
                      <p className="line-clamp-1 text-xs text-ink/55">{t.description}</p>
                      <div className="flex items-center gap-2 font-mono text-[9.5px] uppercase tracking-wide text-ink/45">
                        <span>{CATEGORY_LABELS[t.category]}</span>
                        <span>·</span>
                        <span>{count} symbols</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Preview panel */}
          <div className="hidden min-w-0 flex-1 flex-col bg-paper md:flex">
            {selected && composition ? (
              <>
                <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-display text-2xl uppercase leading-none tracking-tight text-ink">
                      {selected.name}
                    </h3>
                    <div className="flex flex-shrink-0 gap-1.5">
                      <span
                        className={`border border-ink px-2 py-0.5 font-mono text-[9.5px] font-bold uppercase tracking-wide ${DIFFICULTY_BADGE[selected.difficulty]}`}
                      >
                        {DIFFICULTY_LABELS[selected.difficulty]}
                      </span>
                      <span className="border border-ink bg-transparent px-2 py-0.5 font-mono text-[9.5px] font-bold uppercase tracking-wide text-ink/60">
                        {CATEGORY_LABELS[selected.category]}
                      </span>
                    </div>
                  </div>
                  <p className="mt-2 max-w-prose text-[13.5px] leading-relaxed text-ink/70">
                    {selected.description}
                  </p>
                </div>

                {/* Meta row */}
                <div className="grid grid-cols-4 gap-3 border-2 border-ink bg-paper p-3">
                  <Meta k="Symbols" v={String(composition.symbols.length)} />
                  <Meta k="Rebalance" v={composition.rebalance ?? '—'} />
                  <Meta k="Benchmark" v={composition.benchmark ?? '—'} />
                  <Meta k="Weighting" v={composition.method ?? '—'} />
                </div>

                {/* Allocation (grouped) or symbol chips */}
                {composition.groups.length > 0 ? (
                  <div>
                    <div className="mb-2 font-mono text-[9.5px] font-bold uppercase tracking-[0.1em] text-ink/50">
                      Allocation
                    </div>
                    <div className="flex h-4 overflow-hidden border-2 border-ink" aria-hidden="true">
                      {composition.groups.map((grp, i) => (
                        <span
                          key={grp.name}
                          className={`block ${ALLOC_FILLS[i % ALLOC_FILLS.length]}`}
                          style={{ width: `${grp.weight}%` }}
                        />
                      ))}
                    </div>
                    <div className="mt-2 flex flex-col gap-1">
                      {composition.groups.map((grp, i) => (
                        <div key={grp.name} className="flex items-center justify-between text-[12px]">
                          <span className="flex items-center gap-2">
                            <span className={`h-2.5 w-2.5 border border-ink ${ALLOC_FILLS[i % ALLOC_FILLS.length]}`} />
                            <span className="font-mono text-ink">{grp.name}</span>
                          </span>
                          <span className="font-mono font-bold tabular-nums text-ink">{grp.weight}%</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : (
                  <div>
                    <div className="mb-2 font-mono text-[9.5px] font-bold uppercase tracking-[0.1em] text-ink/50">
                      Universe · {composition.symbols.length} symbols
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {composition.symbols.map((s) => (
                        <span
                          key={s}
                          className="border-2 border-ink bg-paper px-1.5 py-0.5 font-mono text-[11px] font-bold text-ink"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* DSL */}
                <div>
                  <div className="mb-2 font-mono text-[9.5px] font-bold uppercase tracking-[0.1em] text-ink/50">
                    Strategy DSL
                  </div>
                  <Suspense
                    fallback={
                      <div className="flex h-24 items-center justify-center border-2 border-ink bg-ink">
                        <Loader2 className="h-4 w-4 animate-spin text-bone/50" />
                      </div>
                    }
                  >
                    <DslCodeBlock code={selected.config_sexpr} className="border-2 border-ink" />
                  </Suspense>
                </div>

                {/* Tags */}
                {selected.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {selected.tags.map((tag) => (
                      <span
                        key={tag}
                        className="border border-ink/20 bg-ink/5 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-ink/60"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}

                </div>

                {/* Pinned action bar — primary CTA always visible. */}
                <div className="flex flex-none flex-col gap-2.5 border-t-2 border-ink bg-ink/[0.04] px-6 py-4">
                  <p className="font-mono text-[11px] text-ink/50">
                    No track record yet — <span className="font-bold text-ink">backtest it</span> after
                    creating to see real performance, then deploy.
                  </p>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleUseTemplate(selected)}
                      className="btn btn-primary flex-1 justify-center"
                    >
                      Use this template
                      <ArrowRight className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => handleCustomizeWithAI(selected)}
                      title="Customize with Copilot"
                      className="btn btn-ghost"
                    >
                      <Sparkles className="h-4 w-4 text-blue-600" />
                      Customize
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex flex-1 items-center justify-center font-mono text-sm text-ink/40">
                Select a template to preview
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-shrink-0 items-center justify-between border-t-2 border-ink bg-ink/[0.04] px-6 py-3">
          <span className="font-mono text-[11px] uppercase tracking-wide text-ink/60">
            {loading ? (
              <span className="text-ink/40">Loading…</span>
            ) : (
              <>
                <span className="font-bold text-ink">{filteredTemplates.length}</span> of{' '}
                {templates.length} templates
              </>
            )}
          </span>
          <button onClick={handleStartBlank} className="btn btn-ghost">
            <Plus className="h-4 w-4" />
            Start from scratch
          </button>
        </div>
          </>
        )}
      </div>
    </div>
  );
}

interface FacetButtonProps {
  label: string;
  active: boolean;
  activeClass?: string;
  onClick: () => void;
}
function FacetButton({ label, active, activeClass = 'bg-orange-500 text-ink', onClick }: FacetButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full border-2 border-ink px-3 py-1.5 text-left font-mono text-xs font-bold uppercase tracking-wide transition-colors ${
        active ? activeClass : 'bg-paper text-ink/60 hover:bg-ink/5'
      }`}
    >
      {label}
    </button>
  );
}
