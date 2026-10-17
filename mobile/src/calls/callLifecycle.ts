// Shared across the conversation, incoming-call listener and active call screen.
const endings = new Map<number, Promise<unknown>>();
const ended = new Set<number>();
const listeners = new Set<(id: number) => void>();

export function callHasEnded(id: number) { return ended.has(id); }
export function notifyCallEnded(id: number) {
  ended.add(id);
  if (ended.size > 100) ended.delete(ended.values().next().value!);
  listeners.forEach(listener => listener(id));
}
export function onCallEnded(listener: (id: number) => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
export function finishCallRequest(id: number, request: () => Promise<unknown>) {
  const existing = endings.get(id);
  if (existing) return existing;
  const promise = request().finally(() => { if (endings.get(id) === promise) endings.delete(id); });
  endings.set(id, promise);
  return promise;
}
export async function waitForCallEndRequests() { await Promise.all([...endings.values()]); }
