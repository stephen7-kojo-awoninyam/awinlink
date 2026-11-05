export type NativeCall = { id: number; conversation: number; call_type: 'VOICE' | 'VIDEO'; caller_name: string };
export function initializeNativeCallEvents() {}
export async function enableNativeCallUI(_handler: (call: NativeCall) => void) {}
export function disableNativeCallUI() {}
export async function showNativeIncomingCall(_call: NativeCall) { return false; }
export async function registerVoipToken() {}
export function openNativeCallSettings() {}

export function bindNativeCall(..._args: unknown[]) { return () => {}; }
export function nativeCallConnected(_id: number) {}
export function endNativeCall(_id: number) {}
export function syncNativeMute(_id: number, _muted: boolean) {}
