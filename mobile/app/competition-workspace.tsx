import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Assignment = { id: number; competition: number; coach: number; coach_name: string; role: 'MENTOR' | 'EVALUATOR' | 'JUDGE'; assigned_at: string };
type Competition = { id: number; title: string; status: string; organization_name: string };
type Participant = { id: number; competition: number; competition_title: string; talent: { id: number; name: string; category: string }; status: string; submission: string; submission_url: string; submitted_at: string | null };
type EvaluationDraft = { score: string; feedback: string };

export default function CompetitionWorkspaceScreen() {
  const { user } = useAuth();
  const isAdmin = user?.role === 'ADMIN';
  const isCoach = user?.role === 'COACH';
  const [assignments, setAssignments] = useState<Assignment[]>([]);
  const [queue, setQueue] = useState<Competition[]>([]);
  const [selected, setSelected] = useState<Competition | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [drafts, setDrafts] = useState<Record<number, EvaluationDraft>>({});
  const [reviewNote, setReviewNote] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try {
      if (isCoach) setAssignments(await apiRequest<Assignment[]>('competitions/judging/'));
      else setQueue(await apiRequest<Competition[]>('competitions/moderation/'));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load competition work.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [isCoach]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  if (!user) return <Redirect href="/login" />;
  if (!isAdmin && !isCoach) return <Redirect href="/(tabs)" />;

  async function openAssignment(assignment: Assignment) {
    setWorkingId(assignment.id); setError('');
    try {
      const [competition, entries] = await Promise.all([
        apiRequest<Competition>(`competitions/${assignment.competition}/`),
        apiRequest<Participant[]>(`competitions/${assignment.competition}/participants/`),
      ]);
      setSelected(competition); setParticipants(entries); setDrafts({});
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load assigned participants.'); }
    finally { setWorkingId(null); }
  }

  async function saveEvaluation(participant: Participant, assignment: Assignment) {
    const draft = drafts[participant.id] || { score: '', feedback: '' };
    setWorkingId(participant.id); setError('');
    try {
      await apiRequest(`competitions/${assignment.competition}/participants/${participant.id}/evaluate/`, {
        method: 'PUT',
        body: assignment.role === 'MENTOR' ? { feedback: draft.feedback.trim() } : { score: draft.score, feedback: draft.feedback.trim() },
      });
      setError('Evaluation saved.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save evaluation.'); }
    finally { setWorkingId(null); }
  }

  async function reviewCompetition(competition: Competition, action: 'approve' | 'reject') {
    setWorkingId(competition.id); setError('');
    try {
      await apiRequest(`competitions/moderation/${competition.id}/`, { method: 'POST', body: { action, review_note: reviewNote[competition.id] || '' } });
      setQueue((current) => current.filter((item) => item.id !== competition.id));
    } catch (e) { setError(e instanceof Error ? e.message : `Unable to ${action} this competition.`); }
    finally { setWorkingId(null); }
  }

  const assignmentForSelected = assignments.find((item) => item.competition === selected?.id);
  const canEvaluate = assignmentForSelected && ((assignmentForSelected.role === 'MENTOR' && selected?.status === 'ONGOING') || (assignmentForSelected.role !== 'MENTOR' && selected?.status === 'JUDGING'));

  return <>
    <Stack.Screen options={{ headerShown: true, title: isAdmin ? 'Competition moderation' : 'Judging assignments', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow={isAdmin ? 'ADMIN WORKSPACE' : 'COACH WORKSPACE'} title={selected ? selected.title : isAdmin ? 'Competition moderation' : 'Judging assignments'} refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {selected && isCoach ? <>
        <Pressable onPress={() => setSelected(null)}><Text style={styles.back}>Back to assignments</Text></Pressable>
        <Text style={styles.meta}>Status: {selected.status.toLowerCase().replaceAll('_', ' ')}</Text>
        {!canEvaluate && <Text style={styles.info}>The backend accepts feedback for this assignment only during its active stage.</Text>}
        {participants.length === 0 ? <EmptyState title="No participants yet" message="Registered participants will appear here." /> : participants.map((participant) => {
          const draft = drafts[participant.id] || { score: '', feedback: '' };
          return <View key={participant.id} style={styles.card}>
            <Text style={styles.person}>{participant.talent.name}</Text>
            <Text style={styles.meta}>{participant.talent.category}</Text>
            {!!participant.submission && <Text style={styles.submission}>{participant.submission}</Text>}
            {!!participant.submission_url && <Text style={styles.submission}>{participant.submission_url}</Text>}
            {assignmentForSelected?.role !== 'MENTOR' && <TextInput accessibilityLabel={`Score for ${participant.talent.name}`} keyboardType="decimal-pad" onChangeText={(score) => setDrafts((current) => ({ ...current, [participant.id]: { ...draft, score } }))} placeholder="Score (0–100)" placeholderTextColor={colors.muted} style={styles.input} value={draft.score} />}
            <TextInput accessibilityLabel={`Feedback for ${participant.talent.name}`} multiline onChangeText={(feedback) => setDrafts((current) => ({ ...current, [participant.id]: { ...draft, feedback } }))} placeholder={assignmentForSelected?.role === 'MENTOR' ? 'Mentoring feedback' : 'Feedback'} placeholderTextColor={colors.muted} style={styles.input} value={draft.feedback} />
            <Pressable disabled={!canEvaluate || workingId !== null} onPress={() => assignmentForSelected && void saveEvaluation(participant, assignmentForSelected)} style={[styles.button, (!canEvaluate || workingId !== null) && styles.disabled]}><Text style={styles.buttonText}>{workingId === participant.id ? 'Saving...' : 'Save evaluation'}</Text></Pressable>
          </View>;
        })}
      </> : loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && (isAdmin ? queue.length === 0 : assignments.length === 0) ? <EmptyState title="Competition workspace unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : isAdmin ? queue.length === 0 ? <EmptyState title="Nothing to review" message="Competitions submitted for approval will appear here." /> : queue.map((competition) => <View key={competition.id} style={styles.card}>
        <Text style={styles.person}>{competition.title}</Text><Text style={styles.meta}>{competition.organization_name} · Submitted</Text>
        <TextInput accessibilityLabel={`Review note for ${competition.title}`} multiline onChangeText={(value) => setReviewNote((current) => ({ ...current, [competition.id]: value }))} placeholder="Review note" placeholderTextColor={colors.muted} style={styles.input} value={reviewNote[competition.id] || ''} />
        <View style={styles.row}><Pressable disabled={workingId !== null} onPress={() => void reviewCompetition(competition, 'approve')} style={styles.button}><Text style={styles.buttonText}>{workingId === competition.id ? 'Working...' : 'Approve'}</Text></Pressable><Pressable disabled={workingId !== null} onPress={() => void reviewCompetition(competition, 'reject')} style={styles.reject}><Text style={styles.rejectText}>Request changes</Text></Pressable></View>
      </View>) : assignments.length === 0 ? <EmptyState title="No judging assignments" message="When an organization assigns you to judge or mentor a competition, it will appear here." /> : assignments.map((assignment) => <Pressable key={assignment.id} disabled={workingId !== null} onPress={() => void openAssignment(assignment)} style={styles.card}><Text style={styles.person}>Competition #{assignment.competition}</Text><Text style={styles.meta}>{assignment.role.toLowerCase()} assignment</Text><Text style={styles.open}>{workingId === assignment.id ? 'Loading...' : 'Open assignment'}</Text></Pressable>)}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, back: { color: colors.primary, fontSize: 12, fontWeight: '800' }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 9, padding: 13 }, person: { color: colors.ink, fontSize: 14, fontWeight: '800' }, meta: { color: colors.muted, fontSize: 11, lineHeight: 17 }, info: { backgroundColor: colors.softBlue, borderRadius: 10, color: colors.primary, fontSize: 11, lineHeight: 17, padding: 10 }, submission: { color: colors.ink, fontSize: 12, lineHeight: 17 }, input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minHeight: 44, padding: 10, textAlignVertical: 'top' }, button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 10, flex: 1, padding: 11 }, buttonText: { color: '#fff', fontSize: 11, fontWeight: '800' }, row: { flexDirection: 'row', gap: 8 }, reject: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 10, flex: 1, padding: 11 }, rejectText: { color: colors.danger, fontSize: 11, fontWeight: '800' }, open: { color: colors.primary, fontSize: 12, fontWeight: '800' }, disabled: { opacity: 0.55 }, error: { color: colors.danger, fontSize: 12 } });
