import { AppRegistry, Linking, Platform } from 'react-native';
import CallKeep, { CONSTANTS, type InitialEvents } from 'react-native-callkeep';
import VoipPush from 'react-native-voip-push-notification';
import * as SecureStore from 'expo-secure-store';
import { apiRequest } from '@/src/api/client';
import { callID, callUUID } from './callIdentity';
import { callHasEnded, finishCallRequest } from './callLifecycle';

export type NativeCall = { id: number; conversation: number; call_type: 'VOICE' | 'VIDEO'; caller_name: string };
type Controls = { end: () => void; mute: (muted: boolean) => void; hold: (held: boolean) => void };
const controls = new Map<number, Controls>();
const displayed = new Set<number>();
const answered = new Set<number>();
const pending = new Set<number>();
const ending = new Set<number>();
const answering = new Set<number>();
const outgoing = new Set<number>();
let answerHandler: ((call: NativeCall) => void) | null = null;
let initialized = false;
let configured = false;
let voipToken: string | null = null;

async function answer(uuid: string) {
  const id = callID(uuid);
  if (!id || answered.has(id) || answering.has(id) || ending.has(id)) return;
  if (!answerHandler) { pending.add(id); return; }
  answering.add(id);
  let calls: (NativeCall & { initiated_by?: { username: string; first_name?: string } })[];
  try { calls = await apiRequest('messaging/calls/incoming/'); } finally { answering.delete(id); }
  if (ending.has(id) || !answerHandler) return;
  const call = calls.find(item => item.id === id);
  if (!call) { endNativeCall(id); return; }
  answered.add(id); pending.delete(id);
  if (Platform.OS === 'android') CallKeep.backToForeground();
  answerHandler({ ...call, caller_name: call.caller_name || call.initiated_by?.first_name || call.initiated_by?.username || 'Awinlink user' });
}

async function end(uuid: string) {
  const id = callID(uuid);
  if (!id) return;
  ending.add(id);
  pending.delete(id);
  const control = controls.get(id);
  if (control) { control.end(); return; }
  // Verify server state; native events and push payloads are never authorization.
  await finishCallRequest(id, async () => {
    const incoming = await apiRequest<{ id: number }[]>('messaging/calls/incoming/');
    await apiRequest(`messaging/calls/${id}/${incoming.some(call => call.id === id) ? 'reject' : 'end'}/`, { method: 'POST', body: { end_for_everyone: true } });
  });
  displayed.delete(id); answered.delete(id);
}

export function initializeNativeCallEvents() {
  if (initialized || Platform.OS === 'web') return;
  initialized = true;
  CallKeep.addEventListener('answerCall', ({ callUUID }) => { void answer(callUUID).catch(() => {}); });
  CallKeep.addEventListener('endCall', ({ callUUID }) => { void end(callUUID).catch(() => {}); });
  CallKeep.addEventListener('didPerformSetMutedCallAction', ({ callUUID, muted }) => {
    const id = callID(callUUID); if (id) controls.get(id)?.mute(muted);
  });
  CallKeep.addEventListener('didToggleHoldCallAction', ({ callUUID, hold }) => {
    const id = callID(callUUID); if (id) controls.get(id)?.hold(hold);
  });
  CallKeep.addEventListener('checkReachability', () => CallKeep.setReachable());
  const replay = (events: InitialEvents) => {
    for (const event of events) {
      if (event.name === 'RNCallKeepPerformAnswerCallAction') void answer(event.data.callUUID).catch(() => {});
      if (event.name === 'RNCallKeepPerformEndCallAction') void end(event.data.callUUID).catch(() => {});
    }
  };
  CallKeep.addEventListener('didLoadWithEvents', replay);
  void CallKeep.getInitialEvents().then(events => { replay(events || []); CallKeep.clearInitialEvents(); }).catch(() => {});
  if (Platform.OS === 'ios') {
    const rememberToken = (token: string) => { voipToken = token; if (answerHandler) void registerVoipToken().catch(() => {}); };
    VoipPush.addEventListener('register', rememberToken);
    VoipPush.addEventListener('didLoadWithEvents', events => {
      for (const event of events) if (event.name === 'RNVoipPushRemoteNotificationsRegisteredEvent') rememberToken(String(event.data));
    });
  }
  if (Platform.OS === 'android') AppRegistry.registerHeadlessTask('RNCallKeepBackgroundMessage', () => async () => {
    CallKeep.setReachable();
    // Keep the bridge alive while a native ringing call can be answered or declined.
    await new Promise(resolve => setTimeout(resolve, 30_000));
  });
}

