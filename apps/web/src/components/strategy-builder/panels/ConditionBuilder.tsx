import { X } from 'lucide-react';
import { useState, useCallback } from 'react';

import type {
  ConditionExpression,
  ConditionOperand,
  IndicatorRef,
  PriceRef,
  NumberValue,
  IndicatorName,
  Comparator,
  PriceField,
} from '../../../types/strategy-builder';
import { INDICATORS, COMPARATORS, getIndicatorInfo } from '../../../types/strategy-builder';

interface ConditionBuilderProps {
  initialCondition?: ConditionExpression;
  defaultSymbol?: string;
  onSave: (condition: ConditionExpression) => void;
  onCancel: () => void;
}

type OperandType = 'price' | 'indicator' | 'number';

interface OperandState {
  type: OperandType;
  // For price
  priceField: PriceField;
  priceSymbol: string;
  // For indicator
  indicator: IndicatorName;
  indicatorPeriod: number;
  indicatorSymbol: string;
  // For number
  numberValue: number;
  isPercent: boolean;
}

function operandToState(operand: ConditionOperand | undefined, defaultSymbol: string): OperandState {
  if (!operand) {
    return {
      type: 'price',
      priceField: 'current',
      priceSymbol: defaultSymbol,
      indicator: 'sma',
      indicatorPeriod: 20,
      indicatorSymbol: defaultSymbol,
      numberValue: 0,
      isPercent: false,
    };
  }

  const base: OperandState = {
    type: operand.type === 'indicator' ? 'indicator' : operand.type === 'price' ? 'price' : 'number',
    priceField: 'current',
    priceSymbol: defaultSymbol,
    indicator: 'sma',
    indicatorPeriod: 20,
    indicatorSymbol: defaultSymbol,
    numberValue: 0,
    isPercent: false,
  };

  if (operand.type === 'price') {
    base.priceField = operand.field;
    base.priceSymbol = operand.symbol;
  } else if (operand.type === 'indicator') {
    base.indicator = operand.indicator;
    base.indicatorPeriod = operand.period || getIndicatorInfo(operand.indicator).defaultPeriod || 20;
    base.indicatorSymbol = operand.symbol;
  } else if (operand.type === 'number') {
    base.numberValue = operand.value;
    base.isPercent = operand.isPercent || false;
  }

  return base;
}

function stateToOperand(state: OperandState): ConditionOperand {
  if (state.type === 'price') {
    return {
      type: 'price',
      symbol: state.priceSymbol,
      field: state.priceField,
    } satisfies PriceRef;
  }

  if (state.type === 'indicator') {
    return {
      type: 'indicator',
      indicator: state.indicator,
      period: state.indicatorPeriod,
      symbol: state.indicatorSymbol,
    } satisfies IndicatorRef;
  }

  return {
    type: 'number',
    value: state.numberValue,
    isPercent: state.isPercent,
  } satisfies NumberValue;
}

export function ConditionBuilder({
  initialCondition,
  defaultSymbol = 'SPY',
  onSave,
  onCancel,
}: ConditionBuilderProps) {
  const [left, setLeft] = useState<OperandState>(
    operandToState(initialCondition?.left, defaultSymbol)
  );
  const [comparator, setComparator] = useState<Comparator>(
    initialCondition?.comparator || 'gt'
  );
  const [right, setRight] = useState<OperandState>(
    operandToState(initialCondition?.right, defaultSymbol)
  );

  const handleSave = useCallback(() => {
    const condition: ConditionExpression = {
      left: stateToOperand(left),
      comparator,
      right: stateToOperand(right),
    };
    onSave(condition);
  }, [left, comparator, right, onSave]);

  const updateLeft = (updates: Partial<OperandState>) => {
    setLeft((prev) => ({ ...prev, ...updates }));
  };

  const updateRight = (updates: Partial<OperandState>) => {
    setRight((prev) => ({ ...prev, ...updates }));
  };

  return (
    <div className="bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 w-[400px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {initialCondition ? 'Edit Condition' : 'Create Condition'}
        </h3>
        <button
          onClick={onCancel}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded"
        >
          <X className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Label */}
        <div className="text-xs font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-400">
          IF
        </div>

        {/* Left operand */}
        <OperandSelector
          label="When"
          state={left}
          onChange={updateLeft}
          showNumber={false}
        />

        {/* Comparator */}
        <div>
          <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
            Condition
          </label>
          <select
            value={comparator}
            onChange={(e) => setComparator(e.target.value as Comparator)}
            className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {COMPARATORS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.verboseLabel}
              </option>
            ))}
          </select>
        </div>

        {/* Right operand */}
        <OperandSelector label="Compare to" state={right} onChange={updateRight} showNumber />
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-3 py-1.5 text-sm bg-amber-500 hover:bg-amber-600 text-white rounded-md transition-colors"
        >
          {initialCondition ? 'Update' : 'Add Condition'}
        </button>
      </div>
    </div>
  );
}

