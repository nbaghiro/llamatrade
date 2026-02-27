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
} from '../../../types/strategy-builder';
import { INDICATORS, COMPARATORS, getIndicatorInfo } from '../../../types/strategy-builder';

interface ConditionEditorProps {
  condition: ConditionExpression;
  defaultSymbol: string;
  onSave: (condition: ConditionExpression) => void;
  onCancel: () => void;
}

type OperandType = 'price' | 'indicator' | 'number';

// Extract operand details for the form
function getOperandDetails(operand: ConditionOperand) {
  if (operand.type === 'price') {
    return {
      type: 'price' as OperandType,
      function: 'current_price',
      symbol: operand.symbol,
      period: 0,
      value: 0,
    };
  }
  if (operand.type === 'indicator') {
    return {
      type: 'indicator' as OperandType,
      function: operand.indicator,
      symbol: operand.symbol,
      period: operand.period || getIndicatorInfo(operand.indicator).defaultPeriod || 14,
      value: 0,
    };
  }
  return {
    type: 'number' as OperandType,
    function: 'value',
    symbol: '',
    period: 0,
    value: operand.value,
  };
}

// Build operand from form state
function buildOperand(
  type: OperandType,
  func: string,
  symbol: string,
  period: number,
  value: number
): ConditionOperand {
  if (type === 'price' || func === 'current_price') {
    return { type: 'price', symbol, field: 'current' } satisfies PriceRef;
  }
  if (type === 'number' || func === 'value') {
    return { type: 'number', value } satisfies NumberValue;
  }
  return {
    type: 'indicator',
    indicator: func as IndicatorName,
    symbol,
    period,
  } satisfies IndicatorRef;
}

