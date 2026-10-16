import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type PipelineEntry = { id: number; talent_id: number; talent_name: string; talent_username: string; opportunity_id: number; opportunity_title: string; stage: string; stage_display: string; notes: string };
type Opportunity = { id: number; organization: number; title: string; active: boolean };
type Organization = { id: number };
const STAGES = ['SHORTLISTED', 'INVITED', 'INTERVIEW', 'SELECTED', 'REJECTED'] as const;

export default function RecruitmentScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ talentId?: string }>();
  const talentId = Number(params.talentId);
  const adding = Number.isInteger(talentId) && talentId > 0;
  const [pipeline, setPipeline] = useState<PipelineEntry[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try {
      const [list, org, available] = await Promise.all([
        apiRequest<PipelineEntry[]>('recruitment/pipeline/'),
        apiRequest<Organization>('organizations/me/'),
        apiRequest<Opportunity[]>('opportunities/'),
      ]);
      setPipeline(list); setNotes(Object.fromEntries(list.map((item) => [item.id, item.notes || ''])));
      setOpportunities(available.filter((item) => item.active && item.organization === org.id));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load recruitment.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ORGANIZATION') return <Redirect href="/(tabs)" />;

  async function addToPipeline(opportunity: Opportunity) {
    setWorkingId(opportunity.id); setError('');
    try {
      await apiRequest('recruitment/create/', { method: 'POST', body: { talent: talentId, opportunity: opportunity.id, stage: 'SHORTLISTED' } });
      router.replace('/recruitment');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to add this talent.'); }
    finally { setWorkingId(null); }
  }
  async function update(item: PipelineEntry, changes: Partial<Pick<PipelineEntry, 'stage' | 'notes'>>) {
    setWorkingId(item.id); setError('');
    try { const saved = await apiRequest<PipelineEntry>(`recruitment/${item.id}/update/`, { method: 'PATCH', body: changes }); setPipeline((current) => current.map((row) => row.id === saved.id ? saved : row)); setNotes((current) => ({ ...current, [saved.id]: saved.notes || '' })); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update this pipeline record.'); }
    finally { setWorkingId(null); }
  }
  async function remove(item: PipelineEntry) {
    setWorkingId(item.id); setError('');
    try { await apiRequest(`recruitment/${item.id}/delete/`, { method: 'DELETE' }); setPipeline((current) => current.filter((row) => row.id !== item.id)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to remove this record.'); }
    finally { setWorkingId(null); }
  }

  return <>
    <Stack.Screen options={{ headerShown: true, title: adding ? 'Add to recruitment' : 'Recruitment pipeline', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="ORGANIZATION WORKSPACE" title={adding ? 'Add to recruitment' : 'Recruitment pipeline'} refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && (adding ? opportunities.length === 0 : pipeline.length === 0) ? <EmptyState title="Recruitment unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : adding ? <>
        <Text style={styles.intro}>Choose one of your active opportunities. Django checks opportunity ownership and prevents duplicate pipeline entries.</Text>
        {opportunities.length === 0 ? <EmptyState title="No active opportunities" message="Create or activate an opportunity before adding talent to its pipeline." /> : opportunities.map((opportunity) => <Pressable key={opportunity.id} disabled={workingId !== null} onPress={() => void addToPipeline(opportunity)} style={styles.opportunity}><Text style={styles.opportunityTitle}>{opportunity.title}</Text><Text style={styles.actionText}>{workingId === opportunity.id ? 'Adding...' : 'Add talent'}</Text></Pressable>)}
      </> : pipeline.length === 0 ? <EmptyState title="Pipeline is empty" message="Add a talent from their profile to an active opportunity pipeline." actionLabel="Discover talent" onAction={() => router.navigate('/(tabs)/discover')} /> : <>
        {pipeline.map((item) => <View key={item.id} style={styles.card}>
          <Pressable onPress={() => router.push({ pathname: '/talent/[id]', params: { id: String(item.talent_id) } })}><Text style={styles.name}>{item.talent_name || item.talent_username}</Text><Text style={styles.meta}>@{item.talent_username} · {item.opportunity_title}</Text></Pressable>
          <Text style={styles.meta}>Current stage: {item.stage_display || item.stage}</Text>
          <View style={styles.stageRow}>{STAGES.map((stage) => <Pressable key={stage} disabled={workingId !== null || stage === item.stage} onPress={() => void update(item, { stage })} style={[styles.stage, stage === item.stage && styles.stageSelected]}><Text style={[styles.stageText, stage === item.stage && styles.stageTextSelected]}>{stage.toLowerCase()}</Text></Pressable>)}</View>
          <TextInput accessibilityLabel={`Recruitment notes for ${item.talent_name}`} multiline onChangeText={(value) => setNotes((current) => ({ ...current, [item.id]: value }))} placeholder="Private recruitment notes" placeholderTextColor={colors.muted} style={styles.input} value={notes[item.id] ?? ''} />
          <View style={styles.stageRow}><Pressable disabled={workingId !== null} onPress={() => void update(item, { notes: notes[item.id] ?? '' })} style={styles.action}><Text style={styles.actionText}>Save notes</Text></Pressable><Pressable disabled={workingId !== null} onPress={() => void remove(item)} style={styles.remove}><Text style={styles.removeText}>Remove</Text></Pressable></View>
        </View>)}
      </>}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, intro: { color: colors.muted, fontSize: 12, lineHeight: 18 }, opportunity: { alignItems: 'center', backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 13, borderWidth: 1, flexDirection: 'row', justifyContent: 'space-between', padding: 14 }, opportunityTitle: { color: colors.ink, flex: 1, fontSize: 13, fontWeight: '800' }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 9, padding: 13 }, name: { color: colors.ink, fontSize: 14, fontWeight: '800' }, meta: { color: colors.muted, fontSize: 11 }, stageRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 }, stage: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 8, borderWidth: 1, paddingHorizontal: 8, paddingVertical: 7 }, stageSelected: { backgroundColor: colors.softBlue, borderColor: colors.primary }, stageText: { color: colors.muted, fontSize: 9, fontWeight: '700', textTransform: 'capitalize' }, stageTextSelected: { color: colors.primary }, input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minHeight: 58, padding: 10, textAlignVertical: 'top' }, action: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 9, flex: 1, padding: 9 }, actionText: { color: colors.primary, fontSize: 10, fontWeight: '800' }, remove: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 9, flex: 1, padding: 9 }, removeText: { color: colors.danger, fontSize: 10, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
