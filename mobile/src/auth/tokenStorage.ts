import * as SecureStore from 'expo-secure-store';

export const getItemAsync = SecureStore.getItemAsync;
export const deleteItemAsync = SecureStore.deleteItemAsync;

export function setItemAsync(key: string, value: string, options?: SecureStore.SecureStoreOptions) {
  // Authenticated CallKit actions can run while the phone is locked. Tokens stay
  // device-bound and are available only after the first unlock following reboot.
  return SecureStore.setItemAsync(key, value, {
    keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY,
    ...options,
  });
}
