import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Shortlist = { id: number; talent_id: number; talent_name: string; talent_username: string; notes: string; starred: boolean; created_at: string };

export default function ShortlistsScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<Shortlist[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { const list = await apiRequest<Shortlist[]>('shortlists/me/'); setItems(list); setNotes(Object.fromEntries(list.map((item) => [item.id, item.notes || '']))); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load shortlists.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ORGANIZATION') return <Redirect href="/(tabs)" />;

  async function update(item: Shortlist, changes: Partial<Pick<Shortlist, 'notes' | 'starred'>>) {
    setWorkingId(item.id); setError('');
    try { const saved = await apiRequest<Shortlist>(`shortlists/${item.id}/update/`, { method: 'PATCH', body: changes }); setItems((current) => current.map((row) => row.id === saved.id ? saved : row)); setNotes((current) => ({ ...current, [saved.id]: saved.notes || '' })); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update this shortlist.'); }
    finally { setWorkingId(null); }
  }
  async function remove(item: Shortlist) {
    setWorkingId(item.id); setError('');
    try { await apiRequest(`shortlists/${item.id}/delete/`, { method: 'DELETE' }); setItems((current) => current.filter((row) => row.id !== item.id)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to remove this talent.'); }
    finally { setWorkingId(null); }
  }

  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Talent shortlist', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="ORGANIZATION WORKSPACE" title="Talent shortlist" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && items.length === 0 ? <EmptyState title="Shortlists unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : items.length === 0 ? <EmptyState title="No saved talents" message="Open a public talent profile and add it to your shortlist." actionLabel="Discover talent" onAction={() => router.navigate('/(tabs)/discover')} /> : <>
        {items.map((item) => <View key={item.id} style={styles.card}>
          <Pressable onPress={() => router.push({ pathname: '/talent/[id]', params: { id: String(item.talent_id) } })}><Text style={styles.name}>{item.talent_name || item.talent_username}</Text><Text style={styles.username}>@{item.talent_username}</Text></Pressable>
          <TextInput accessibilityLabel={`Notes for ${item.talent_name}`} multiline onChangeText={(value) => setNotes((current) => ({ ...current, [item.id]: value }))} placeholder="Private organization notes" placeholderTextColor={colors.muted} style={styles.input} value={notes[item.id] ?? ''} />
          <View style={styles.actions}>
            <Pressable disabled={workingId !== null} onPress={() => void update(item, { notes: notes[item.id] ?? '' })} style={styles.action}><Text style={styles.actionText}>Save notes</Text></Pressable>
            <Pressable disabled={workingId !== null} onPress={() => void update(item, { starred: !item.starred })} style={styles.action}><Text style={styles.actionText}>{item.starred ? 'Unstar' : 'Star'}</Text></Pressable>
            <Pressable disabled={workingId !== null} onPress={() => void remove(item)} style={styles.remove}><Text style={styles.removeText}>Remove</Text></Pressable>
          </View>
        </View>)}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 9, padding: 13 }, name: { color: colors.ink, fontSize: 14, fontWeight: '800' }, username: { color: colors.primary, fontSize: 11 }, input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minHeight: 62, padding: 10, textAlignVertical: 'top' }, actions: { flexDirection: 'row', gap: 7 }, action: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 9, flex: 1, padding: 9 }, actionText: { color: colors.primary, fontSize: 10, fontWeight: '800' }, remove: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 9, flex: 1, padding: 9 }, removeText: { color: colors.danger, fontSize: 10, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
