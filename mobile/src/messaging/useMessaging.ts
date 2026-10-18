import { useCallback, useRef, useState } from 'react';
import { AppState, Platform } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { getAccessToken, getWebSocketUrl } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';

// A focused inbox or conversation owns its subscription and disposes all retries.
export function useMessaging(onUpdate: () => void | Promise<void>, conversationId?: number) {
  const { user } = useAuth();
  const update = useRef(onUpdate);
  update.current = onUpdate;
  const socketRef = useRef<WebSocket | null>(null);
  const [typing, setTyping] = useState('');
  const lastSent = useRef(0);
  useFocusEffect(useCallback(() => {
    let disposed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let expiry: ReturnType<typeof setTimeout> | undefined;
    let delay = 1000;
    let connecting = false;
    const retryLater = () => {
      if (disposed || retry) return;
      retry = setTimeout(() => { retry = undefined; void connect(); }, delay + Math.random() * 300);
      delay = Math.min(delay * 2, 30000);
    };
    const isBackground = () => AppState.currentState === 'background';
    async function connect() {
      if (disposed || connecting || socketRef.current || isBackground()) return;
      connecting = true;
      try {
        await update.current();
        const token = await getAccessToken();
        if (disposed || !token || isBackground()) return;
        const Socket = WebSocket as unknown as new (url: string, protocols: string[], options?: { headers: Record<string, string> }) => WebSocket;
        const socket = new Socket(getWebSocketUrl('ws/user/'), [], Platform.OS === 'web' ? undefined : { headers: { Authorization: `Bearer ${token}` } });
        socketRef.current = socket;
        socket.onopen = () => { delay = 1000; void update.current(); };
        socket.onmessage = event => {
          if (disposed || socketRef.current !== socket) return;
          try {
            const data = JSON.parse(String(event.data));
            if (data.type === 'typing' && data.conversation_id === conversationId && data.user_id !== user?.id) {
              if (expiry) clearTimeout(expiry);
              setTyping(data.is_typing ? `${data.username} is typing...` : '');
              expiry = setTimeout(() => setTyping(''), 4000);
            }
            if ((data.type === 'message_created' || (data.type === 'messages_read' && !conversationId)) && (!conversationId || data.conversation_id === conversationId)) void update.current();
          } catch { /* Ignore unknown events. */ }
        };
        socket.onerror = () => socket.close();
        socket.onclose = () => { if (socketRef.current === socket) socketRef.current = null; setTyping(''); retryLater(); };
      } catch { retryLater(); }
      finally { connecting = false; }
    }
    void connect();
    const foreground = AppState.addEventListener('change', state => {
      if (state === 'active') { void update.current(); void connect(); }
      else { socketRef.current?.close(); }
    });
    // Catch up even when a proxy silently loses the socket.
    const fallback = setInterval(() => { if (AppState.currentState === 'active') void update.current(); }, 30000);
    return () => {
      disposed = true;
      if (retry) clearTimeout(retry);
      if (expiry) clearTimeout(expiry);
      clearInterval(fallback);
      foreground.remove();
      const socket = socketRef.current;
      socketRef.current = null;
      if (socket) { socket.onclose = null; socket.close(); }
      setTyping('');
    };
  }, [conversationId, user?.id]));
  const sendTyping = (value: string) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN || !conversationId) return;
    if (value && Date.now() - lastSent.current < 1000) return;
    lastSent.current = Date.now();
    socket.send(JSON.stringify({ type: 'typing', conversation_id: conversationId, is_typing: !!value }));
  };
  return { typing, sendTyping };
}
