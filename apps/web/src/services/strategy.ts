/**
 * Strategy service calls used by the strategy screens. Each call carries the tenant context
 * from the auth store, as the shared stores do.
 */

import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import {
  AssetClass,
  StrategyStatus,
  TemplateCategory,
  TemplateDifficulty,
} from '@llamatrade/core/proto/strategy_pb';

import { getTenantContext } from '../store/auth';

import { strategyClient } from './grpc-client';

const context = () => getTenantContext();

export async function listStrategies(
  params: { page?: number; pageSize?: number; statuses?: StrategyStatus[]; search?: string } = {}
) {
  return strategyClient.listStrategies({
    context: context(),
    pagination:
      params.page || params.pageSize
        ? { page: params.page ?? 1, pageSize: params.pageSize ?? 20 }
        : undefined,
    statuses: params.statuses,
    search: params.search,
  });
}

export async function getStrategy(strategyId: string, version?: number) {
  return strategyClient.getStrategy({ context: context(), strategyId, version });
}

export async function updateStrategy(
  strategyId: string,
  data: { name?: string; description?: string; dslCode?: string; changeSummary?: string }
) {
  return strategyClient.updateStrategy({ context: context(), strategyId, ...data });
}

/** The engine's checks on a saved version (ValidateStrategy). */
export async function validateStrategy(strategyId: string, version?: number) {
  return strategyClient.validateStrategy({ context: context(), strategyId, version });
}

/** The same checks as ValidateStrategy, run on unsaved text. */
export async function checkDraft(dslCode: string) {
  const res = await strategyClient.compileStrategy({
    context: context(),
    dslCode,
    validateOnly: true,
  });
  return res.result;
}

export async function listStrategyVersions(strategyId: string, pageSize = 50) {
  return strategyClient.listStrategyVersions({
    context: context(),
    strategyId,
    pagination: { page: 1, pageSize },
  });
}

/** Executions of one strategy that are running now, newest first. */
export async function listRunningExecutions(strategyId: string) {
  const res = await strategyClient.listExecutions({
    context: context(),
    strategyId,
    statuses: [ExecutionStatus.RUNNING, ExecutionStatus.PAUSED],
    pagination: { page: 1, pageSize: 10 },
  });
  return res.executions;
}

export async function listTemplates(
  params: {
    category?: TemplateCategory;
    assetClass?: AssetClass;
    difficulty?: TemplateDifficulty;
  } = {}
) {
  return strategyClient.listTemplates({ ...params });
}

export async function getTemplate(templateId: string) {
  return strategyClient.getTemplate({ templateId });
}