export function ConditionEditor({ condition, defaultSymbol, onSave, onCancel }: ConditionEditorProps) {
  const leftDetails = getOperandDetails(condition.left);
  const rightDetails = getOperandDetails(condition.right);

  const [leftFunc, setLeftFunc] = useState(leftDetails.function);
  const [leftSymbol, setLeftSymbol] = useState(leftDetails.symbol || defaultSymbol);
  const [leftPeriod, setLeftPeriod] = useState(leftDetails.period);

  const [comparator, setComparator] = useState<Comparator>(condition.comparator);

  const [rightType, setRightType] = useState<'indicator' | 'value'>(
    rightDetails.type === 'number' ? 'value' : 'indicator'
  );
  const [rightFunc, setRightFunc] = useState(rightDetails.function);
  const [rightSymbol, setRightSymbol] = useState(rightDetails.symbol || defaultSymbol);
  const [rightPeriod, setRightPeriod] = useState(rightDetails.period);
  const [rightValue, setRightValue] = useState(rightDetails.value);

  const handleSave = useCallback(() => {
    const leftOperand = buildOperand(
      leftFunc === 'current_price' ? 'price' : 'indicator',
      leftFunc,
      leftSymbol,
      leftPeriod,
      0
    );

    const rightOperand = buildOperand(
      rightType === 'value' ? 'number' : rightFunc === 'current_price' ? 'price' : 'indicator',
      rightType === 'value' ? 'value' : rightFunc,
      rightSymbol,
      rightPeriod,
      rightValue
    );

    onSave({
      left: leftOperand,
      comparator,
      right: rightOperand,
    });
  }, [leftFunc, leftSymbol, leftPeriod, comparator, rightType, rightFunc, rightSymbol, rightPeriod, rightValue, onSave]);

  // Function options for dropdowns
  const functionOptions = [
    { value: 'current_price', label: 'current price' },
    ...INDICATORS.map((i) => ({
      value: i.name,
      label: `${i.defaultPeriod || ''}${i.defaultPeriod ? 'd ' : ''}${i.label.toLowerCase()}`,
    })),
  ];

  const leftInfo = leftFunc !== 'current_price' ? INDICATORS.find(i => i.name === leftFunc) : null;
  const rightInfo = rightFunc !== 'current_price' ? INDICATORS.find(i => i.name === rightFunc) : null;

  return (
    <div data-testid="condition-editor" className="bg-white dark:bg-gray-900 rounded-lg shadow-xl border border-gray-200 dark:border-gray-700 w-[420px]">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        <span className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Edit Conditional
        </span>
        <button
          onClick={onCancel}
          className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded transition-colors"
        >
          <X className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Left side: "if [function] of [asset]" */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-500 dark:text-gray-400 w-6">if</span>

          {/* Function dropdown */}
          <select
            value={leftFunc}
            onChange={(e) => {
              setLeftFunc(e.target.value);
              const info = INDICATORS.find(i => i.name === e.target.value);
              if (info?.defaultPeriod) setLeftPeriod(info.defaultPeriod);
            }}
            className="px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            {functionOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {/* Period input for indicators */}
          {leftInfo?.hasPeriod && (
            <div className="flex items-center gap-1">
              <input
                type="number"
                value={leftPeriod}
                onChange={(e) => setLeftPeriod(parseInt(e.target.value) || 1)}
                min={1}
                max={500}
                className="w-14 px-2 py-1.5 text-sm text-center bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="text-xs text-gray-400">d</span>
            </div>
          )}

          <span className="text-sm text-gray-500 dark:text-gray-400">of</span>

          {/* Asset input */}
          <div className="flex items-center gap-1 px-3 py-1.5 bg-emerald-500 text-white rounded-full">
            <span className="w-2 h-2 rounded-full bg-white/80" />
            <input
              type="text"
              value={leftSymbol}
              onChange={(e) => setLeftSymbol(e.target.value.toUpperCase())}
              className="w-12 bg-transparent text-sm font-medium focus:outline-none placeholder:text-white/60"
              placeholder="SPY"
            />
          </div>
        </div>

        {/* Comparator: "is [comparator]" */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400 w-6">is</span>

          <select
            value={comparator}
            onChange={(e) => setComparator(e.target.value as Comparator)}
            className="px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {COMPARATORS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.verboseLabel}
              </option>
            ))}
          </select>
        </div>

        {/* Right side: value or function */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-gray-500 dark:text-gray-400 w-6" />

          {/* Type toggle */}
          <div className="flex rounded-full border border-gray-300 dark:border-gray-600 overflow-hidden">
            <button
              onClick={() => setRightType('indicator')}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                rightType === 'indicator'
                  ? 'bg-blue-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              Function
            </button>
            <button
              onClick={() => setRightType('value')}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                rightType === 'value'
                  ? 'bg-blue-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
            >
              Value
            </button>
          </div>

          {rightType === 'value' ? (
            <input
              type="number"
              value={rightValue}
              onChange={(e) => setRightValue(parseFloat(e.target.value) || 0)}
              step="any"
              className="w-20 px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          ) : (
            <>
              {/* Function dropdown */}
              <select
                value={rightFunc}
                onChange={(e) => {
                  setRightFunc(e.target.value);
                  const info = INDICATORS.find(i => i.name === e.target.value);
                  if (info?.defaultPeriod) setRightPeriod(info.defaultPeriod);
                }}
                className="px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {functionOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>

              {/* Period input */}
              {rightInfo?.hasPeriod && (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={rightPeriod}
                    onChange={(e) => setRightPeriod(parseInt(e.target.value) || 1)}
                    min={1}
                    max={500}
                    className="w-14 px-2 py-1.5 text-sm text-center bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <span className="text-xs text-gray-400">d</span>
                </div>
              )}

              <span className="text-sm text-gray-500 dark:text-gray-400">of</span>

              {/* Asset */}
              <div className="flex items-center gap-1 px-3 py-1.5 bg-emerald-500 text-white rounded-full">
                <span className="w-2 h-2 rounded-full bg-white/80" />
                <input
                  type="text"
                  value={rightSymbol}
                  onChange={(e) => setRightSymbol(e.target.value.toUpperCase())}
                  className="w-12 bg-transparent text-sm font-medium focus:outline-none placeholder:text-white/60"
                  placeholder="SPY"
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="flex justify-end gap-2 px-4 py-3 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
        <button
          onClick={onCancel}
          className="px-4 py-1.5 text-sm text-gray-600 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-full transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-4 py-1.5 text-sm bg-emerald-500 hover:bg-emerald-600 text-white rounded-full transition-colors font-medium"
        >
          Save
        </button>
      </div>
    </div>
  );
}
