// Strategies List Store
// Manages the list of user strategies for the StrategiesPage

import { create } from 'zustand';

import {
  StrategyStatus,
  type Strategy,
} from '../generated/proto/strategy_pb';
import { strategyClient } from '../services/grpc-client';

import { getTenantContext } from './auth';

// Map UI status strings to proto enum values
function parseStatusFilter(status: string): StrategyStatus[] | undefined {
  switch (status) {
    case 'draft':
      return [StrategyStatus.DRAFT];
    case 'active':
      return [StrategyStatus.ACTIVE];
    case 'paused':
      return [StrategyStatus.PAUSED];
    case 'archived':
      return [StrategyStatus.ARCHIVED];
    default:
      return undefined; // 'all' - no filter
  }
}

interface StrategiesState {
  // Data
  strategies: Strategy[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;

  // Filters
  statusFilter: string;
  typeFilter: string;
  searchQuery: string;

  // Async state
  loading: boolean;
  error: string | null;

  // Actions
  fetchStrategies: () => Promise<void>;
  setPage: (page: number) => void;
  setStatusFilter: (status: string) => void;
  setTypeFilter: (type: string) => void;
  setSearchQuery: (query: string) => void;
  deleteStrategy: (id: string) => Promise<void>;
  activateStrategy: (id: string) => Promise<void>;
  pauseStrategy: (id: string) => Promise<void>;
  cloneStrategy: (id: string, newName?: string) => Promise<string | null>;
  clearError: () => void;
}

export const useStrategiesStore = create<StrategiesState>((set, get) => ({
  // Initial state
  strategies: [],
  total: 0,
  page: 1,
  pageSize: 12,
  totalPages: 0,

  statusFilter: 'all',
  typeFilter: 'all',
  searchQuery: '',

  loading: false,
  error: null,

  // Fetch strategies with current filters
  fetchStrategies: async () => {
    // Note: typeFilter is kept for UI but not used for backend query (proto doesn't support it)
    const { page, pageSize, statusFilter, searchQuery } = get();

    set({ loading: true, error: null });

    // Get tenant context (will be undefined if not authenticated)
    const context = getTenantContext();
    if (!context) {
      set({
        error: 'Please log in to view your strategies',
        loading: false,
      });
      return;
    }

    try {
      const response = await strategyClient.listStrategies({
        context,
        pagination: { page, pageSize },
        statuses: parseStatusFilter(statusFilter),
        search: searchQuery || undefined,
      });

      const pagination = response.pagination;
      set({
        strategies: response.strategies,
        total: pagination?.totalItems ?? response.strategies.length,
        totalPages: pagination?.totalPages ?? 1,
        loading: false,
      });
    } catch (error) {
      // Check for authentication errors
      const errorMessage = error instanceof Error ? error.message : String(error);
      const isAuthError = errorMessage.includes('401') ||
                          errorMessage.includes('Unauthorized') ||
                          errorMessage.includes('unauthenticated');

      set({
        error: isAuthError
          ? 'Please log in to view your strategies'
          : (error instanceof Error ? error.message : 'Failed to fetch strategies'),
        loading: false,
      });
    }
  },

  setPage: (page) => {
    set({ page });
    get().fetchStrategies();
  },

  setStatusFilter: (status) => {
    set({ statusFilter: status, page: 1 });
    get().fetchStrategies();
  },

  setTypeFilter: (type) => {
    set({ typeFilter: type, page: 1 });
    get().fetchStrategies();
  },

  setSearchQuery: (query) => {
    set({ searchQuery: query });
    // Debounce would be nice here, but for simplicity just fetch
    get().fetchStrategies();
  },

  deleteStrategy: async (id) => {
    set({ loading: true, error: null });
    try {
      const context = getTenantContext();
      await strategyClient.deleteStrategy({ context, strategyId: id });
      // Remove from local state
      set((state) => ({
        strategies: state.strategies.filter((s) => s.id !== id),
        total: state.total - 1,
        loading: false,
      }));
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to delete strategy',
        loading: false,
      });
    }
  },

  activateStrategy: async (id) => {
    try {
      const context = getTenantContext();
      const response = await strategyClient.updateStrategyStatus({
        context,
        strategyId: id,
        status: StrategyStatus.ACTIVE,
      });
      const updated = response.strategy;
      if (updated) {
        set((state) => ({
          strategies: state.strategies.map((s) =>
            s.id === id ? { ...s, status: updated.status } : s
          ),
        }));
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to activate strategy',
      });
    }
  },

  pauseStrategy: async (id) => {
    try {
      const context = getTenantContext();
      const response = await strategyClient.updateStrategyStatus({
        context,
        strategyId: id,
        status: StrategyStatus.PAUSED,
      });
      const updated = response.strategy;
      if (updated) {
        set((state) => ({
          strategies: state.strategies.map((s) =>
            s.id === id ? { ...s, status: updated.status } : s
          ),
        }));
      }
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to pause strategy',
      });
    }
  },

  cloneStrategy: async (id, newName) => {
    try {
      const context = getTenantContext();
      // Clone by creating a new strategy based on the existing one
      const getResponse = await strategyClient.getStrategy({ context, strategyId: id });
      const original = getResponse.strategy;
      if (!original) {
        throw new Error('Strategy not found');
      }

      const createResponse = await strategyClient.createStrategy({
        context,
        name: newName ?? `${original.name} (Copy)`,
        description: original.description,
        dslCode: original.dslCode,
        templateId: original.templateId,
        templateParams: original.templateParams,
        symbols: original.symbols,
        timeframe: original.timeframe,
        parameters: original.parameters,
      });

      // Refresh list to include the clone
      get().fetchStrategies();
      return createResponse.strategy?.id ?? null;
    } catch (error) {
      set({
        error: error instanceof Error ? error.message : 'Failed to clone strategy',
      });
      return null;
    }
  },

  clearError: () => {
    set({ error: null });
  },
}));
