/**
 * Agent Chat component.
 *
 * Centered dialog with:
 * - Message list with streaming support
 * - Tool call indicators
 * - Pending artifact cards
 * - Suggested prompts
 * - Auto-context injection (strategy DSL)
 */

import {
  AlertCircle,
  BarChart3,
  CloudOff,
  LineChart,
  Search,
  Sparkles,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react';
import { useEffect, useMemo, useRef } from 'react';

import { useAgentStore } from '../../store/agent';

import { ChatInput } from './ChatInput';
import { ChatMessage } from './ChatMessage';
import { PendingArtifactCard } from './PendingArtifactCard';
import { StreamingIndicator } from './StreamingIndicator';
import { ToolCallIndicator } from './ToolCallIndicator';

interface AgentChatProps {
  /** Optional page context for suggested prompts */
  page?: string;
  /** Strategy DSL code (auto-included in context) */
  strategyDSL?: string;
  /** Strategy name */
  strategyName?: string;
  /** Callback when chat is closed */
  onClose?: () => void;
}

export function AgentChat({
  page,
  strategyDSL,
  strategyName,
  onClose,
}: AgentChatProps) {
  const {
    messages,
    pendingArtifacts,
    isStreaming,
    streamingContent,
    currentToolCall,
    suggestedPrompts,
    error,
    loading,
    serviceUnavailable,
    sendMessage,
    dismissArtifact,
    getSuggestedPrompts,
    clearError,
  } = useAgentStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Build UI context (memoized to avoid re-renders)
  const uiContext = useMemo(
    () => ({ page }),
    [page]
  );

  // Build artifact map for inline rendering in messages
  const artifactMap = useMemo(() => {
    const map = new Map<string, (typeof pendingArtifacts)[0]>();
    for (const artifact of pendingArtifacts) {
      map.set(artifact.id, artifact);
    }
    return map;
  }, [pendingArtifacts]);

  // Load suggested prompts on mount or context change
  useEffect(() => {
    if (page) {
      getSuggestedPrompts(uiContext);
    }
  }, [page, getSuggestedPrompts, uiContext]);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, streamingContent]);

  const handleSendMessage = (content: string) => {
    // Include strategy DSL in every message for context
    sendMessage(content, strategyDSL, strategyName, page);
  };

  const handleSuggestedPrompt = (prompt: string) => {
    sendMessage(prompt, strategyDSL, strategyName, page);
  };

  // Uncommitted artifacts only
  const activeArtifacts = pendingArtifacts.filter((a) => !a.isCommitted);

  // Show context indicator when DSL is available
  const hasStrategyContext = Boolean(strategyDSL);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop - click to close */}
      <div
        className="absolute inset-0 bg-black/20 dark:bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      {/* Dialog */}
      <div className="relative w-full max-w-3xl h-[calc(100vh-2rem)] bg-white dark:bg-gray-900 rounded-2xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <Sparkles className="w-5 h-5 text-blue-500" />
            <h2 className="font-semibold bg-gradient-to-r from-blue-600 via-cyan-600 to-emerald-600 bg-clip-text text-transparent">
              LlamaTrade Copilot
            </h2>
            {hasStrategyContext && (
              <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">
                Strategy context active
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {/* Close button */}
            {onClose && (
              <button
                onClick={onClose}
                className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                title="Close"
              >
                <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
              </button>
            )}
          </div>
        </div>

        {/* Main content */}
        <div className="flex flex-1 overflow-hidden">
          {/* Chat area */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Messages */}
            <div className={`flex-1 overflow-y-auto p-4 space-y-4 bg-dotted-grid ${messages.length === 0 ? 'flex items-center justify-center' : ''}`}>
              {/* Service unavailable message */}
              {serviceUnavailable && messages.length === 0 && (
                <div className="text-center">
                  <CloudOff className="w-12 h-12 text-gray-400 mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100 mb-2">
                    Copilot Unavailable
                  </h3>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4 max-w-md mx-auto">
                    The AI agent service is not running. Start the agent service to use Copilot.
                  </p>
                  <code className="text-xs bg-gray-100 dark:bg-gray-800 px-3 py-2 rounded-lg text-gray-700 dark:text-gray-300 font-mono">
                    cd services/agent && uv run uvicorn src.main:app --port 8890
                  </code>
                </div>
              )}

              {/* Welcome message if no messages and service is available */}
              {messages.length === 0 && !isStreaming && !serviceUnavailable && (
                <div className="flex flex-col items-center py-6">
                  {/* Hero section */}
                  <div className="text-center mb-6">
                    <div className="relative inline-block mb-4">
                      <div
                        className="w-16 h-16 rounded-2xl flex items-center justify-center shadow-lg"
                        style={{
                          background: 'linear-gradient(135deg, #2563EB 0%, #0891B2 50%, #059669 100%)',
                        }}
                      >
                        <Sparkles className="w-8 h-8 text-white" />
                      </div>
                      <div className="absolute -bottom-1 -right-1 w-5 h-5 bg-green-500 rounded-full border-2 border-white dark:border-gray-900" />
                    </div>
                    <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
                      LlamaTrade Copilot
                    </h3>
                    <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
                      Your AI trading assistant. Build strategies, analyze portfolios, and optimize performance.
                    </p>
                    {hasStrategyContext && (
                      <p className="text-sm text-blue-600 dark:text-blue-400 mt-2">
                        I can see your current strategy and help you improve it.
                      </p>
                    )}
                  </div>

                  {/* Capability showcase cards */}
                  <div className="grid grid-cols-2 gap-3 w-full mb-6 px-4">
                    <CapabilityCard
                      icon={<LineChart className="w-5 h-5" />}
                      title="Generate Strategies"
                      description="Describe your goals and get a complete DSL strategy"
                      example="Create a defensive portfolio that shifts to bonds in downtrends"
                      onClick={() => handleSuggestedPrompt('Create a defensive portfolio that shifts to bonds when the market is bearish')}
                      disabled={loading}
                    />
                    <CapabilityCard
                      icon={<TrendingUp className="w-5 h-5" />}
                      title="Optimize Performance"
                      description="Analyze backtest results and improve your strategies"
                      example="How can I improve my strategy's Sharpe ratio?"
                      onClick={() => handleSuggestedPrompt(hasStrategyContext ? 'How can I improve this strategy?' : 'How can I improve my strategy performance and reduce drawdowns?')}
                      disabled={loading}
                    />
                    <CapabilityCard
                      icon={<BarChart3 className="w-5 h-5" />}
                      title="Portfolio Analysis"
                      description="Get insights on your current holdings and allocation"
                      example="Analyze my portfolio risk exposure"
                      onClick={() => handleSuggestedPrompt('Analyze my current portfolio and suggest improvements')}
                      disabled={loading}
                    />
                    <CapabilityCard
                      icon={<Search className="w-5 h-5" />}
                      title="Research Assets"
                      description="Explore indicators, market data, and asset info"
                      example="What's the current RSI for tech stocks?"
                      onClick={() => handleSuggestedPrompt('Show me technical indicators for QQQ and SPY')}
                      disabled={loading}
                    />
                  </div>

                  {/* Quick start prompts */}
                  <div className="w-full px-4">
                    <p className="text-xs text-gray-500 dark:text-gray-400 text-center mb-3 uppercase tracking-wide font-medium">
                      Quick start
                    </p>
                    <div className="flex flex-wrap justify-center gap-2">
                      {suggestedPrompts.length > 0 ? (
                        suggestedPrompts.slice(0, 4).map((prompt, index) => (
                          <button
                            key={index}
                            onClick={() => handleSuggestedPrompt(prompt)}
                            disabled={loading}
                            className="px-3 py-1.5 text-sm rounded-full border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:border-blue-400 dark:hover:border-blue-600 hover:text-blue-600 dark:hover:text-blue-400 transition-all shadow-sm"
                          >
                            {prompt}
                          </button>
                        ))
                      ) : (
                        <>
                          <QuickPromptButton
                            label="60/40 Portfolio"
                            onClick={() => handleSuggestedPrompt('Create a simple 60/40 portfolio')}
                            disabled={loading}
                          />
                          <QuickPromptButton
                            label="Momentum Strategy"
                            onClick={() => handleSuggestedPrompt('Build a momentum-based sector rotation strategy')}
                            disabled={loading}
                          />
                          {hasStrategyContext ? (
                            <QuickPromptButton
                              label="Improve Strategy"
                              onClick={() => handleSuggestedPrompt('How can I improve this strategy?')}
                              disabled={loading}
                            />
                          ) : (
                            <QuickPromptButton
                              label="View Templates"
                              onClick={() => handleSuggestedPrompt('Show me available strategy templates')}
                              disabled={loading}
                            />
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* Message list */}
              {messages.map((message) => (
                <ChatMessage key={message.id} message={message} artifacts={artifactMap} />
              ))}

              {/* Streaming indicator */}
              {isStreaming && (
                <StreamingIndicator content={streamingContent} />
              )}

              {/* Tool call indicator */}
              {currentToolCall && (
                <div className="pl-11">
                  <ToolCallIndicator
                    toolName={currentToolCall.name}
                    status={currentToolCall.status}
                    resultPreview={currentToolCall.resultPreview}
                  />
                </div>
              )}


              {/* Pending artifacts */}
              {activeArtifacts.length > 0 && (
                <div className="space-y-2">
                  {activeArtifacts.map((artifact) => (
                    <PendingArtifactCard
                      key={artifact.id}
                      artifact={artifact}
                      onDismiss={dismissArtifact}
                    />
                  ))}
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Error display - fixed above input */}
            {error && !serviceUnavailable && (
              <div className="mx-4 mb-2 flex items-start gap-2 p-3 rounded-lg bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-400">
                <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <p className="text-sm">{error}</p>
                  <button
                    onClick={clearError}
                    className="text-xs underline mt-1 hover:no-underline"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            {/* Input */}
            <div className="px-4 pb-4">
              <div>
                <ChatInput
                  onSend={handleSendMessage}
                  disabled={isStreaming || loading || serviceUnavailable}
                  placeholder={
                    serviceUnavailable
                      ? 'Copilot service unavailable...'
                      : hasStrategyContext
                        ? 'Ask about your strategy...'
                        : 'Ask Copilot anything...'
                  }
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Capability showcase card for the welcome screen */
interface CapabilityCardProps {
  icon: React.ReactNode;
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
      className="group text-left p-4 rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800/50 hover:border-blue-400 dark:hover:border-blue-600 hover:shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <div className="flex items-start gap-3">
        <div className="p-2 rounded-lg bg-gradient-to-br from-blue-500/10 to-cyan-500/10 text-blue-600 dark:text-blue-400 group-hover:from-blue-500/20 group-hover:to-cyan-500/20 transition-colors">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-0.5">
            {title}
          </h4>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
            {description}
          </p>
          <p className="text-xs text-blue-600 dark:text-blue-400 italic truncate">
            &ldquo;{example}&rdquo;
          </p>
        </div>
        <Zap className="w-4 h-4 text-gray-300 dark:text-gray-600 group-hover:text-blue-400 transition-colors flex-shrink-0" />
      </div>
    </button>
  );
}

/** Quick prompt button */
function QuickPromptButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="px-3 py-1.5 text-sm rounded-full border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:border-blue-400 dark:hover:border-blue-600 hover:text-blue-600 dark:hover:text-blue-400 transition-all shadow-sm disabled:opacity-50"
    >
      {label}
    </button>
  );
}
