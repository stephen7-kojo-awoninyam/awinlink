import { useCallback, useState } from 'react';
import { ActivityIndicator, Image, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Course = { id: number; title: string; description: string; creator_name: string; category_name: string; thumbnail: string | null; level: string; duration: number; is_free: boolean; lesson_count: number; enrollment_count: number; average_rating: number };
type Enrollment = { id: number; course: number; course_title: string; lesson_count: number; completed_lessons: number; progress_percentage: number; completed: boolean };

export default function LearningScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [courses, setCourses] = useState<Course[]>([]);
  const [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try { const [list, mine] = await Promise.all([apiRequest<Course[]>('learning/courses/'), apiRequest<Enrollment[]>('learning/my-enrollments/')]); setCourses(list); setEnrollments(mine); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load learning.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  const enrolled = new Set(enrollments.map((item) => item.course));
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Learning', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="GROW YOUR SKILLS" title="Learning" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && courses.length === 0 ? <EmptyState title="Learning unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
      <Text style={styles.section}>My learning</Text>
        <Pressable onPress={() => router.push('/classrooms')} style={styles.resultsButton}><Text style={styles.resultsText}>Live classrooms</Text></Pressable>
        {['ATHLETE', 'ORGANIZATION', 'COACH', 'ADMIN'].includes(user?.role || '') && <Pressable onPress={() => router.push('/learning/studio')} style={styles.resultsButton}><Text style={styles.resultsText}>Create and manage courses</Text></Pressable>}
        <Pressable onPress={() => router.push('/learning/results')} style={styles.resultsButton}><Text style={styles.resultsText}>View certificates and quiz attempts</Text></Pressable>
        {enrollments.length === 0 ? <Text style={styles.hint}>Courses you enroll in will show progress here.</Text> : enrollments.map((item) => <Pressable key={item.id} onPress={() => router.push({ pathname: '/learning/[id]', params: { id: String(item.course) } })} style={styles.progressCard}><Text style={styles.title}>{item.course_title}</Text><Text style={styles.hint}>{item.completed_lessons} of {item.lesson_count} lessons · {item.progress_percentage}% complete</Text><View style={styles.track}><View style={[styles.fill, { width: `${Math.min(100, item.progress_percentage)}%` }]} /></View></Pressable>)}
        <Text style={styles.section}>Explore courses</Text>
        {courses.length === 0 ? <EmptyState title="No courses available" message="Approved learning courses will appear here." /> : courses.map((course) => <Pressable key={course.id} onPress={() => router.push({ pathname: '/learning/[id]', params: { id: String(course.id) } })} style={styles.courseCard}>{course.thumbnail ? <Image source={{ uri: course.thumbnail }} style={styles.thumbnail} /> : <View style={[styles.thumbnail, styles.thumbnailFallback]}><Text style={styles.thumbnailInitial}>{course.title.charAt(0)}</Text></View>}<View style={styles.copy}><Text style={styles.title}>{course.title}</Text><Text style={styles.hint}>{course.category_name} · {course.level.toLowerCase()} · {course.lesson_count} lessons</Text><Text numberOfLines={2} style={styles.description}>{course.description}</Text>{enrolled.has(course.id) && <Text style={styles.enrolled}>ENROLLED</Text>}</View></Pressable>)}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, resultsButton: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 11, padding: 11 }, resultsText: { color: colors.primary, fontSize: 12, fontWeight: '800' }, hint: { color: colors.muted, fontSize: 12, lineHeight: 18 }, progressCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 8, padding: 14 }, track: { backgroundColor: colors.softBlue, borderRadius: 5, height: 7, overflow: 'hidden' }, fill: { backgroundColor: colors.primary, height: 7 }, courseCard: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, flexDirection: 'row', gap: 12, padding: 12 }, thumbnail: { backgroundColor: colors.softBlue, borderRadius: 12, height: 78, width: 78 }, thumbnailFallback: { alignItems: 'center', justifyContent: 'center' }, thumbnailInitial: { color: colors.primary, fontSize: 24, fontWeight: '800' }, copy: { flex: 1, gap: 4 }, title: { color: colors.ink, fontSize: 14, fontWeight: '800' }, description: { color: colors.ink, fontSize: 12, lineHeight: 17 }, enrolled: { color: colors.primary, fontSize: 10, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
