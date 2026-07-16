/**
 * Copilot empty state.
 *
 * The centered first-open experience: a greeting, a short subline, the composer
 * slotted in prominently beneath it, and prompt starters (capability cards +
 * quick-start chips) that send on click. Also renders the service-unavailable
 * notice when the agent backend is offline.
 *
 * This is pure presentation — all messaging behaviour lives in the store and is
 * threaded through the `onPrompt` callback and the `composer` slot.
 */

import {
  BarChart3,
  CloudOff,
  LineChart,
  Search,
  Sparkles,
  TrendingUp,
  Zap,
} from 'lucide-react';
import type { ReactNode } from 'react';

interface CopilotEmptyStateProps {
  /** Whether the current page exposes a strategy DSL for context. */
  hasStrategyContext: boolean;
  /** Disable starter buttons while a request is in flight. */
  loading: boolean;
  /** Context-aware prompts from the backend (falls back to defaults). */
  suggestedPrompts: string[];
  /** When true, show the offline notice instead of the greeting/starters. */
  serviceUnavailable: boolean;
  /** Fired when a starter is clicked. */
  onPrompt: (prompt: string) => void;
  /** The composer element, rendered between the greeting and the starters. */
  composer: ReactNode;
}

interface CapabilityCardData {
  icon: ReactNode;
  title: string;
  description: string;
  example: string;
  prompt: string;
}

function buildCapabilityCards(hasStrategyContext: boolean): CapabilityCardData[] {
  return [
    {
      icon: <LineChart className="h-5 w-5" />,
      title: 'Generate Strategies',
      description: 'Describe your goals and get a complete DSL strategy',
      example: 'Create a defensive portfolio that shifts to bonds in downtrends',
      prompt:
        'Create a defensive portfolio that shifts to bonds when the market is bearish',
    },
    {
      icon: <TrendingUp className="h-5 w-5" />,
      title: 'Optimize Performance',
      description: 'Analyze backtest results and improve your strategies',
      example: "How can I improve my strategy's Sharpe ratio?",
      prompt: hasStrategyContext
        ? 'How can I improve this strategy?'
        : 'How can I improve my strategy performance and reduce drawdowns?',
    },
    {
      icon: <BarChart3 className="h-5 w-5" />,
      title: 'Portfolio Analysis',
      description: 'Get insights on your current holdings and allocation',
      example: 'Analyze my portfolio risk exposure',
      prompt: 'Analyze my current portfolio and suggest improvements',
    },
    {
      icon: <Search className="h-5 w-5" />,
      title: 'Research Assets',
      description: 'Explore indicators, market data, and asset info',
      example: "What's the current RSI for tech stocks?",
      prompt: 'Show me technical indicators for QQQ and SPY',
    },
  ];
}

function buildFallbackPrompts(hasStrategyContext: boolean): { label: string; prompt: string }[] {
  return [
    { label: '60/40 Portfolio', prompt: 'Create a simple 60/40 portfolio' },
    {
      label: 'Momentum Strategy',
      prompt: 'Build a momentum-based sector rotation strategy',
    },
    hasStrategyContext
      ? { label: 'Improve Strategy', prompt: 'How can I improve this strategy?' }
      : { label: 'View Templates', prompt: 'Show me available strategy templates' },
  ];
}

