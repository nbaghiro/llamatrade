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
} from '@llamatrade/core/strategy/types';
import { INDICATORS, COMPARATORS, getIndicatorInfo } from '@llamatrade/core/strategy/types';

interface ConditionEditorProps {
  condition: ConditionExpression;
  defaultSymbol: string;
  onSave: (condition: ConditionExpression) => void;
  onCancel: () => void;
}

type OperandType = 'price' | 'indicator' | 'number';

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
    <div data-testid="condition-editor" className="bg-paper border-2 border-ink shadow-lg w-[420px]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <span className="text-[11px] font-mono font-bold uppercase tracking-wide text-ink/70">
          Edit Conditional
        </span>
        <button
          onClick={onCancel}
          className="p-1 hover:bg-ink/10 transition-colors"
        >
          <X className="w-4 h-4 text-ink/60" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-ink/60 w-6">if</span>

          <select
            value={leftFunc}
            onChange={(e) => {
              setLeftFunc(e.target.value);
              const info = INDICATORS.find(i => i.name === e.target.value);
              if (info?.defaultPeriod) setLeftPeriod(info.defaultPeriod);
            }}
            className="px-3 py-1.5 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            {functionOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          {leftInfo?.hasPeriod && (
            <div className="flex items-center gap-1">
              <input
                type="number"
                value={leftPeriod}
                onChange={(e) => setLeftPeriod(parseInt(e.target.value) || 1)}
                min={1}
                max={500}
                className="w-14 px-2 py-1.5 text-sm text-center bg-paper text-ink border-2 border-ink focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <span className="text-xs text-ink/60">d</span>
            </div>
          )}

          <span className="text-sm text-ink/60">of</span>

          <div className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-bone border-2 border-ink">
            <span className="w-2 h-2 rounded-full bg-bone" />
            <input
              type="text"
              value={leftSymbol}
              onChange={(e) => setLeftSymbol(e.target.value.toUpperCase())}
              className="w-12 bg-transparent text-sm font-mono font-bold focus:outline-none placeholder:text-bone/60"
              placeholder="SPY"
            />
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-ink/60 w-6">is</span>

          <select
            value={comparator}
            onChange={(e) => setComparator(e.target.value as Comparator)}
            className="px-3 py-1.5 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {COMPARATORS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.verboseLabel}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-ink/60 w-6" />

          <div className="flex border-2 border-ink overflow-hidden">
            <button
              onClick={() => setRightType('indicator')}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                rightType === 'indicator'
                  ? 'bg-blue-600 text-bone'
                  : 'bg-paper text-ink hover:bg-ink hover:text-bone'
              }`}
            >
              Function
            </button>
            <button
              onClick={() => setRightType('value')}
              className={`px-3 py-1 text-xs font-medium transition-colors ${
                rightType === 'value'
                  ? 'bg-blue-600 text-bone'
                  : 'bg-paper text-ink hover:bg-ink hover:text-bone'
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
              className="w-20 px-3 py-1.5 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          ) : (
            <>
              <select
                value={rightFunc}
                onChange={(e) => {
                  setRightFunc(e.target.value);
                  const info = INDICATORS.find(i => i.name === e.target.value);
                  if (info?.defaultPeriod) setRightPeriod(info.defaultPeriod);
                }}
                className="px-3 py-1.5 text-sm bg-paper text-ink border-2 border-ink focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                {functionOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>

              {rightInfo?.hasPeriod && (
                <div className="flex items-center gap-1">
                  <input
                    type="number"
                    value={rightPeriod}
                    onChange={(e) => setRightPeriod(parseInt(e.target.value) || 1)}
                    min={1}
                    max={500}
                    className="w-14 px-2 py-1.5 text-sm text-center bg-paper text-ink border-2 border-ink focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <span className="text-xs text-ink/60">d</span>
                </div>
              )}

              <span className="text-sm text-ink/60">of</span>

              <div className="flex items-center gap-1 px-3 py-1.5 bg-green-600 text-bone border-2 border-ink">
                <span className="w-2 h-2 rounded-full bg-bone" />
                <input
                  type="text"
                  value={rightSymbol}
                  onChange={(e) => setRightSymbol(e.target.value.toUpperCase())}
                  className="w-12 bg-transparent text-sm font-mono font-bold focus:outline-none placeholder:text-bone/60"
                  placeholder="SPY"
                />
              </div>
            </>
          )}
        </div>
      </div>

      <div className="flex justify-end gap-2 px-4 py-3 border-t-2 border-ink bg-bone">
        <button
          onClick={onCancel}
          className="px-4 py-1.5 text-sm text-ink border-2 border-ink hover:bg-ink hover:text-bone transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSave}
          className="px-4 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-bone border-2 border-ink transition-colors font-mono font-bold uppercase tracking-wide"
        >
          Save
        </button>
      </div>
    </div>
  );
}
