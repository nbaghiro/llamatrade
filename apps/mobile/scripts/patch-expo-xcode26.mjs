/**
 * Xcode 26 Swift-compat shim for expo-modules-jsi (Expo SDK 57).
 *
 * Under Xcode 26's Swift compiler, `abs(_:)` in expo-modules-jsi's
 * JavaScriptCodable+Date.swift is ambiguous ("type of expression is ambiguous
 * without a type annotation"), which fails `expo run:ios`. `Double.magnitude`
 * is the unambiguous, semantically identical equivalent.
 *
 * Idempotent — safe to re-run. Runs as apps/mobile's `postinstall` so the fix
 * survives `npm install`. DELETE this once Expo ships Xcode-26 support.
 *
 * (patch-package can't generate/apply here — nested npm-workspace node_modules
 * with no app-level lockfile — so this hand-rolled patch is the durable path.)
 */
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const INNER = 'apple/Sources/ExpoModulesJSI/Coding/JavaScriptCodable+Date.swift';
const NEEDLE = 'abs(milliseconds) <= maxJavaScriptDateMilliseconds';
const FIX = 'milliseconds.magnitude <= maxJavaScriptDateMilliseconds';

const here = dirname(fileURLToPath(import.meta.url)); // apps/mobile/scripts
const candidates = [
  join(here, '..', 'node_modules', 'expo-modules-jsi', INNER), // apps/mobile/node_modules
  join(here, '..', '..', '..', 'node_modules', 'expo-modules-jsi', INNER), // hoisted root
];

const file = candidates.find(existsSync);
if (!file) {
  console.log('[patch:xcode26] expo-modules-jsi not found — skipping');
  process.exit(0);
}

const src = readFileSync(file, 'utf8');
if (!src.includes(NEEDLE)) {
  process.exit(0); // already patched or upstream changed
}
writeFileSync(file, src.replace(NEEDLE, FIX));
console.log('[patch:xcode26] applied abs()->magnitude to expo-modules-jsi');
