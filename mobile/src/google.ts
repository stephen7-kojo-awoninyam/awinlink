import * as WebBrowser from 'expo-web-browser';
import { apiRequest } from '@/src/api/client';
import type { AuthResponse } from '@/src/types';

export type GoogleResult = AuthResponse | { signup_required?: boolean; pending?: boolean; email?: string };
export const GOOGLE_RETURN_URL = 'awinlink://google-complete';
export type GoogleExchange = { exchange_secret: string; handoff: string };

export async function beginGoogle(link: boolean, password: string) {
  const started = await apiRequest<{ authorization_url: string; exchange_secret: string }>('auth/google/start/', {
    method: 'POST', authenticated: link, body: { link, ...(link ? { password } : {}) },
  });
  const result = await WebBrowser.openAuthSessionAsync(started.authorization_url, GOOGLE_RETURN_URL);
  if (result.type !== 'success') {
    throw new Error('Google sign-in was cancelled. You can try again.');
  }
  const returned = new URL(result.url);
  const handoff = returned.searchParams.get('handoff');
  if (`${returned.protocol}//${returned.host}${returned.pathname}` !== GOOGLE_RETURN_URL || !handoff || returned.searchParams.has('error')) {
    throw new Error('Google sign-in was cancelled. You can try again.');
  }
  return { exchange_secret: started.exchange_secret, handoff };
}

export async function exchangeGoogle(exchange: GoogleExchange, signup?: Record<string, unknown>, link = false) {
  return apiRequest<GoogleResult>('auth/google/complete/', {
    method: 'POST', authenticated: link, body: { ...exchange, ...(signup ? { signup } : {}) },
  });
}
