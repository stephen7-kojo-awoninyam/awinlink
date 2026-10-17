import { useEffect, useRef, useState } from 'react';
import { AppState, Modal, Platform, Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';

import { apiRequest, getAccessToken, getWebSocketUrl } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { enableNativeCallUI, disableNativeCallUI, showNativeIncomingCall, endNativeCall, registerVoipToken } from './nativeCallUI';
import { callHasEnded, finishCallRequest, notifyCallEnded } from './callLifecycle';

type IncomingCall = {
  id: number;
  conversation: number;
  call_type: 'VOICE' | 'VIDEO';
  caller_name: string;
};

Notifications.setNotificationHandler({
  handleNotification: async (notification) => {
    const isIncomingCall = notification.request.content.data?.type === 'incoming_call';
    return {
      shouldShowBanner: !isIncomingCall,
      shouldShowList: !isIncomingCall,
      shouldPlaySound: !isIncomingCall,
      shouldSetBadge: false,
    };
  },
});

function socketWithToken(url: string, token: string) {
  const Socket = WebSocket as unknown as new (
    url: string,
    protocols: string[],
    options: { headers: Record<string, string> },
  ) => WebSocket;
  return new Socket(url, [], { headers: { Authorization: `Bearer ${token}` } });
}

function callFromData(data: Record<string, unknown>): IncomingCall | null {
  const id = Number(data.call_id);
  const conversation = Number(data.conversation_id ?? data.conversation);
  const callType = data.call_type;
  const caller = data.caller;
  const callerName = typeof data.caller_name === 'string'
    ? data.caller_name
    : typeof caller === 'object' && caller !== null && 'username' in caller
      ? String(caller.username)
      : 'Awinlink user';
  if (!Number.isInteger(id) || id < 1 || !Number.isInteger(conversation) || conversation < 1) return null;
  if (callType !== 'VOICE' && callType !== 'VIDEO') return null;
  return { id, conversation, call_type: callType, caller_name: callerName };
}

async function registerNativePushToken() {
  if (!Device.isDevice || (Platform.OS !== 'ios' && Platform.OS !== 'android')) return;
  try {
    if (Platform.OS === 'android') {
      await Notifications.setNotificationChannelAsync('incoming-calls', {
        name: 'Incoming calls',
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        sound: 'default',
        lightColor: '#2458d3',
      });
    }
    await Notifications.setNotificationCategoryAsync('incoming-call', [
      {
        identifier: 'ANSWER',
        buttonTitle: 'Answer',
        options: { opensAppToForeground: true },
      },
      {
        identifier: 'DECLINE',
        buttonTitle: 'Decline',
        options: { opensAppToForeground: true, isDestructive: true },
      },
    ]);

    let permission = await Notifications.getPermissionsAsync();
    const alreadyGranted = permission.granted ||
      permission.ios?.status === Notifications.IosAuthorizationStatus.PROVISIONAL;
    if (!alreadyGranted) permission = await Notifications.requestPermissionsAsync();
    if (!permission.granted &&
      permission.ios?.status !== Notifications.IosAuthorizationStatus.PROVISIONAL) return;

    const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID ||
      Constants.easConfig?.projectId || Constants.expoConfig?.extra?.eas?.projectId;
    if (!projectId) return;
    const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
    await apiRequest('notifications/mobile-push/', {
      method: 'POST',
      body: { token, platform: Platform.OS },
    });
    await SecureStore.setItemAsync('awinlink.push-token', token);
    if (Platform.OS === 'ios') await registerVoipToken();
  } catch {
    // Calls remain available through foreground WebSockets if native push setup is unavailable.
  }
}

export function IncomingCallListener() {
  const { user } = useAuth();
  const [fallback, setFallback] = useState<IncomingCall | null>(null);
  const fallbackActions = useRef<{ answer: () => void; decline: () => void } | null>(null);
  const alertingCall = useRef<number | null>(null);
  const handledCall = useRef<number | null>(null);
  const routedCalls = useRef(new Set<number>());

  useEffect(() => {
    if (!user) return;
    handledCall.current = null;
    routedCalls.current.clear();
    let active = true;
    let socket: WebSocket | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;
    let incomingRequest = 0;

    const routeToCall = (call: IncomingCall, autoAccept = false) => {
      if (!active || callHasEnded(call.id) || routedCalls.current.has(call.id)) return;
      setFallback(null);
      routedCalls.current.add(call.id);
      handledCall.current = call.id;
      alertingCall.current = null;
      router.push({ pathname: '/call/[id]', params: {
        id: String(call.id), mode: 'incoming', callType: call.call_type,
        conversationId: String(call.conversation), title: call.caller_name,
        autoAccept: autoAccept ? 'true' : 'false',
      } });
    };

    void enableNativeCallUI(call => routeToCall(call, true)).catch(() => {});

    const showIncomingCall = async (call: IncomingCall) => {
      if (!active || callHasEnded(call.id) || handledCall.current === call.id || alertingCall.current === call.id) return;
      alertingCall.current = call.id;
      const shown = await showNativeIncomingCall(call).catch(() => false);
      if (!active || callHasEnded(call.id)) { endNativeCall(call.id); return; }
      if (shown) return;
      fallbackActions.current = {
        decline: () => {
          handledCall.current = call.id;
          alertingCall.current = null;
          setFallback(null);
          endNativeCall(call.id);
          void finishCallRequest(call.id, () => apiRequest(`messaging/calls/${call.id}/reject/`, { method: 'POST' })).catch(() => {});
        },
        answer: () => routeToCall(call),
      };
      setFallback(call);
    };

    const handlePushResponse = (response: Notifications.NotificationResponse) => {
      const data = response.notification.request.content.data as Record<string, unknown>;
      const call = callFromData(data);
      if (!call) return;
      if (response.actionIdentifier === 'DECLINE') {
        handledCall.current = call.id;
        endNativeCall(call.id);
        void finishCallRequest(call.id, () => apiRequest(`messaging/calls/${call.id}/reject/`, { method: 'POST' })).catch(() => {});
      } else {
        routeToCall(call, response.actionIdentifier === 'ANSWER');
      }
    };

    const responseSubscription = Notifications.addNotificationResponseReceivedListener(handlePushResponse);
    const receivedSubscription = Notifications.addNotificationReceivedListener((notification) => {
      const call = callFromData(notification.request.content.data as Record<string, unknown>);
      if (call) void showIncomingCall(call);
    });
    void Notifications.getLastNotificationResponseAsync().then((response) => {
      if (active && response) handlePushResponse(response);
    }).catch(() => {});
    void registerNativePushToken();

    const checkIncoming = async () => {
      if (!active || AppState.currentState !== 'active') return;
      const request = ++incomingRequest;
      try {
        const calls = await apiRequest<{
          id: number;
          conversation: number;
          call_type: 'VOICE' | 'VIDEO';
          initiated_by: { username: string; first_name?: string; last_name?: string };
        }[]>('messaging/calls/incoming/');
        if (!active || request !== incomingRequest) return;
        calls.forEach((item) => {
          const callerName = [item.initiated_by.first_name, item.initiated_by.last_name]
            .filter(Boolean)
            .join(' ') || item.initiated_by.username;
          void showIncomingCall({
            id: item.id,
            conversation: item.conversation,
            call_type: item.call_type,
            caller_name: callerName,
          });
        });
        if (alertingCall.current && !calls.some(call => call.id === alertingCall.current)) {
          const id = alertingCall.current;
          notifyCallEnded(id); endNativeCall(id); alertingCall.current = null;
          setFallback(current => current?.id === id ? null : current);
        }
      } catch {
        // Push and the authenticated user WebSocket remain available during feed failures.
      }
    };

    const foregroundSubscription = AppState.addEventListener('change', state => {
      if (active && state === 'active') {
        void registerNativePushToken();
        void checkIncoming();
      }
    });

    void (async () => {
      const token = await getAccessToken();
      if (!active || !token) return;
      try {
        socket = socketWithToken(getWebSocketUrl('ws/user/'), token);
        socket.onmessage = (event) => {
          if (!active) return;
          try {
            const message = JSON.parse(String(event.data)) as { type?: string; call_id?: number };
            if (message.type === 'incoming_call' && message.call_id) void checkIncoming();
            if (message.type === 'call_ended' && message.call_id) {
              notifyCallEnded(message.call_id); endNativeCall(message.call_id);
              if (alertingCall.current === message.call_id) alertingCall.current = null;
              setFallback(current => current?.id === message.call_id ? null : current);
              void Notifications.getPresentedNotificationsAsync().then(items => Promise.all(items
                .filter(item => Number(item.request.content.data?.call_id) === message.call_id)
                .map(item => Notifications.dismissNotificationAsync(item.request.identifier)))).catch(() => {});
            }
          } catch { /* Ignore unrelated or malformed events. */ }
        };
      } catch { /* Polling and push still work if the user socket is unavailable. */ }
      await checkIncoming();
      if (active) pollTimer = setInterval(() => void checkIncoming(), 5000);
    })().catch(() => { /* Push remains available if secure token storage fails. */ });

    return () => {
      active = false;
      setFallback(null);
      disableNativeCallUI();
      if (pollTimer) clearInterval(pollTimer);
      socket?.close();
      responseSubscription.remove();
      receivedSubscription.remove();
      foregroundSubscription.remove();
      alertingCall.current = null;
    };
  }, [user]);

  return <Modal visible={!!fallback} transparent animationType="fade" onRequestClose={() => fallbackActions.current?.decline()}>
    <View style={{ flex: 1, justifyContent: 'center', backgroundColor: '#0009', padding: 24 }}>
      <View style={{ backgroundColor: 'white', borderRadius: 16, padding: 24, gap: 16 }}>
        <Text accessibilityRole="header" style={{ fontSize: 20 }}>{fallback?.caller_name} is calling</Text>
        <Text>{fallback?.call_type === 'VIDEO' ? 'Video call' : 'Audio call'}</Text>
        <Pressable accessibilityRole="button" onPress={() => fallbackActions.current?.answer()}><Text>Answer</Text></Pressable>
        <Pressable accessibilityRole="button" onPress={() => fallbackActions.current?.decline()}><Text>Decline</Text></Pressable>
      </View>
    </View>
  </Modal>;
}