export async function registerVoipToken() {
  if (!voipToken) return;
  const expo_token = await SecureStore.getItemAsync('awinlink.push-token');
  await apiRequest('notifications/voip-push/', { method: 'POST', body: { token: voipToken, environment: __DEV__ ? 'development' : 'production', expo_token } });
  await SecureStore.setItemAsync('awinlink.voip-token', voipToken);
}

export async function enableNativeCallUI(onAnswer: (call: NativeCall) => void) {
  initializeNativeCallEvents();
  answerHandler = onAnswer;
  if (!configured) {
    await CallKeep.setup({ ios: { appName: 'Awinlink', supportsVideo: true, maximumCallGroups: '1', maximumCallsPerCallGroup: '1', includesCallsInRecents: false }, android: {
      alertTitle: 'Enable Awinlink calls', alertDescription: 'Enable the Awinlink phone account to answer calls from your lock screen.', cancelButton: 'Later', okButton: 'Open settings', additionalPermissions: [], selfManaged: false,
      foregroundService: { channelId: 'awinlink-active-calls', channelName: 'Awinlink active calls', notificationTitle: 'Awinlink call in progress', notificationIcon: 'ic_launcher' },
    } });
    configured = true;
  }
  if (Platform.OS === 'android') { CallKeep.setAvailable(true); CallKeep.canMakeMultipleCalls(false); }
  CallKeep.setReachable();
  if (Platform.OS === 'ios') await registerVoipToken();
  for (const id of pending) void answer(callUUID(id)).catch(() => {});
}

export function disableNativeCallUI() {
  answerHandler = null; pending.clear();
  for (const id of displayed) endNativeCall(id);
  if (Platform.OS === 'android') CallKeep.setAvailable(false);
}

export async function showNativeIncomingCall(call: NativeCall) {
  if (callHasEnded(call.id)) return false;
  if (!configured) return false;
  if (Platform.OS === 'android' && !await CallKeep.hasPhoneAccount()) return false;
  if (callHasEnded(call.id)) return false;
  if (!displayed.has(call.id)) {
    displayed.add(call.id);
    CallKeep.displayIncomingCall(callUUID(call.id), String(call.id), call.caller_name, 'generic', call.call_type === 'VIDEO', { ios: { supportsHolding: false, supportsDTMF: false, supportsGrouping: false, supportsUngrouping: false } });
  }
  return true;
}

export function bindNativeCall(id: number, incoming: boolean, name: string, video: boolean, control: Controls) {
  controls.set(id, control);
  if (configured && !displayed.has(id)) {
    displayed.add(id);
    if (!incoming) { outgoing.add(id); CallKeep.startCall(callUUID(id), String(id), name, 'generic', video); }
  }
  return () => { controls.delete(id); endNativeCall(id); };
}
export function nativeCallConnected(id: number) {
  if (!displayed.has(id)) return;
  if (Platform.OS === 'android') CallKeep.setCurrentCallActive(callUUID(id));
  else if (outgoing.has(id)) CallKeep.reportConnectedOutgoingCallWithUUID(callUUID(id));
  else { answered.add(id); CallKeep.answerIncomingCall(callUUID(id)); }
}
export function endNativeCall(id: number) {
  if (!Number.isSafeInteger(id) || id < 1 || id > 0xffffffffffff) return;
  displayed.delete(id); answered.delete(id); pending.delete(id);
  ending.add(id); outgoing.delete(id);
  try { CallKeep.reportEndCallWithUUID(callUUID(id), CONSTANTS.END_CALL_REASONS.REMOTE_ENDED); } catch { /* Media cleanup must continue even if Telecom is unavailable. */ }
}
export function syncNativeMute(id: number, muted: boolean) { if (displayed.has(id)) CallKeep.setMutedCall(callUUID(id), muted); }
export function openNativeCallSettings() { if (Platform.OS === 'android') void Linking.sendIntent('android.telecom.action.CHANGE_PHONE_ACCOUNTS').catch(() => Linking.openSettings()); }
