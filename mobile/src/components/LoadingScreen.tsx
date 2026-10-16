import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/src/theme';

export function LoadingScreen() {
  return (
    <View style={styles.container}>
      <ActivityIndicator color={colors.primary} size="large" />
      <Text style={styles.label}>Connecting to Awinlink…</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    backgroundColor: colors.background,
    flex: 1,
    gap: 14,
    justifyContent: 'center',
  },
  label: { color: colors.muted, fontSize: 14, fontWeight: '600' },
});
