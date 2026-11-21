import { ConnectError } from '@connectrpc/connect';
import { SleeveType } from '@llamatrade/core/proto/ledger_pb';
import { getTenantContext, ledgerClient } from '@llamatrade/core/net';
import { useFundingStore } from '@llamatrade/core/stores/funding';

/**
 * Moves free paper cash from the Unallocated sleeve into a session's sleeve (TransferCapital).
 * Returns null on success, else a message to show.
 */
export async function moveToSession(sleeveId: string, amount: number): Promise<string | null> {
  const funding = useFundingStore.getState();
  if (!funding.resolved) await funding.resolveAccount();
  const credentialsId = useFundingStore.getState().paperCredentialId;
  if (!credentialsId) return 'No paper account is connected yet.';
  try {
    const context = getTenantContext();
    const acct = await ledgerClient.getOrCreateAccount({ context, credentialsId });
    const accountId = acct.account?.id;
    const from = acct.baseSleeves.find((s) => s.type === SleeveType.UNALLOCATED)?.id;
    if (!accountId || !from) return "The paper account's unallocated cash couldn't be found.";
    await ledgerClient.transferCapital({
      context,
      accountId,
      fromSleeveId: from,
      toSleeveId: sleeveId,
      amount: { value: amount.toFixed(2) },
      requestId: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`,
    });
    return null;
  } catch (e) {
    return e instanceof ConnectError ? e.rawMessage || e.message : 'The money could not be moved. Please try again.';
  }
}
