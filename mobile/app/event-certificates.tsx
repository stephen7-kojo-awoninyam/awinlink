import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Redirect, Stack, useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Certificate = { id: number; event_title: string; certificate_title: string; certificate_code: string; description: string; issued_at: string; verified: boolean };

export default function EventCertificatesScreen() {
  const { user } = useAuth();
  const [items, setItems] = useState<Certificate[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [verified, setVerified] = useState<Record<string, boolean>>({});
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { setItems(await apiRequest<Certificate[]>('events/my-certificates/')); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load event certificates.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ATHLETE') return <Redirect href="/(tabs)" />;

  async function verify(code: string) {
    setError('');
    try {
      const result = await apiRequest<Certificate>(`events/certificates/${encodeURIComponent(code)}/verify/`);
      setVerified((current) => ({ ...current, [code]: result.verified }));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to verify this certificate.'); }
  }

  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Event certificates', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="YOUR ACHIEVEMENTS" title="Event certificates" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && items.length === 0 ? <EmptyState title="Certificates unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : items.length === 0 ? <EmptyState title="No event certificates" message="Certificates issued for events you attended will appear here." /> : items.map((item) => <View key={item.id} style={styles.card}>
        <Text style={styles.title}>{item.certificate_title}</Text><Text style={styles.event}>{item.event_title}</Text>
        {!!item.description && <Text style={styles.description}>{item.description}</Text>}
        <Text selectable style={styles.meta}>Code: {item.certificate_code}</Text><Text style={styles.meta}>Issued {new Date(item.issued_at).toLocaleDateString()}</Text>
        <Pressable accessibilityRole="button" onPress={() => void verify(item.certificate_code)} style={styles.button}><Text style={styles.buttonText}>{verified[item.certificate_code] === undefined ? 'Verify certificate' : verified[item.certificate_code] ? 'Verified' : 'Not verified'}</Text></Pressable>
      </View>)}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 8, padding: 15 }, title: { color: colors.ink, fontSize: 15, fontWeight: '800' }, event: { color: colors.primary, fontSize: 13, fontWeight: '700' }, description: { color: colors.ink, fontSize: 13, lineHeight: 19 }, meta: { color: colors.muted, fontSize: 11 }, button: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 10, padding: 11 }, buttonText: { color: colors.primary, fontSize: 12, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
