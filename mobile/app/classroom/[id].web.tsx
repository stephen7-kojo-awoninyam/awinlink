import { Linking, Pressable, StyleSheet, Text } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { getWebSocketUrl } from '@/src/api/client';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

export default function BrowserClassroom() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const valid = Number.isSafeInteger(Number(id)) && Number(id) > 0;
  return <><Stack.Screen options={{ headerShown: true, title: 'Browser classroom' }} /><Page title="Open your browser classroom">
    <Text>Use Awinlink’s browser classroom for camera, microphone, screen sharing, chat and the shared whiteboard. Sign in with your existing browser account if prompted.</Text>
    <Pressable accessibilityRole="link" disabled={!valid} style={styles.button} onPress={() => void Linking.openURL(getWebSocketUrl(`learning/sessions/${Number(id)}/classroom/`).replace(/^ws:/, 'http:').replace(/^wss:/, 'https:'))}><Text style={styles.label}>Open classroom</Text></Pressable>
  </Page></>;
}
const styles = StyleSheet.create({ button: { backgroundColor: colors.primary, padding: 14, borderRadius: 12 }, label: { color: '#fff', fontWeight: '700' } });
