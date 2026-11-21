import assert from 'node:assert/strict';
import { test } from 'node:test';

import { checkRegister, checkSignIn, registerError, resetError, RpcCode, signInError, UNREACHABLE, WRONG_PASSWORD } from '../errors.ts';
import { exampleBacktest } from '../example.ts';

test('sign in: wrong credentials sit under the password field', () => {
  assert.deepEqual(signInError({ code: RpcCode.Unauthenticated, message: 'Invalid email or password' }), {
    field: 'password',
    message: WRONG_PASSWORD,
  });
  assert.equal(signInError({ code: RpcCode.Unavailable, message: '' }).message, UNREACHABLE);
  assert.equal(signInError({ code: null, message: '', network: true }).field, null);
  assert.match(signInError({ code: RpcCode.ResourceExhausted, message: '' }).message, /Too many attempts/);
});

test('sign in and register: checked before sending', () => {
  assert.equal(checkSignIn('', 'x')?.field, 'email');
  assert.equal(checkSignIn('sam@', 'x')?.field, 'email');
  assert.equal(checkSignIn('sam@rivera.dev', '')?.field, 'password');
  assert.equal(checkSignIn('sam@rivera.dev', 'pw'), null);
  assert.equal(checkRegister({ workspace: 'R', email: 'a@b.co', password: 'short', inviteCode: 'X' })?.field, 'password');
  assert.equal(checkRegister({ workspace: 'R', email: 'a@b.co', password: 'longenough', inviteCode: '' })?.field, 'inviteCode');
});

test('register and reset: server errors land on the right field or state', () => {
  assert.equal(registerError({ code: RpcCode.InvalidArgument, message: 'invite code is not valid' }).field, 'inviteCode');
  assert.equal(registerError({ code: RpcCode.AlreadyExists, message: 'exists' }).field, 'email');
  assert.equal(resetError({ code: RpcCode.InvalidArgument, message: 'Invalid or expired reset link' }).state, 'expired');
  assert.equal(resetError({ code: RpcCode.InvalidArgument, message: 'Password too short' }).state, 'choose');
});

test('example backtest is fixed and ends where the web example does', () => {
  const ex = exampleBacktest();
  assert.equal(ex.strategy.length, ex.days.length);
  assert.equal(Math.round(ex.strategy[ex.strategy.length - 1] * 100) / 100, 30352.18);
  assert.equal((ex.total * 100).toFixed(1), '21.4');
  assert.equal(ex.benchmarkValues[0], 25000);
});
