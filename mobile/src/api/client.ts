import * as SecureStore from 'expo-secure-store';

import type { AuthResponse, RegistrationData } from '@/src/types';

const ACCESS_TOKEN_KEY = 'awinlink.access-token';
const REFRESH_TOKEN_KEY = 'awinlink.refresh-token';
const API_ORIGIN = process.env.EXPO_PUBLIC_API_URL?.replace(/\/+$/, '');

export async function mediaSource(uri: string) {
  const resolved = API_ORIGIN ? new URL(uri, `${API_ORIGIN}/`) : new URL(uri);
  // Never send account credentials to Cloudinary or another external host.
  if (API_ORIGIN && resolved.origin === new URL(API_ORIGIN).origin && resolved.pathname.startsWith('/media/')) {
    const token = await getAccessToken();
    if (token) return { uri: resolved.href, headers: { Authorization: `Bearer ${token}` } };
  }
  return { uri: resolved.href };
}

export function getWebSocketUrl(path: string) {
  if (!API_ORIGIN) {
    throw new Error('API URL is not set. Copy .env.example to .env and set EXPO_PUBLIC_API_URL.');
  }
  const origin = API_ORIGIN.replace(/^http:/i, 'ws:').replace(/^https:/i, 'wss:');
  return `${origin}/${path.replace(/^\/+/, '')}`;
}

export async function getAccessToken() {
  return SecureStore.getItemAsync(ACCESS_TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function apiUrl(path: string) {
  if (!API_ORIGIN) {
    throw new Error(
      'API URL is not set. Copy .env.example to .env and set EXPO_PUBLIC_API_URL.',
    );
  }
  return `${API_ORIGIN}/api/${path.replace(/^\/+/, '')}`;
}

async function readError(response: Response) {
  const body = (await response.json().catch(() => null)) as Record<string, unknown> | null;
  if (typeof body?.detail === 'string') return body.detail;
  if (body?.error && typeof body.error === 'object' && 'detail' in body.error && typeof body.error.detail === 'string') {
    return body.error.detail;
  }
  if (Array.isArray(body?.non_field_errors) && typeof body.non_field_errors[0] === 'string') {
    return body.non_field_errors[0];
  }
  if (body) {
    const firstFieldError = Object.entries(body).find(([, value]) => Array.isArray(value) && value.length);
    if (firstFieldError) {
      const [field, messages] = firstFieldError;
      const firstMessage = Array.isArray(messages) ? messages[0] : undefined;
      if (typeof firstMessage === 'string') return `${field}: ${firstMessage}`;
    }
  }
  return `Request failed (${response.status}).`;
}

async function refreshAccessToken() {
  const refresh = await SecureStore.getItemAsync(REFRESH_TOKEN_KEY);
  if (!refresh) return null;

  const response = await fetch(apiUrl('auth/refresh/'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  });
  if (!response.ok) {
    if (response.status === 400 || response.status === 401) {
      await clearTokens();
      return null;
    }
    throw new ApiError(await readError(response), response.status);
  }

  const data = (await response.json()) as { access?: unknown };
  if (typeof data.access !== 'string') {
    throw new Error('The token refresh response did not include an access token.');
  }
  await SecureStore.setItemAsync(ACCESS_TOKEN_KEY, data.access);
  return data.access;
}

export async function clearTokens() {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}

export async function storeTokens(access: string, refresh: string) {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, access),
    SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refresh),
  ]);
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
  authenticated?: boolean;
  retryAfterRefresh?: boolean;
};

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    body,
    authenticated = true,
    retryAfterRefresh = true,
    headers: inputHeaders,
    ...requestOptions
  } = options;

  const headers = new Headers(inputHeaders);
  if (body !== undefined && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  let accessToken = authenticated
    ? await SecureStore.getItemAsync(ACCESS_TOKEN_KEY)
    : null;
  if (authenticated && accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(apiUrl(path), {
    ...requestOptions,
    headers,
    body:
      body === undefined
        ? undefined
        : body instanceof FormData
          ? body
          : JSON.stringify(body),
  });

  if (response.status === 401 && authenticated && retryAfterRefresh) {
    accessToken = await refreshAccessToken();
    if (accessToken) {
      return apiRequest<T>(path, {
        ...options,
        headers: { ...Object.fromEntries(headers.entries()), Authorization: `Bearer ${accessToken}` },
        retryAfterRefresh: false,
      });
    }
  }

  if (!response.ok) {
    throw new ApiError(await readError(response), response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function signInRequest(username: string, password: string) {
  return apiRequest<AuthResponse>('auth/login/', {
    method: 'POST',
    authenticated: false,
    body: { username, password },
  });
}

export async function signUpRequest(data: RegistrationData) {
  return apiRequest<AuthResponse>('auth/register/', {
    method: 'POST',
    authenticated: false,
    body: data,
  });
}

export async function loadCurrentUser() {
  return apiRequest<AuthResponse['user']>('auth/me/');
}
