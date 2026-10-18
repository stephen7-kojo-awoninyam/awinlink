import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Opportunity = {
  id: number;
  title: string;
  description: string;
  opportunity_type: string;
  organization_name: string;
  domain_name: string;
  experience_level: string;
  work_type: string;
  location: string;
  deadline: string | null;
  skills: string[];
  active: boolean;
};
type Application = { opportunity: number };

export default function OpportunitiesScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<Opportunity[]>([]);
  const [applied, setApplied] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const opportunities = await apiRequest<Opportunity[]>('opportunities/');
      setItems(opportunities);
      if (user?.role === 'ATHLETE') {
        const applications = await apiRequest<Application[]>('applications/me/');
        setApplied(new Set(applications.map((application) => application.opportunity)));
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load opportunities.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [user?.role]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const matches = items.filter((item) =>
    [item.title, item.organization_name, item.domain_name, item.location, item.description]
      .filter(Boolean)
      .join(' ')
      .toLocaleLowerCase()
      .includes(query.trim().toLocaleLowerCase()),
  );

  async function apply() {
    if (!selected || submitting) return;
    setSubmitting(true);
    setNotice('');
    setError('');
    try {
      await apiRequest('applications/create/', {
        method: 'POST',
        body: { opportunity: selected.id, message: message.trim() },
      });
      setApplied((current) => new Set(current).add(selected.id));
      setNotice('Application submitted.');
      setMessage('');
    } catch (applyError) {
      setError(applyError instanceof Error ? applyError.message : 'Unable to submit your application.');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Page eyebrow="FIND YOUR NEXT STEP" title="Opportunities"
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary}
        onRefresh={() => { setRefreshing(true); void load(); }} />}>
      <Pressable accessibilityRole="button" onPress={() => router.push('/marketplace')} style={styles.myApplications}><Text style={styles.open}>Talent Market</Text></Pressable>
      {user?.role === 'ATHLETE' && <Pressable accessibilityRole="button" onPress={() => router.push('/applications')} style={styles.myApplications}><Text style={styles.open}>My applications</Text></Pressable>}
      <TextInput accessibilityLabel="Search opportunities" value={query} onChangeText={setQuery}
        placeholder="Search title, organization, or location" placeholderTextColor={colors.muted}
        style={styles.search} />
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
        error && items.length === 0 ? <EmptyState title="Opportunities unavailable" message={error}
          actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> :
          selected ? (
            <View style={styles.card}>
              <Pressable accessibilityRole="button" onPress={() => { setSelected(null); setError(''); setNotice(''); }}>
                <Text style={styles.back}>Back to opportunities</Text>
              </Pressable>
              <Text style={styles.title}>{selected.title}</Text>
              <Text style={styles.meta}>{selected.organization_name} | {selected.domain_name}</Text>
              <Text style={styles.meta}>{selected.opportunity_type} | {selected.experience_level} | {selected.work_type}</Text>
              {!!selected.location && <Text style={styles.meta}>{selected.location}</Text>}
              {!!selected.deadline && <Text style={styles.meta}>Apply by {selected.deadline}</Text>}
              <Text style={styles.description}>{selected.description}</Text>
              {!!selected.skills?.length && <Text style={styles.meta}>Skills: {selected.skills.join(' | ')}</Text>}
              {user?.role === 'ATHLETE' && (
                applied.has(selected.id) ? <Text style={styles.success}>You have applied.</Text> : (
                  <>
                    <TextInput accessibilityLabel="Application message" value={message} onChangeText={setMessage}
                      placeholder="Message to the organization (optional)" placeholderTextColor={colors.muted}
                      multiline style={styles.messageInput} />
                    <Pressable accessibilityRole="button" disabled={submitting} onPress={() => void apply()}
                      style={[styles.button, submitting && styles.disabled]}>
                      <Text style={styles.buttonText}>{submitting ? 'Submitting...' : 'Apply'}</Text>
                    </Pressable>
                  </>
                )
              )}
              {!!notice && <Text style={styles.success}>{notice}</Text>}
              {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
            </View>
          ) : matches.length === 0 ? <EmptyState title="No opportunities found"
            message={items.length ? 'Try a different search.' : 'Check back for new opportunities.'} /> :
            matches.map((item) => (
              <Pressable accessibilityRole="button" key={item.id} onPress={() => { setSelected(item); setNotice(''); setError(''); }}
                style={styles.card}>
                <Text style={styles.title}>{item.title}</Text>
                <Text style={styles.meta}>{item.organization_name} | {item.domain_name}</Text>
                <Text numberOfLines={3} style={styles.description}>{item.description}</Text>
                <Text style={styles.open}>View details</Text>
              </Pressable>
            ))
      }
      {user?.role !== 'ATHLETE' && <Text style={styles.meta}>Applications are available to talent accounts.</Text>}
    </Page>
  );
}

const styles = StyleSheet.create({
  myApplications: { alignSelf: "flex-end", paddingVertical: 4 },
  search: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.ink, minHeight: 48, paddingHorizontal: 13 },
  loader: { marginTop: 28 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 9, padding: 15 },
  back: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  title: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  meta: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  description: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  open: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  messageInput: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, minHeight: 84, padding: 12, textAlignVertical: 'top' },
  button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, justifyContent: 'center', minHeight: 46 },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  success: { color: colors.success, fontSize: 13, fontWeight: '700' },
  error: { color: colors.danger, fontSize: 13 },
});
