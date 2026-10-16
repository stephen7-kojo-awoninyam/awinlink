import { Stack } from 'expo-router';

import { DirectoryScreen } from '@/src/components/DirectoryScreen';
import { colors } from '@/src/theme';

export default function CompetitionsRoute() {
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Competitions', headerTintColor: colors.primary, headerStyle: { backgroundColor: colors.background }, headerShadowVisible: false }} />
      <DirectoryScreen kind="competitions" />
    </>
  );
}
