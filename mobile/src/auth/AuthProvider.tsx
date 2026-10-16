import * as SecureStore from 'expo-secure-store';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type PropsWithChildren,
} from 'react';

import {
  ApiError,
  apiRequest,
  clearTokens,
  loadCurrentUser,
  signInRequest,
  signUpRequest,
  storeTokens,
} from '@/src/api/client';
import type { RegistrationData, User } from '@/src/types';

const USER_KEY = 'awinlink.user';

type AuthContextValue = {
  user: User | null;
  isLoading: boolean;
  sessionError: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (data: RegistrationData) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function isUser(value: unknown): value is User {
  return (
    typeof value === 'object' &&
    value !== null &&
    'id' in value &&
    typeof value.id === 'number' &&
    'username' in value &&
    typeof value.username === 'string'
  );
}

export function AuthProvider({ children }: PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionError, setSessionError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function restoreSession() {
      try {
        const access = await SecureStore.getItemAsync('awinlink.access-token');
        if (!access) return;
        try {
          const currentUser = await loadCurrentUser();
          if (active) {
            setUser(currentUser);
            await SecureStore.setItemAsync(USER_KEY, JSON.stringify(currentUser));
          }
        } catch (restoreError) {
          if (restoreError instanceof ApiError && restoreError.status === 401) {
            await clearTokens();
            await SecureStore.deleteItemAsync(USER_KEY);
            return;
          }

          const cachedUser = await SecureStore.getItemAsync(USER_KEY);
          if (cachedUser) {
            const parsedUser: unknown = JSON.parse(cachedUser);
            if (isUser(parsedUser) && active) setUser(parsedUser);
          }
        }
      } catch (restoreError) {
        if (active) {
          setSessionError(
            restoreError instanceof Error
              ? restoreError.message
              : 'Unable to restore your saved session.',
          );
        }
      } finally {
        if (active) setIsLoading(false);
      }
    }
    void restoreSession();
    return () => {
      active = false;
    };
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const response = await signInRequest(username, password);
    await storeTokens(response.access, response.refresh);
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(response.user));
    setUser(response.user);
    setSessionError(null);
  }, []);

  const signUp = useCallback(async (data: RegistrationData) => {
    const response = await signUpRequest(data);
    await storeTokens(response.access, response.refresh);
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(response.user));
    setUser(response.user);
    setSessionError(null);
  }, []);

  const signOut = useCallback(async () => {
    const pushToken = await SecureStore.getItemAsync('awinlink.push-token');
    if (pushToken) {
      try {
        await apiRequest('notifications/mobile-push/', {
          method: 'DELETE',
          body: { token: pushToken },
        });
      } catch {
        // Signing out should still complete if the device is offline.
      }
      await SecureStore.deleteItemAsync('awinlink.push-token');
    }
    await clearTokens();
    await SecureStore.deleteItemAsync(USER_KEY);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, isLoading, sessionError, signIn, signUp, signOut }),
    [user, isLoading, sessionError, signIn, signUp, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider.');
  }
  return context;
}
