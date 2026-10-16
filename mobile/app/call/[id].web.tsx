import { Pressable, StyleSheet, Text, View } from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '@/src/theme';

export default function WebCallScreen() {
  const { title } = useLocalSearchParams<{ title?: string }>();
  return (
    <SafeAreaView style={styles.safe}>
      <Stack.Screen options={{ title: 'Awinlink call', headerShown: true }} />
      <View style={styles.content}>
        <Text style={styles.title}>Native calling required</Text>
        <Text style={styles.message}>
          Audio and video calls are available in the installed Android and iOS apps.
        </Text>
        <Pressable accessibilityRole="button" onPress={() => router.back()} style={styles.button}>
          <Text style={styles.buttonText}>Return to {title || 'conversation'}</Text>
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { backgroundColor: colors.background, flex: 1 },
  content: { alignItems: 'center', flex: 1, justifyContent: 'center', padding: 28 },
  title: { color: colors.ink, fontSize: 22, fontWeight: '800', textAlign: 'center' },
  message: { color: colors.muted, fontSize: 15, lineHeight: 22, marginTop: 12, textAlign: 'center' },
  button: { backgroundColor: colors.primary, borderRadius: 18, marginTop: 22, paddingHorizontal: 18, paddingVertical: 12 },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '700' },
});
