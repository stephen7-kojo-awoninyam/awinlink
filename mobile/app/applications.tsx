import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Redirect, Stack, useFocusEffect, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Application = { id: number; talent: number; talent_name: string; opportunity: number; opportunity_title: string; organization_name: string; message: string; status: string; created_at: string };

export default function ApplicationsScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<Application[]>([]);
  const [selected, setSelected] = useState<Application | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { setItems(await apiRequest<Application[]>(user?.role === 'ORGANIZATION' ? 'applications/' : 'applications/me/')); }
    catch (loadError) { setError(loadError instanceof Error ? loadError.message : 'Unable to load applications.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [user?.role]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  async function openApplication(item: Application) {
    try { setSelected(await apiRequest<Application>(`applications/${item.id}/`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to open this application.'); }
  }
  async function updateStatus(status: 'REVIEWING' | 'ACCEPTED' | 'REJECTED') {
    if (!selected || working) return;
    setWorking(true); setError('');
    try {
      const updated = await apiRequest<Application>(`applications/${selected.id}/status/`, { method: 'PATCH', body: { status } });
      setSelected(updated);
      setItems(current => current.map(item => item.id === updated.id ? updated : item));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update application status.'); }
    finally { setWorking(false); }
  }
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ATHLETE' && user.role !== 'ORGANIZATION') return <Redirect href="/(tabs)" />;
  const title = user.role === 'ORGANIZATION' ? 'Applications received' : 'My applications';
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title, headerTintColor: colors.primary, headerShadowVisible: false }} />
      <Page eyebrow={user.role === 'ORGANIZATION' ? 'RECRUITMENT' : 'YOUR OPPORTUNITIES'} title={selected ? selected.talent_name || 'Application details' : title}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
        {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
          error ? <EmptyState title="Applications unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> :
          selected ? <View style={styles.card}>
            <Pressable accessibilityRole="button" onPress={() => setSelected(null)}><Text style={styles.open}>Back to applications</Text></Pressable>
            <Text style={styles.title}>{selected.opportunity_title}</Text>
            <Text style={styles.organization}>{selected.organization_name}</Text>
            {user.role === 'ORGANIZATION' && <Text style={styles.status}>Applicant talent #{selected.talent}</Text>}
            {user.role === 'ORGANIZATION' && <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: '/talent/[id]', params: { id: String(selected.talent) } })}><Text style={styles.open}>View talent profile</Text></Pressable>}
            <Text style={styles.status}>{selected.status.replaceAll('_', ' ')}</Text>
            {!!selected.message && <Text style={styles.message}>{selected.message}</Text>}
            <Text style={styles.date}>Submitted {new Date(selected.created_at).toLocaleDateString()}</Text>
            {user.role === 'ORGANIZATION' && ['PENDING', 'REVIEWING'].includes(selected.status) && <View style={styles.actions}>
              {selected.status === 'PENDING' && <Pressable accessibilityRole="button" disabled={working} onPress={() => void updateStatus('REVIEWING')} style={styles.secondaryButton}><Text style={styles.secondaryText}>{working ? 'Saving...' : 'Mark reviewing'}</Text></Pressable>}
              <Pressable accessibilityRole="button" disabled={working} onPress={() => void updateStatus('ACCEPTED')} style={styles.statusButton}><Text style={styles.statusButtonText}>{working ? 'Saving...' : 'Accept'}</Text></Pressable>
              <Pressable accessibilityRole="button" disabled={working} onPress={() => void updateStatus('REJECTED')} style={styles.rejectButton}><Text style={styles.rejectText}>{working ? 'Saving...' : 'Reject'}</Text></Pressable>
            </View>}
          </View> : items.length === 0 ? <EmptyState title="No applications yet" message={user.role === 'ORGANIZATION' ? 'Applications for your organization’s opportunities will appear here.' : 'Applications you submit will appear here.'} /> :
          items.map((item) => (
            <Pressable accessibilityRole="button" key={item.id} onPress={() => void openApplication(item)} style={styles.card}>
              <Text style={styles.title}>{user.role === 'ORGANIZATION' ? item.talent_name || `Applicant ${item.talent}` : item.opportunity_title}</Text>
              {user.role === 'ORGANIZATION' && <Text style={styles.organization}>{item.opportunity_title}</Text>}
              {user.role === 'ATHLETE' && <Text style={styles.organization}>{item.organization_name}</Text>}
              <Text style={styles.status}>{item.status.replaceAll('_', ' ')}</Text>
              <Text style={styles.date}>Submitted {new Date(item.created_at).toLocaleDateString()}</Text>
              <Text style={styles.open}>View application</Text>
            </Pressable>
          ))
        }
      </Page>
    </>
  );
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 8, padding: 15 },
  title: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  organization: { color: colors.muted, fontSize: 12 },
  status: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'capitalize' },
  message: { color: colors.ink, fontSize: 13, lineHeight: 19 },
  date: { color: colors.muted, fontSize: 10 },
  open: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  secondaryButton: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 10, padding: 10 },
  secondaryText: { color: colors.primary, fontSize: 11, fontWeight: '800' },
  statusButton: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 10, padding: 10 },
  statusButtonText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  rejectButton: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 10, padding: 10 },
  rejectText: { color: colors.danger, fontSize: 11, fontWeight: '800' },
});
