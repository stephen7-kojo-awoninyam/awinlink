import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text } from 'react-native';
import { Redirect, useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Competition = { id: number; title: string; status: string; review_note?: string };

const NEXT_ACTION: Record<string, { action: string; label: string }> = {
  DRAFT: { action: 'submit', label: 'Submit for approval' },
  REJECTED: { action: 'return_to_draft', label: 'Return to draft' },
  APPROVED: { action: 'publish', label: 'Publish' },
  PUBLISHED: { action: 'close_registration', label: 'Close registration' },
  REGISTRATION_CLOSED: { action: 'start', label: 'Start competition' },
  ONGOING: { action: 'start_judging', label: 'Start judging' },
  JUDGING: { action: 'publish_results', label: 'Publish results' },
  RESULTS: { action: 'complete', label: 'Complete competition' },
};

export default function CompetitionManagementScreen() {
  const { user } = useAuth();
  const [items, setItems] = useState<Competition[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState<number | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { setItems(await apiRequest<Competition[]>('competitions/my/created/')); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load your competitions.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ORGANIZATION') return <Redirect href="/(tabs)" />;

  async function transition(item: Competition, action: string) {
    setWorking(item.id); setError('');
    try {
      const updated = await apiRequest<Competition>(`competitions/${item.id}/action/`, { method: 'POST', body: { action } });
      setItems(current => current.map(value => value.id === updated.id ? updated : value));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update competition status.'); }
    finally { setWorking(null); }
  }

  return <Page eyebrow="ORGANIZATION WORKSPACE" title="My competitions" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
    {loading ? <ActivityIndicator color={colors.primary} /> : error && items.length === 0 ? <EmptyState title="Competitions unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : items.length === 0 ? <EmptyState title="No competitions yet" message="Create a competition from the Create tab. Drafts will appear here." /> : items.map(item => {
      const next = NEXT_ACTION[item.status];
      return <Pressable key={item.id} style={styles.card}>
        <Text style={styles.title}>{item.title}</Text>
        <Text style={styles.status}>{item.status.replaceAll('_', ' ')}</Text>
        {!!item.review_note && <Text style={styles.note}>Review: {item.review_note}</Text>}
        {next && <Pressable accessibilityRole="button" disabled={working !== null} onPress={() => void transition(item, next.action)} style={styles.button}><Text style={styles.buttonText}>{working === item.id ? 'Updating...' : next.label}</Text></Pressable>}
      </Pressable>;
    })}
    {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
  </Page>;
}

const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 9, padding: 15 }, title: { color: colors.ink, fontSize: 15, fontWeight: '800' }, status: { color: colors.muted, fontSize: 12 }, note: { color: colors.muted, fontSize: 12 }, button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 11, padding: 12 }, buttonText: { color: '#fff', fontSize: 12, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
