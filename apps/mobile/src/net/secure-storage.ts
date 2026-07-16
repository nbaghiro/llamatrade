/**
 * Zustand persist adapter backed by the device secure enclave (Keychain /
 * Keystore) instead of localStorage/AsyncStorage. Used for the auth session;
 * Alpaca broker keys should use SecureStore directly too — never plain storage.
 */
import * as SecureStore from 'expo-secure-store';
import type { StateStorage } from 'zustand/middleware';

export const secureStorage: StateStorage = {
  getItem: (name) => SecureStore.getItemAsync(name),
  setItem: (name, value) => SecureStore.setItemAsync(name, value),
  removeItem: (name) => SecureStore.deleteItemAsync(name),
};
