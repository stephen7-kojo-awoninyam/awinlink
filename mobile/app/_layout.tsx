import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { AuthProvider } from '@/src/auth/AuthProvider';
import { IncomingCallListener } from '@/src/calls/IncomingCallListener';

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <IncomingCallListener />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#f4f7fb' } }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="login" />
        <Stack.Screen name="(tabs)" />
      </Stack>
    </AuthProvider>
  );
}
