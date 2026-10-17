// Reversible UUIDs allow native answer/end events to identify a call before JS has its payload.
const PREFIX = 'a7100000-0000-4000-8000-';
export function callUUID(id: number): string {
  if (!Number.isSafeInteger(id) || id < 1 || id > 0xffffffffffff) throw new Error('Invalid native call ID.');
  return `${PREFIX}${id.toString(16).padStart(12, '0')}`;
}
export function callID(uuid: string): number | null {
  const value = String(uuid).toLowerCase();
  if (!value.startsWith(PREFIX) || !/^[0-9a-f]{12}$/.test(value.slice(PREFIX.length))) return null;
  const id = Number.parseInt(value.slice(PREFIX.length), 16);
  return id > 0 ? id : null;
}
