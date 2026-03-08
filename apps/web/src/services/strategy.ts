/**
 * Strategy gRPC service
 *
 * This module wraps the strategyClient with convenience functions.
 * It uses the proto-generated types directly.
 */

import {
  StrategyStatus,
  type Strategy,
} from '../generated/proto/strategy_pb';

import { strategyClient } from './grpc-client';

// ============================================
// Strategy CRUD
// ============================================

export async function listStrategies(params: {
  page?: number;
  pageSize?: number;
  statuses?: StrategyStatus[];
  search?: string;
} = {}) {
  return strategyClient.listStrategies({
    pagination: params.page || params.pageSize
      ? { page: params.page ?? 1, pageSize: params.pageSize ?? 20 }
      : undefined,
    statuses: params.statuses,
    search: params.search,
  });
}

export async function getStrategy(strategyId: string) {
  return strategyClient.getStrategy({ strategyId });
}

export async function createStrategy(data: {
  name: string;
  description?: string;
  dslCode?: string;
  templateId?: string;
  templateParams?: Record<string, string>;
  symbols?: string[];
  timeframe?: string;
  parameters?: Record<string, string>;
}) {
  return strategyClient.createStrategy({
    name: data.name,
    description: data.description,
    dslCode: data.dslCode,
    templateId: data.templateId,
    templateParams: data.templateParams,
    symbols: data.symbols,
    timeframe: data.timeframe,
    parameters: data.parameters,
  });
}

export async function updateStrategy(
  strategyId: string,
  data: {
    name?: string;
    description?: string;
    dslCode?: string;
    symbols?: string[];
    timeframe?: string;
    parameters?: Record<string, string>;
    changeSummary?: string;
  }
) {
  return strategyClient.updateStrategy({
    strategyId,
    name: data.name,
    description: data.description,
    dslCode: data.dslCode,
    symbols: data.symbols,
    timeframe: data.timeframe,
    parameters: data.parameters,
    changeSummary: data.changeSummary,
  });
}

export async function deleteStrategy(strategyId: string) {
  return strategyClient.deleteStrategy({ strategyId });
}

export async function activateStrategy(strategyId: string) {
  return strategyClient.updateStrategyStatus({
    strategyId,
    status: StrategyStatus.ACTIVE,
  });
}

export async function pauseStrategy(strategyId: string) {
  return strategyClient.updateStrategyStatus({
    strategyId,
    status: StrategyStatus.PAUSED,
  });
}

export async function validateStrategy(strategyId: string, version?: number) {
  return strategyClient.validateStrategy({ strategyId, version });
}

export async function compileStrategy(dslCode: string, validateOnly = false) {
  return strategyClient.compileStrategy({ dslCode, validateOnly });
}

// ============================================
// Version Management
// ============================================

export async function listStrategyVersions(strategyId: string, pagination?: { page?: number; pageSize?: number }) {
  return strategyClient.listStrategyVersions({
    strategyId,
    pagination: pagination ? { page: pagination.page ?? 1, pageSize: pagination.pageSize ?? 20 } : undefined,
  });
}

// ============================================
// Template Operations
// ============================================

export async function listTemplates(params: {
  category?: string;
  assetClass?: string;
  difficulty?: string;
} = {}) {
  return strategyClient.listTemplates({
    category: params.category,
    assetClass: params.assetClass,
    difficulty: params.difficulty,
  });
}

export async function getTemplate(templateId: string) {
  return strategyClient.getTemplate({ templateId });
}

// ============================================
// Re-exports for convenience
// ============================================

export { StrategyStatus };
export type { Strategy };

// ============================================
// Convenience exports
// ============================================

export const strategyApi = {
  // Strategies
  list: listStrategies,
  get: getStrategy,
  create: createStrategy,
  update: updateStrategy,
  delete: deleteStrategy,
  activate: activateStrategy,
  pause: pauseStrategy,
  validate: validateStrategy,
  compile: compileStrategy,

  // Versions
  listVersions: listStrategyVersions,

  // Templates
  listTemplates,
  getTemplate,
};

export default strategyApi;
