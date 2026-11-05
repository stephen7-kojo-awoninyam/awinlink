import { useEffect, useRef, useState } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import { apiRequest, getWebSocketUrl } from '@/src/api/client';
import { socketAccessToken, maintainSocketAuthentication } from '@/src/api/socketAuthentication';
import { useAuth } from '@/src/auth/AuthProvider';
import { callHasEnded, notifyCallEnded } from './callLifecycle';

type Incoming = { id: number; call_type: string; conversation: number; initiated_by: { username: string } };
export function IncomingCallListener() {
  const { user } = useAuth();
  const routed = useRef(new Set<number>());
  const [call, setCall] = useState<Incoming | null>(null);
  useEffect(() => {
    if (!user) return;
    routed.current.clear();
    let active = true, polling = false, queuedCheck = false;
    let socket: WebSocket | undefined;
    const check = async () => {
      if (polling) { queuedCheck = true; return; }
      polling = true;
      try {
        const incoming = await apiRequest<Incoming[]>('messaging/calls/incoming/');
        if (active) setCall(incoming.find(item => !routed.current.has(item.id) && !callHasEnded(item.id)) || null);
      } catch { /* Keep the socket and polling fallback available. */ }
      finally {
        polling = false;
        if (active && queuedCheck) { queuedCheck = false; void check(); }
      }
    };
    void check();
    const timer = setInterval(() => void check(), 5000);
    void socketAccessToken().then(token => {
      if (!active || !token) return;
      socket = new WebSocket(getWebSocketUrl('ws/user/'), ['bearer', token]);
      maintainSocketAuthentication(socket);
      socket.onmessage = event => {
        try {
          const message = JSON.parse(String(event.data));
          if (message.type === 'call_ended') {
            const id = Number(message.call_id);
            notifyCallEnded(id);
            setCall(current => current?.id === id ? null : current);
          }
          if (['incoming_call', 'call_ended'].includes(message.type)) void check();
        } catch { /* Ignore unrelated messages. */ }
      };
    }).catch(() => {});
    return () => { active = false; clearInterval(timer); socket?.close(); setCall(null); };
  }, [user]);
  async function decline() {
    if (!call) return;
    try { await apiRequest(`messaging/calls/${call.id}/reject/`, { method: 'POST' }); setCall(null); } catch { /* Retry remains available. */ }
  }
  return <Modal visible={!!call} transparent onRequestClose={() => void decline()}>
    <View style={{ flex: 1, justifyContent: 'center', backgroundColor: '#0009', padding: 24 }}>
      <View style={{ backgroundColor: 'white', borderRadius: 16, padding: 24, gap: 16 }}>
        <Text accessibilityRole="header">{call?.initiated_by?.username} is calling</Text>
        <Pressable accessibilityRole="button" style={{ minHeight: 48, padding: 12 }} onPress={() => {
          if (!call) return;
          routed.current.add(call.id);
          router.push({ pathname: '/call/[id]', params: { id: String(call.id), mode: 'incoming', callType: call.call_type, title: call.initiated_by?.username, autoAccept: 'true' } });
          setCall(null);
        }}><Text>Answer</Text></Pressable>
        <Pressable accessibilityRole="button" style={{ minHeight: 48, padding: 12 }} onPress={() => void decline()}><Text>Decline</Text></Pressable>
      </View>
    </View>
  </Modal>;
}
