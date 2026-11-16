import { useDeployStore, validateDeploy } from '@llamatrade/core/stores/deploy';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import { DEFAULT_RISK_LIMITS } from '../../lib/sessionState';
import { rebalanceWord } from '../../types/backtest';
import { KvList } from '../backtest/parts';
import { PaperPill } from '../shell/PaperPill';
import { Sheet } from '../ui/Sheet';

export interface DeploySheetProps {
  open: boolean;
  onClose: () => void;
  strategyId: string;
  strategyName: string;
  /** 0 deploys the current version. */
  strategyVersion: number;
  /** Strategy.rebalance, e.g. "monthly". */
  rebalance?: string;
  /** Where the sheet was opened from, e.g. "from this backtest". */
  context?: string;
  /** Suggested capital, e.g. the backtest's starting capital. */
  suggestedCapital?: number;
}

/**
 * Starts a paper session for one strategy version: capital against unallocated cash,
 * the limits it trades under, then the session. The first orders aren't previewed;
 * they're worked out at the first rebalance.
 */
export function DeploySheet({
  open,
  onClose,
  strategyId,
  strategyName,
  strategyVersion,
  rebalance,
  context = 'Alpaca paper',
  suggestedCapital,
}: DeploySheetProps) {
  const navigate = useNavigate();
  const resolveAccount = useFundingStore((s) => s.resolveAccount);
  const resolved = useFundingStore((s) => s.resolved);
  const resolving = useFundingStore((s) => s.resolving);
  const unallocated = useFundingStore((s) => s.unallocatedCash);
  const credentialId = useFundingStore((s) => s.paperCredentialId);
  const deploy = useDeployStore((s) => s.deploy);
  const deploying = useDeployStore((s) => s.deploying);
  const deployError = useDeployStore((s) => s.error);
  const clearError = useDeployStore((s) => s.clearError);
  const [draft, setDraft] = useState('');
  const [touched, setTouched] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    clearError();
    setTouched(false);
    setLiveError(null);
    resolveAccount().catch(() => undefined);
  }, [open, resolveAccount, clearError]);

  useEffect(() => {
    if (!open || !resolved) return;
    const start =
      suggestedCapital && suggestedCapital > 0
        ? Math.min(suggestedCapital, unallocated)
        : unallocated;
    setDraft(start > 0 ? String(Math.floor(start * 100) / 100) : '');
  }, [open, resolved, suggestedCapital, unallocated]);

  const amount = Number(draft);
  const invalid = resolved
    ? validateDeploy({
        allocation: amount,
        unallocatedCash: unallocated,
        hasPaperCredential: credentialId !== null,
      })
    : null;
  const noKeys = resolved && credentialId === null;

  const onStart = async () => {
    setTouched(true);
    if (invalid) return;
    const result = await deploy({
      strategyId,
      strategyName,
      strategyVersion,
      allocation: amount,
      goLive: true,
    });
    if (!result) return;
    if (result.liveError) {
      setLiveError(result.liveError);
      return;
    }
    onClose();
    navigate(result.sessionId ? `/trading/${result.sessionId}` : '/trading');
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      width={520}
      title={
        <span className="grid gap-0.5">
          <span>Deploy {strategyName} to paper</span>
          <span className="text-xs font-normal text-fg-3">
            {strategyVersion ? `Version ${strategyVersion}` : 'Current version'} · {context}
          </span>
        </span>
      }
      footer={
        <>
          <span className="mr-auto self-center text-[11.5px] text-fg-3">
            Paper only during the beta.
          </span>
          <button type="button" className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={
              deploying ||
              !resolved ||
              noKeys ||
              Boolean(liveError) ||
              (touched && Boolean(invalid))
            }
            onClick={onStart}
          >
            {deploying ? 'Starting…' : 'Start session'}
          </button>
        </>
      }
    >
      <div className="grid gap-4 px-[18px] py-4">
        {noKeys ? (
          <div
            role="alert"
            className="rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2.5 text-[12.5px]"
          >
            <b className="block font-semibold text-risk">Alpaca paper isn&apos;t connected</b>
            Connect your paper keys in Settings, then deploy from here.{' '}
            <Link to="/settings/broker" className="text-accent hover:underline">
              Open Settings
            </Link>
          </div>
        ) : (
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-fg-2">Capital</span>
            <span className="flex items-center gap-1.5">
              <span className="text-fg-3">$</span>
              <input
                type="number"
                inputMode="decimal"
                min={0}
                step={100}
                value={draft}
                disabled={!resolved}
                onChange={(e) => {
                  setDraft(e.target.value);
                  setTouched(true);
                }}
                aria-invalid={touched && Boolean(invalid)}
                aria-describedby="deploy-capital-help"
                className={`input num ${touched && invalid ? 'input-error' : ''}`}
              />
            </span>
            <span
              id="deploy-capital-help"
              className={`text-[11.5px] ${touched && invalid ? 'text-risk' : 'text-fg-3'}`}
            >
              {resolving && !resolved
                ? 'Reading your paper account…'
                : touched && invalid
                  ? invalid
                  : `of ${formatMoney(unallocated)} unallocated`}
            </span>
          </label>
        )}

        <div className="grid gap-2">
          <b className="text-[13px] font-semibold">Limits this session trades under</b>
          <KvList
            rows={[
              ['Order value', formatMoney(DEFAULT_RISK_LIMITS.maxOrderValue, { dp: 0 })],
              ['Position size', formatMoney(DEFAULT_RISK_LIMITS.maxPositionSize, { dp: 0 })],
              ['Daily loss', formatMoney(DEFAULT_RISK_LIMITS.maxDailyLoss, { dp: 0 })],
              ['Order rate', `${DEFAULT_RISK_LIMITS.ordersPerMinute} a minute`],
            ]}
          />
          <p className="m-0 text-[12px] text-fg-3">
            These are the default limits. If your account has its own, those apply instead; they
            can&apos;t be viewed or changed in the app yet.
          </p>
        </div>

        <div className="grid gap-1.5">
          <b className="text-[13px] font-semibold">First orders</b>
          <p className="m-0 text-[12.5px] text-fg-2">
            The first orders are worked out at the next rebalance after you deploy. Each one runs
            through the seven risk checks before it reaches Alpaca.
          </p>
        </div>

        <KvList
          rows={[
            ['Rebalances', rebalanceWord(rebalance)],
            ['Starts', 'with the next market data for its symbols'],
            ['Mode', <PaperPill key="mode" />],
          ]}
        />

        {(deployError || liveError) && (
          <div
            role="alert"
            className="rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2.5 text-[12.5px]"
          >
            {liveError ? (
              <>
                <b className="block font-semibold text-risk">
                  The capital is set aside, but the session didn&apos;t start
                </b>
                {liveError}{' '}
                <Link to="/trading" className="text-accent hover:underline" onClick={onClose}>
                  Open Sessions
                </Link>
              </>
            ) : (
              <>
                <b className="block font-semibold text-risk">The session couldn&apos;t start</b>
                {deployError}
              </>
            )}
          </div>
        )}
      </div>
    </Sheet>
  );
}
