// Keep in sync with accounts/legal.py when legally reviewed Terms change.
export const TERMS_VERSION = '2026-10-18-draft-1';

export function policyUrl(path: 'terms' | 'privacy' | 'community-guidelines') {
  const origin = process.env.EXPO_PUBLIC_API_URL;
  if (!origin) throw new Error('Awinlink server URL is not configured.');
  return new URL(`/${path}/`, origin).toString();
}
