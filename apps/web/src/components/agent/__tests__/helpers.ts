import { MessageRole, type AgentMessage } from '@llamatrade/core/stores/agent';

type ToolCall = AgentMessage['toolCalls'][number];

export const tool = (over: Partial<ToolCall> & { name: string }): ToolCall =>
  ({
    id: over.name,
    argumentsJson: '',
    resultJson: '',
    durationMs: 0,
    success: true,
    ...over,
  }) as unknown as ToolCall;

export const message = (
  id: string,
  content: string,
  over: { user?: boolean; toolCalls?: ToolCall[]; artifacts?: string[] } = {}
): AgentMessage =>
  ({
    id,
    sessionId: 'c1',
    role: over.user ? MessageRole.USER : MessageRole.ASSISTANT,
    content,
    toolCalls: over.toolCalls ?? [],
    inlineArtifactIds: over.artifacts ?? [],
    thinking: '',
  }) as unknown as AgentMessage;
