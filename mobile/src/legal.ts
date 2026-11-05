// Keep in sync with accounts/legal.py whenever Terms text changes, including drafts.
export const TERMS_VERSION = '2026-11-04-draft-2';

export function policyUrl(path: 'terms' | 'privacy' | 'community-guidelines') {
  const origin = process.env.EXPO_PUBLIC_API_URL;
  if (!origin) throw new Error('Awinlink server URL is not configured.');
  return new URL(`/${path}/`, origin).toString();
}