interface OperandSelectorProps {
  label: string;
  state: OperandState;
  onChange: (updates: Partial<OperandState>) => void;
  showNumber?: boolean;
}

function OperandSelector({ label, state, onChange, showNumber = true }: OperandSelectorProps) {
  const indicatorInfo = state.type === 'indicator' ? getIndicatorInfo(state.indicator) : null;

  return (
    <div className="space-y-2">
      <label className="block text-xs font-medium text-gray-500 dark:text-gray-400">
        {label}
      </label>

      {/* Type selector */}
      <div className="flex gap-1">
        <button
          onClick={() => onChange({ type: 'price' })}
          className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
            state.type === 'price'
              ? 'bg-amber-500 text-white'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
          }`}
        >
          Price
        </button>
        <button
          onClick={() => onChange({ type: 'indicator' })}
          className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
            state.type === 'indicator'
              ? 'bg-amber-500 text-white'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
          }`}
        >
          Indicator
        </button>
        {showNumber && (
          <button
            onClick={() => onChange({ type: 'number' })}
            className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
              state.type === 'number'
                ? 'bg-amber-500 text-white'
                : 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700'
            }`}
          >
            Value
          </button>
        )}
      </div>

      {/* Type-specific inputs */}
      {state.type === 'price' && (
        <div className="flex gap-2">
          <select
            value={state.priceField}
            onChange={(e) => onChange({ priceField: e.target.value as PriceField })}
            className="flex-1 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            <option value="current">Current price</option>
            <option value="open">Open</option>
            <option value="high">High</option>
            <option value="low">Low</option>
            <option value="close">Close</option>
          </select>
          <input
            type="text"
            value={state.priceSymbol}
            onChange={(e) => onChange({ priceSymbol: e.target.value.toUpperCase() })}
            placeholder="Symbol"
            className="w-24 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
        </div>
      )}

      {state.type === 'indicator' && (
        <div className="space-y-2">
          <select
            value={state.indicator}
            onChange={(e) => {
              const ind = e.target.value as IndicatorName;
              const info = getIndicatorInfo(ind);
              onChange({
                indicator: ind,
                indicatorPeriod: info.defaultPeriod || 20,
              });
            }}
            className="w-full px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            {INDICATORS.map((ind) => (
              <option key={ind.name} value={ind.name}>
                {ind.label}
              </option>
            ))}
          </select>
          <div className="flex gap-2">
            {indicatorInfo?.hasPeriod && (
              <div className="flex items-center gap-1">
                <input
                  type="number"
                  value={state.indicatorPeriod}
                  onChange={(e) => onChange({ indicatorPeriod: parseInt(e.target.value) || 1 })}
                  min={1}
                  max={500}
                  className="w-20 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
                />
                <span className="text-xs text-gray-500">days</span>
              </div>
            )}
            <input
              type="text"
              value={state.indicatorSymbol}
              onChange={(e) => onChange({ indicatorSymbol: e.target.value.toUpperCase() })}
              placeholder="Symbol"
              className="w-24 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
            />
          </div>
        </div>
      )}

      {state.type === 'number' && (
        <div className="flex gap-2 items-center">
          <input
            type="number"
            value={state.numberValue}
            onChange={(e) => onChange({ numberValue: parseFloat(e.target.value) || 0 })}
            step="any"
            className="flex-1 px-3 py-2 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-amber-500"
          />
          <label className="flex items-center gap-1 text-sm text-gray-600 dark:text-gray-400">
            <input
              type="checkbox"
              checked={state.isPercent}
              onChange={(e) => onChange({ isPercent: e.target.checked })}
              className="rounded border-gray-300 dark:border-gray-600"
            />
            %
          </label>
        </div>
      )}
    </div>
  );
}