export function CopilotEmptyState({
  hasStrategyContext,
  loading,
  suggestedPrompts,
  serviceUnavailable,
  onPrompt,
  composer,
}: CopilotEmptyStateProps) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="flex min-h-full flex-col items-center justify-center px-4 py-10">
        <div className="flex w-full max-w-2xl flex-col items-center">
          {serviceUnavailable ? (
            <ServiceUnavailableNotice />
          ) : (
            <CopilotGreeting hasStrategyContext={hasStrategyContext} />
          )}

          {/* Composer sits centered, directly under the greeting. */}
          <div className="mt-7 w-full">{composer}</div>

          {!serviceUnavailable && (
            <div className="mt-8 w-full space-y-6">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {buildCapabilityCards(hasStrategyContext).map((card) => (
                  <CapabilityCard
                    key={card.title}
                    icon={card.icon}
                    title={card.title}
                    description={card.description}
                    example={card.example}
                    onClick={() => onPrompt(card.prompt)}
                    disabled={loading}
                  />
                ))}
              </div>

              <QuickStartChips
                hasStrategyContext={hasStrategyContext}
                suggestedPrompts={suggestedPrompts}
                loading={loading}
                onPrompt={onPrompt}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Centered greeting: identity mark, title, and subline. */
function CopilotGreeting({ hasStrategyContext }: { hasStrategyContext: boolean }) {
  return (
    <div className="text-center">
      <div
        className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-2xl shadow-lg"
        style={{
          background: 'linear-gradient(135deg, #2563EB 0%, #0891B2 50%, #059669 100%)',
        }}
      >
        <Sparkles className="h-7 w-7 text-white" />
      </div>
      <h2 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
        How can I help you trade today?
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-gray-600 dark:text-gray-400">
        Your AI trading assistant. Build strategies, analyze portfolios, and optimize
        performance.
      </p>
      {hasStrategyContext && (
        <p className="mt-2 text-sm font-medium text-green-600 dark:text-green-400">
          I can see your current strategy and help you improve it.
        </p>
      )}
    </div>
  );
}

/** Offline notice shown when the agent backend is not reachable. */
function ServiceUnavailableNotice() {
  return (
    <div className="text-center">
      <CloudOff className="mx-auto mb-4 h-12 w-12 text-gray-400" />
      <h2 className="mb-2 text-lg font-medium text-gray-900 dark:text-gray-100">
        Copilot Unavailable
      </h2>
      <p className="mx-auto mb-4 max-w-md text-sm text-gray-600 dark:text-gray-400">
        The AI agent service is not running. Start the agent service to use Copilot.
      </p>
      <code className="rounded-lg bg-gray-100 px-3 py-2 font-mono text-xs text-gray-700 dark:bg-gray-800 dark:text-gray-300">
        cd services/agent &amp;&amp; uv run uvicorn src.main:app --port 8890
      </code>
    </div>
  );
}

/** Row of quick-start prompt chips (context-aware, backend-driven when available). */
function QuickStartChips({
  hasStrategyContext,
  suggestedPrompts,
  loading,
  onPrompt,
}: {
  hasStrategyContext: boolean;
  suggestedPrompts: string[];
  loading: boolean;
  onPrompt: (prompt: string) => void;
}) {
  const chips =
    suggestedPrompts.length > 0
      ? suggestedPrompts.slice(0, 4).map((prompt) => ({ label: prompt, prompt }))
      : buildFallbackPrompts(hasStrategyContext);

  return (
    <div>
      <p className="mb-3 text-center text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Quick start
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {chips.map((chip) => (
          <button
            key={chip.label}
            onClick={() => onPrompt(chip.prompt)}
            disabled={loading}
            className="rounded-full border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-700 shadow-sm transition-all hover:border-green-400 hover:text-green-600 disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300 dark:hover:border-green-600 dark:hover:text-green-400"
          >
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Capability showcase card. */
interface CapabilityCardProps {
  icon: ReactNode;
  title: string;
  description: string;
  example: string;
  onClick: () => void;
  disabled?: boolean;
}

function CapabilityCard({
  icon,
  title,
  description,
  example,
  onClick,
  disabled,
}: CapabilityCardProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="group rounded-xl border border-gray-200 bg-white p-4 text-left transition-all hover:border-green-400 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 dark:border-gray-700 dark:bg-gray-800/50 dark:hover:border-green-600"
    >
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-green-500/10 p-2 text-green-600 transition-colors group-hover:bg-green-500/20 dark:text-green-400">
          {icon}
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="mb-0.5 font-medium text-gray-900 dark:text-gray-100">{title}</h3>
          <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">{description}</p>
          <p className="truncate text-xs italic text-green-600 dark:text-green-400">
            &ldquo;{example}&rdquo;
          </p>
        </div>
        <Zap className="h-4 w-4 flex-shrink-0 text-gray-300 transition-colors group-hover:text-green-400 dark:text-gray-600" />
      </div>
    </button>
  );
}
