import { Stack } from 'expo-router';

import { DirectoryScreen } from '@/src/components/DirectoryScreen';
import { colors } from '@/src/theme';

export default function EventsRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Events', headerTintColor: colors.primary, headerStyle: { backgroundColor: colors.background }, headerShadowVisible: false }} />
      <DirectoryScreen kind="events" />
    </>
  );
}
