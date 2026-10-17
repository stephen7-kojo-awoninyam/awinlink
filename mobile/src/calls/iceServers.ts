export type CallIceServer = {
  urls: string | string[];
  username?: string;
  credential?: string;
};

const DEFAULT_STUN: CallIceServer = { urls: 'stun:stun.l.google.com:19302' };

export function validatedIceServers(value: unknown): CallIceServer[] {
  if (!Array.isArray(value) || value.length === 0) return [DEFAULT_STUN];
  const servers = value.filter(
    (server): server is CallIceServer =>
      typeof server === 'object' &&
      server !== null &&
      'urls' in server &&
      ((typeof server.urls === 'string' && /^(stun|stuns|turn|turns):/.test(server.urls)) ||
        (Array.isArray(server.urls) && server.urls.length > 0 && server.urls.every((url: unknown) => typeof url === 'string' && /^(stun|stuns|turn|turns):/.test(url)))),
  );
  return servers.length ? servers : [DEFAULT_STUN];
}
