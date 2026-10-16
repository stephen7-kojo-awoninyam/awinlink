import { useEffect, useRef } from 'react';
import { Alert, Platform } from 'react-native';
import { router } from 'expo-router';
import Constants from 'expo-constants';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';

import { apiRequest, getAccessToken, getWebSocketUrl } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';

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
  } catch {
    // Calls remain available through foreground WebSockets if native push setup is unavailable.
  }
}

export function IncomingCallListener() {
  const { user } = useAuth();
  const alertingCall = useRef<number | null>(null);
  const handledCall = useRef<number | null>(null);
  const routedCalls = useRef(new Set<number>());

  useEffect(() => {
    if (!user) return;
    let active = true;
    let socket: WebSocket | undefined;
    let pollTimer: ReturnType<typeof setInterval> | undefined;

    const routeToCall = (call: IncomingCall, autoAccept = false) => {
      if (!active || routedCalls.current.has(call.id)) return;
      routedCalls.current.add(call.id);
      handledCall.current = call.id;
      alertingCall.current = null;
      router.push({ pathname: '/call/[id]', params: {
        id: String(call.id), mode: 'incoming', callType: call.call_type,
        conversationId: String(call.conversation), title: call.caller_name,
        autoAccept: autoAccept ? 'true' : 'false',
      } });
    };

    const showIncomingCall = (call: IncomingCall) => {
      if (!active || handledCall.current === call.id || alertingCall.current === call.id) return;
      alertingCall.current = call.id;
      Alert.alert(`${call.caller_name} is calling`, call.call_type === 'VIDEO' ? 'Video call' : 'Audio call', [
        { text: 'Decline', style: 'destructive', onPress: () => {
          handledCall.current = call.id;
          alertingCall.current = null;
          void apiRequest(`messaging/calls/${call.id}/reject/`, { method: 'POST' }).catch(() => {});
        } },
        { text: 'Answer', onPress: () => routeToCall(call) },
      ], { onDismiss: () => {
        if (alertingCall.current === call.id) {
          alertingCall.current = null;
          handledCall.current = call.id;
        }
      } });
    };

    const handlePushResponse = (response: Notifications.NotificationResponse) => {
      const data = response.notification.request.content.data as Record<string, unknown>;
      const call = callFromData(data);
      if (!call) return;
      if (response.actionIdentifier === 'DECLINE') {
        handledCall.current = call.id;
        void apiRequest(`messaging/calls/${call.id}/reject/`, { method: 'POST' }).catch(() => {});
      } else {
        routeToCall(call, response.actionIdentifier === 'ANSWER');
      }
    };

    const responseSubscription = Notifications.addNotificationResponseReceivedListener(handlePushResponse);
    const receivedSubscription = Notifications.addNotificationReceivedListener((notification) => {
      const call = callFromData(notification.request.content.data as Record<string, unknown>);
      if (call) showIncomingCall(call);
    });
    void Notifications.getLastNotificationResponseAsync().then((response) => {
      if (active && response) handlePushResponse(response);
    }).catch(() => {});
    void registerNativePushToken();

    const checkIncoming = async () => {
      try {
        const calls = await apiRequest<{
          id: number;
          conversation: number;
          call_type: 'VOICE' | 'VIDEO';
          initiated_by: { username: string; first_name?: string; last_name?: string };
        }[]>('messaging/calls/incoming/');
        calls.forEach((item) => {
          const callerName = [item.initiated_by.first_name, item.initiated_by.last_name]
            .filter(Boolean)
            .join(' ') || item.initiated_by.username;
          showIncomingCall({
            id: item.id,
            conversation: item.conversation,
            call_type: item.call_type,
            caller_name: callerName,
          });
        });
      } catch {
        // Push and the authenticated user WebSocket remain available during feed failures.
      }
    };

    void (async () => {
      const token = await getAccessToken();
      if (!active || !token) return;
      try {
        socket = socketWithToken(getWebSocketUrl('ws/user/'), token);
        socket.onmessage = (event) => {
          try {
            const message = JSON.parse(String(event.data)) as { type?: string; call_id?: number };
            if (message.type === 'incoming_call' && message.call_id) void checkIncoming();
          } catch { /* Ignore unrelated or malformed events. */ }
        };
      } catch { /* Polling and push still work if the user socket is unavailable. */ }
      await checkIncoming();
      pollTimer = setInterval(() => void checkIncoming(), 5000);
    })();

    return () => {
      active = false;
      if (pollTimer) clearInterval(pollTimer);
      socket?.close();
      responseSubscription.remove();
      receivedSubscription.remove();
      alertingCall.current = null;
    };
  }, [user]);

  return null;
}
