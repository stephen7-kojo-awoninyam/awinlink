import { useScopedState } from '@/src/privacy-state';
import { useAuth } from '@/src/auth/AuthProvider';
import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useRef } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect, useRouter } from 'expo-router';

import { downloadMedia } from '@/src/media-download';
import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Certificate = { id: number; course_id: number; certificate_id: string; course_title: string; user_name: string; issued_at: string; pdf: string | null };
type Attempt = { id: number; quiz_title: string; lesson_id: number; passing_score: number; score: number; total_questions: number; percentage: number; passed: boolean; attempted_at: string };

export default function LearningResultsScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const scope = `${user?.id}:${user?.role}`;
  const [certificates, setCertificates] = useScopedState<Certificate[]>(scope, []);
  const [attempts, setAttempts] = useScopedState<Attempt[]>(scope, []);
  const [loading, setLoading] = useScopedState(scope, true);
  const [refreshing, setRefreshing] = useScopedState(scope, false);
  const [error, setError] = useScopedState(scope, '');
  const operation = useRef(0);
  const load = useCallback(async () => {
    const request = ++operation.current;
    setError('');
    const [certs, quizAttempts] = await Promise.allSettled([apiRequest<Certificate[]>('learning/my-certificates/'), apiRequest<Attempt[]>('learning/quiz-attempts/me/')]);
    if (request !== operation.current) return;
    setCertificates(certs.status === 'fulfilled' ? certs.value : []);
    setAttempts(quizAttempts.status === 'fulfilled' ? quizAttempts.value : []);
    if (certs.status === 'rejected' || quizAttempts.status === 'rejected') setError('Some learning results could not be loaded. Refresh to retry.');
    setLoading(false); setRefreshing(false);
  }, [scope]);
  useFocusEffect(useCallback(() => { void load(); return () => { operation.current++; }; }, [load]));
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Learning results', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="YOUR PROGRESS" title="Learning results" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && !certificates.length && !attempts.length ? <EmptyState title="Results unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        <Text style={styles.section}>Certificates</Text>
        {certificates.length ? certificates.map((item) => <View key={item.id} style={styles.card}><Text style={styles.title}>{item.course_title}</Text><Text style={styles.meta}>Certificate {item.certificate_id} · {new Date(item.issued_at).toLocaleDateString()}</Text>{!item.pdf && <><Text style={styles.meta}>Certificate issued; PDF generation is pending. Return to the completed course to retry.</Text>{!!item.course_id && <Pressable accessibilityRole="link" onPress={() => router.push({ pathname: '/learning/[id]', params: { id: String(item.course_id) } })}><Text style={styles.link}>Return to course</Text></Pressable>}</>}{!!item.pdf && <Pressable accessibilityRole="link" onPress={() => void downloadMedia(item.pdf!).catch(() => setError('Unable to download this certificate.'))}><Text style={styles.link}>Open certificate PDF</Text></Pressable>}</View>) : <Text style={styles.meta}>Certificates will appear when issued by the learning backend.</Text>}
        <Text style={styles.section}>Quiz attempts</Text>
        {attempts.length ? attempts.map((item) => <View key={item.id} style={styles.card}><Text accessibilityRole="header" style={styles.title}>{item.quiz_title}</Text><Text style={styles.meta}>{item.score}/{item.total_questions} · {item.percentage}% · {item.passed ? 'Passed' : `Not passed · ${item.passing_score}% needed`}</Text><Text style={styles.meta}>{new Date(item.attempted_at).toLocaleString()}</Text>{!item.passed && !!item.lesson_id && <Pressable accessibilityRole="button" accessibilityLabel={`Retry ${item.quiz_title}`} onPress={() => router.push({ pathname: '/learning/quiz/[id]', params: { id: String(item.lesson_id) } })}><Text style={styles.link}>Try quiz again</Text></Pressable>}</View>) : <Text style={styles.meta}>Your submitted quiz attempts will appear here.</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}

      <LoadMore items={certificates} onChange={setCertificates} label="Load more certificates" />
      <LoadMore items={attempts} onChange={setAttempts} label="Load more attempts" />
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 6, padding: 13 }, title: { color: colors.ink, fontSize: 14, fontWeight: '800' }, meta: { color: colors.muted, fontSize: 12, lineHeight: 18 }, link: { color: colors.primary, fontSize: 12, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
