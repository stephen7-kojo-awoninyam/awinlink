import { refreshSocketAccessToken } from './client';

export const socketAccessToken = refreshSocketAccessToken;

// Renew in place before the five-minute access token expires, preserving active
// calls without reconnecting their signaling socket or acquiring media again.
export function maintainSocketAuthentication(socket: WebSocket) {
  let stopped = false;
  let refreshing = false;
  let firstFrameSeen = false;
  let supported = false;
  // Older call servers relay arbitrary messages. Never send a credential until
  // the initial server handshake explicitly advertises secure renewal support.
  socket.addEventListener('message', event => {
    if (firstFrameSeen) return;
    firstFrameSeen = true;
    try {
      const message = JSON.parse(String(event.data));
      supported = ['connection', 'user_connection'].includes(message.type) && message.reauthentication === true;
    } catch { supported = false; }
  });
  const stop = () => { stopped = true; clearInterval(timer); };
  const timer = setInterval(async () => {
    if (socket.readyState >= 2) { stop(); return; }
    if (stopped || refreshing || !supported || socket.readyState !== 1) return;
    refreshing = true;
    try {
      const access = await refreshSocketAccessToken();
      if (!stopped && socket.readyState === 1) socket.send(JSON.stringify({ type: 'reauthenticate', access }));
    } catch {
      if (!stopped) socket.close();
      stop();
    } finally { refreshing = false; }
  }, 240_000);
  socket.addEventListener('close', stop);
  return stop;
}
