const events = new Set([
  'ice_configuration', 'inbound_media', 'selected_ice_pair', 'playback_blocked',
  'signal_sent', 'signal_received', 'remote_track', 'ice_state', 'ice_error',
  'signaling_error', 'local_tracks',
]);
const safeValues: Record<string, Set<string>> = {
  type: new Set(['ready', 'offer', 'answer', 'ice_candidate', 'ice-candidate']),
  policy: new Set(['all', 'relay']),
  kind: new Set(['audio', 'video']),
  localType: new Set(['host', 'srflx', 'prflx', 'relay']),
  remoteType: new Set(['host', 'srflx', 'prflx', 'relay']),
  state: new Set(['new', 'checking', 'connected', 'completed', 'disconnected', 'failed', 'closed']),
  media: new Set(['AUDIO', 'VIDEO']),
  name: new Set(['Error', 'TypeError', 'OperationError', 'NotAllowedError', 'AbortError', 'InvalidStateError']),
};
const safeNumbers = new Set(['bytesReceived', 'packetsLost', 'framesDecoded', 'code', 'count']);
const safeBooleans = new Set(['relayConfigured']);

/** Keep development diagnostics useful without retaining call, account, or peer IDs. */
export function safeCallDiagnostic(event: string, detail: Record<string, unknown> = {}, at = Date.now()) {
  if (!events.has(event)) return null;
  const safe: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(detail)) {
    if (safeValues[key]?.has(String(value))) safe[key] = String(value);
    else if (safeNumbers.has(key) && typeof value === 'number' && Number.isFinite(value) && value >= 0) safe[key] = value;
    else if (safeBooleans.has(key) && typeof value === 'boolean') safe[key] = value;
  }
  return { at, event, ...safe };
}
