
import { create } from '@bufbuild/protobuf';
import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import {
  AlertConditionSchema,
  AlertConditionType,
  ChannelPreferenceSchema,
  ChannelType,
} from '@llamatrade/core/proto/notification_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { Copy, Plus, Send, Trash2 } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  CATEGORY_GROUPS,
  CHANNEL_LABELS,
  CONDITION_TYPE_LABELS,
  categoryLabel,
} from '../../types/notifications';
import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { Card } from '../common/Card';
import { Input } from '../common/Input';
import { Select } from '../common/Select';

const PREFERENCE_CHANNELS = [ChannelType.EMAIL, ChannelType.WEBHOOK] as const;

const CONDITION_OPTIONS = Object.entries(CONDITION_TYPE_LABELS).map(([value, label]) => ({
  value,
  label: label ?? '',
}));

export function NotificationSettings() {
  return (
    <div className="space-y-6">
      <PreferencesMatrix />
      <WebhookManager />
      <AlertManager />
    </div>
  );
}

function PreferencesMatrix() {
  const { preferences, fetchPreferences, updatePreferences } = useNotificationsStore();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void fetchPreferences();
  }, [fetchPreferences]);

  const enabledByChannel = useMemo(() => {
    const map = new Map<ChannelType, { enabled: boolean; categories: Set<NotificationCategory> }>();
    for (const pref of preferences) {
      map.set(pref.channel, { enabled: pref.enabled, categories: new Set(pref.categories) });
    }
    return map;
  }, [preferences]);

  const isOn = (channel: ChannelType, category: NotificationCategory): boolean => {
    const state = enabledByChannel.get(channel);
    if (!state || !state.enabled) return false;
    return state.categories.size === 0 || state.categories.has(category);
  };

  const toggle = async (channel: ChannelType, category: NotificationCategory) => {
    const state = enabledByChannel.get(channel);
    const allCategories = CATEGORY_GROUPS.flatMap((g) => [...g.categories]);
    const current = new Set(
      state && state.categories.size > 0
        ? state.categories
        : state?.enabled !== false
          ? allCategories
          : [],
    );
    if (current.has(category)) current.delete(category);
    else current.add(category);
    setSaving(true);
    try {
      await updatePreferences(
        PREFERENCE_CHANNELS.map((ch) => {
          const chState = enabledByChannel.get(ch);
          return create(ChannelPreferenceSchema, {
            channel: ch,
            enabled: chState?.enabled ?? true,
            categories:
              ch === channel
                ? [...current]
                : chState
                  ? [...chState.categories]
                  : [],
          });
        }),
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-5">
      <h3 className="text-sm font-bold uppercase tracking-wide text-ink">Delivery preferences</h3>
      <p className="mt-1 text-[13px] text-ink/60">
        In-app notifications are always kept. Critical and security notices always email.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full text-[13px]">
          <thead>
            <tr className="border-b-2 border-ink text-left">
              <th className="py-2 pr-4 font-mono uppercase tracking-wide text-[11px]">Category</th>
              {PREFERENCE_CHANNELS.map((ch) => (
                <th key={ch} className="py-2 px-3 font-mono uppercase tracking-wide text-[11px]">
                  {CHANNEL_LABELS[ch]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {CATEGORY_GROUPS.map((group) => (
              <GroupRows
                key={group.label}
                label={group.label}
                categories={group.categories}
                isOn={isOn}
                onToggle={toggle}
                disabled={saving}
              />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function GroupRows({
  label,
  categories,
  isOn,
  onToggle,
  disabled,
}: {
  label: string;
  categories: ReadonlyArray<NotificationCategory>;
  isOn: (channel: ChannelType, category: NotificationCategory) => boolean;
  onToggle: (channel: ChannelType, category: NotificationCategory) => Promise<void>;
  disabled: boolean;
}) {
  return (
    <>
      <tr>
        <td
          colSpan={1 + PREFERENCE_CHANNELS.length}
          className="pt-4 pb-1 font-mono uppercase tracking-wide text-[11px] text-ink/50"
        >
          {label}
        </td>
      </tr>
      {categories.map((category) => (
        <tr key={category} className="border-b border-ink/10">
          <td className="py-1.5 pr-4 text-ink">{categoryLabel(category)}</td>
          {PREFERENCE_CHANNELS.map((ch) => (
            <td key={ch} className="py-1.5 px-3">
              <input
                type="checkbox"
                checked={isOn(ch, category)}
                disabled={disabled}
                onChange={() => void onToggle(ch, category)}
                className="h-4 w-4 accent-orange-500"
                aria-label={`${categoryLabel(category)} via ${CHANNEL_LABELS[ch]}`}
              />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function WebhookManager() {
  const { webhooks, fetchWebhooks, createWebhook, updateWebhook, deleteWebhook, testWebhook } =
    useNotificationsStore();
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void fetchWebhooks();
  }, [fetchWebhooks]);

  const handleCreate = async () => {
    if (!name.trim() || !url.trim()) return;
    setBusy(true);
    try {
      const { secret } = await createWebhook({ name, url, events: [] });
      setNewSecret(secret);
      setName('');
      setUrl('');
    } catch (error) {
      setTestResult(error instanceof Error ? error.message : 'Webhook creation failed');
    } finally {
      setBusy(false);
    }
  };

  const handleTest = async (webhookId: string) => {
    setBusy(true);
    try {
      const result = await testWebhook(webhookId);
      setTestResult(
        result.success ? `Delivered (HTTP ${result.statusCode})` : `Failed: ${result.message}`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <h3 className="text-sm font-bold uppercase tracking-wide text-ink">Webhooks</h3>
      <p className="mt-1 text-[13px] text-ink/60">
        Signed POSTs (X-Webhook-Signature, HMAC-SHA256 of the raw body) to your endpoint.
        A persistently failing endpoint is disabled automatically.
      </p>

      {newSecret && (
        <div className="mt-3 border-2 border-ink bg-orange-500/10 p-3 text-[13px]">
          <p className="font-medium text-ink">
            Signing secret (shown once — store it now):
          </p>
          <div className="mt-1 flex items-center gap-2">
            <code className="font-mono text-[12px] break-all">{newSecret}</code>
            <button
              onClick={() => {
                void navigator.clipboard.writeText(newSecret);
              }}
              aria-label="Copy secret"
              className="shrink-0 text-ink/60 hover:text-ink"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
          <Button size="sm" variant="ghost" className="mt-2" onClick={() => setNewSecret(null)}>
            I stored it
          </Button>
        </div>
      )}
      {testResult && <p className="mt-2 text-[13px] text-ink/70">{testResult}</p>}

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <Input
          placeholder="Name (e.g. ops-alerts)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-48"
        />
        <Input
          placeholder="https://example.com/hooks/llamatrade"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          className="flex-1 min-w-64"
        />
        <Button size="sm" onClick={() => void handleCreate()} disabled={busy}>
          <Plus className="h-4 w-4" />
          Add webhook
        </Button>
      </div>

      <div className="mt-4 space-y-2">
        {webhooks.map((webhook) => (
          <div
            key={webhook.id}
            className="flex flex-wrap items-center gap-3 border-2 border-ink/20 px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink truncate">{webhook.name}</p>
              <p className="text-[12px] font-mono text-ink/60 truncate">{webhook.url}</p>
            </div>
            {!webhook.isActive && <Badge variant="danger">Disabled</Badge>}
            {webhook.failureCount > 0 && webhook.isActive && (
              <Badge variant="accent">{webhook.failureCount} failures</Badge>
            )}
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => void handleTest(webhook.id)}
            >
              <Send className="h-3.5 w-3.5" />
              Test
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() =>
                void updateWebhook({ ...webhook, isActive: !webhook.isActive })
              }
            >
              {webhook.isActive ? 'Disable' : 'Re-enable'}
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={() => void deleteWebhook(webhook.id)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        {webhooks.length === 0 && (
          <p className="text-[13px] text-ink/50">No webhooks configured.</p>
        )}
      </div>
    </Card>
  );
}

function AlertManager() {
  const { alerts, fetchAlerts, createAlert, deleteAlert, toggleAlert } = useNotificationsStore();
  const [name, setName] = useState('');
  const [symbol, setSymbol] = useState('');
  const [threshold, setThreshold] = useState('');
  const [conditionType, setConditionType] = useState<string>(
    String(AlertConditionType.PRICE_ABOVE),
  );
  const [emailToo, setEmailToo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void fetchAlerts();
  }, [fetchAlerts]);

  const handleCreate = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await createAlert({
        name,
        description: '',
        condition: create(AlertConditionSchema, {
          type: Number(conditionType) as AlertConditionType,
          symbol: symbol.trim().toUpperCase(),
          threshold: { value: threshold || '0' },
        }),
        channels: emailToo ? [ChannelType.EMAIL] : [],
        cooldownMinutes: 60,
      });
      setName('');
      setSymbol('');
      setThreshold('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Alert creation failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="p-5">
      <h3 className="text-sm font-bold uppercase tracking-wide text-ink">Price alerts</h3>
      <p className="mt-1 text-[13px] text-ink/60">
        Fire a notification when a market or trading condition is met. One-hour cooldown between
        triggers.
      </p>
      {error && <p className="mt-2 text-[13px] text-red-600">{error}</p>}

      <div className="mt-4 flex flex-wrap items-end gap-2">
        <Input
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="w-44"
        />
        <Select
          value={conditionType}
          onChange={(e) => setConditionType(e.target.value)}
          options={CONDITION_OPTIONS}
          className="w-44"
        />
        <Input
          placeholder="Symbol"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="w-28"
        />
        <Input
          placeholder="Threshold"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          className="w-28"
        />
        <label className="flex items-center gap-1.5 text-[13px] text-ink/70">
          <input
            type="checkbox"
            checked={emailToo}
            onChange={(e) => setEmailToo(e.target.checked)}
            className="h-4 w-4 accent-orange-500"
          />
          Email me
        </label>
        <Button size="sm" onClick={() => void handleCreate()} disabled={busy}>
          <Plus className="h-4 w-4" />
          Add alert
        </Button>
      </div>

      <div className="mt-4 space-y-2">
        {alerts.map((alert) => (
          <div
            key={alert.id}
            className="flex flex-wrap items-center gap-3 border-2 border-ink/20 px-3 py-2"
          >
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink truncate">{alert.name}</p>
              <p className="text-[12px] font-mono text-ink/60">
                {CONDITION_TYPE_LABELS[alert.condition?.type ?? AlertConditionType.UNSPECIFIED] ??
                  'Condition'}
                {alert.condition?.symbol ? ` · ${alert.condition.symbol}` : ''}
                {alert.condition?.threshold?.value
                  ? ` · ${alert.condition.threshold.value}`
                  : ''}
                {alert.timesTriggered > 0 ? ` · fired ${alert.timesTriggered}×` : ''}
              </p>
            </div>
            <Badge variant={alert.isActive ? 'success' : 'gray'}>
              {alert.isActive ? 'Active' : 'Paused'}
            </Badge>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => void toggleAlert(alert.id, !alert.isActive)}
            >
              {alert.isActive ? 'Pause' : 'Resume'}
            </Button>
            <Button
              size="sm"
              variant="danger"
              disabled={busy}
              onClick={() => void deleteAlert(alert.id)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
        {alerts.length === 0 && <p className="text-[13px] text-ink/50">No alerts yet.</p>}
      </div>
    </Card>
  );
}
