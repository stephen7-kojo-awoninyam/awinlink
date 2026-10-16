import { useCallback, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Certificate = { id: number; certificate_id: string; course_title: string; user_name: string; issued_at: string; pdf: string | null };
type Attempt = { id: number; quiz_title: string; score: number; total_questions: number; percentage: number; passed: boolean; attempted_at: string };

export default function LearningResultsScreen() {
  const [certificates, setCertificates] = useState<Certificate[]>([]);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { const [certs, quizAttempts] = await Promise.all([apiRequest<Certificate[]>('learning/my-certificates/'), apiRequest<Attempt[]>('learning/quiz-attempts/me/')]); setCertificates(certs); setAttempts(quizAttempts); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load learning results.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Learning results', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="YOUR PROGRESS" title="Learning results" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && !certificates.length && !attempts.length ? <EmptyState title="Results unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        <Text style={styles.section}>Certificates</Text>
        {certificates.length ? certificates.map((item) => <View key={item.id} style={styles.card}><Text style={styles.title}>{item.course_title}</Text><Text style={styles.meta}>Certificate {item.certificate_id} · {new Date(item.issued_at).toLocaleDateString()}</Text>{!!item.pdf && <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(item.pdf!)}><Text style={styles.link}>Open certificate PDF</Text></Pressable>}</View>) : <Text style={styles.meta}>Certificates will appear when issued by the learning backend.</Text>}
        <Text style={styles.section}>Quiz attempts</Text>
        {attempts.length ? attempts.map((item) => <View key={item.id} style={styles.card}><Text style={styles.title}>{item.quiz_title}</Text><Text style={styles.meta}>{item.score}/{item.total_questions} · {item.percentage}% · {item.passed ? 'Passed' : 'Not passed'}</Text><Text style={styles.meta}>{new Date(item.attempted_at).toLocaleString()}</Text></View>) : <Text style={styles.meta}>Your submitted quiz attempts will appear here.</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 6, padding: 13 }, title: { color: colors.ink, fontSize: 14, fontWeight: '800' }, meta: { color: colors.muted, fontSize: 12, lineHeight: 18 }, link: { color: colors.primary, fontSize: 12, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
