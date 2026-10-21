import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { AuthProvider, useAuth } from '@/src/auth/AuthProvider';
import { IncomingCallListener } from '@/src/calls/IncomingCallListener';
import { LoadingScreen } from '@/src/components/LoadingScreen';

function Navigation() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <LoadingScreen />;
  return <>
    <IncomingCallListener />
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#f4f7fb' } }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="password-reset" />
      <Stack.Screen name="team-invitation" />
      <Stack.Protected guard={!user}>
        <Stack.Screen name="login" />
        <Stack.Screen name="register" />
      </Stack.Protected>
      <Stack.Protected guard={!!user}>
        <Stack.Screen name="(tabs)" />
        {['applications', 'classrooms', 'classroom/[id]', 'call/[id]', 'competition-management',
          'competition-workspace', 'competitions', 'connections', 'conversation/[id]',
          'event-certificates', 'event-management', 'events', 'learning', 'learning/[id]',
          'learning/quiz/[id]', 'learning/results', 'learning/studio', 'messages', 'onboarding',
          'organizations', 'organization-team', 'organization-rosters', 'organization-agreements', 'account-settings', 'report', 'portfolio', 'profile-edit', 'recruitment', 'shortlists', 'specialist',
          'talent/[id]'].map(name => <Stack.Screen key={name} name={name} />)}
      </Stack.Protected>
    </Stack>
  </>;
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <Navigation />
    </AuthProvider>
  );
}
