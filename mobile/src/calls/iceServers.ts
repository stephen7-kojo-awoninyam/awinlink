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
      (typeof server.urls === 'string' ||
        (Array.isArray(server.urls) && server.urls.every((url: unknown) => typeof url === 'string'))),
  );
  return servers.length ? servers : [DEFAULT_STUN];
}
