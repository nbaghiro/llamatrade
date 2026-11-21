import { create } from '@bufbuild/protobuf';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { TransactionSchema, TransactionType } from '@llamatrade/core/proto/portfolio_pb';
import { mapRow } from '@llamatrade/core/stores/activity';
import { describe, expect, it } from 'vitest';

const txn = (type: TransactionType, description = '') =>
  create(TransactionSchema, { id: 't1', type, amount: { value: '2500' }, description });

describe('mapRow funding labels', () => {
  it('never calls a deposit paper when the account is unknown', () => {
    const row = mapRow(txn(TransactionType.DEPOSIT));
    expect(row.label).toBe('Deposit');
    expect(row.sublabel).toBe('Into unallocated cash');
    expect(row.sublabel).not.toMatch(/paper/i);
    expect(row.signed).toBe(2500);
  });

  it('describes a withdrawal by where the cash came from', () => {
    const row = mapRow(txn(TransactionType.WITHDRAWAL));
    expect(row.sublabel).toBe('From unallocated cash');
    expect(row.signed).toBe(-2500);
  });

  it('keeps the description the ledger gives', () => {
    expect(mapRow(txn(TransactionType.DEPOSIT, 'Live deposit')).sublabel).toBe('Live deposit');
  });
});

describe('mapRow account and sleeve', () => {
  it('carries the account mode and sleeve the ledger booked the row on', () => {
    const live = mapRow(
      create(TransactionSchema, {
        id: 't2',
        type: TransactionType.DEPOSIT,
        amount: { value: '100' },
        executionMode: ExecutionMode.LIVE,
        sleeveId: 'sl-unalloc',
        accountId: 'acct-1',
      })
    );
    expect(live.account).toBe('live');
    expect(live.sleeveId).toBe('sl-unalloc');
    const paper = mapRow(
      create(TransactionSchema, { type: TransactionType.BUY, executionMode: ExecutionMode.PAPER })
    );
    expect(paper.account).toBe('paper');
  });

  it('leaves the account and sleeve unknown when the transaction has neither', () => {
    const row = mapRow(txn(TransactionType.DEPOSIT));
    expect(row.account).toBeNull();
    expect(row.sleeveId).toBe('');
  });
});
