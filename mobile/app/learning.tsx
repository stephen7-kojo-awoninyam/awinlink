import { useScopedState } from '@/src/privacy-state';
import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useRef } from 'react';
import { ActivityIndicator, Image, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';
import { learningStyles as ui, learningColors as palette } from '@/src/learning-theme';

type Course = { id: number; title: string; description: string; creator_name: string; category_name: string; thumbnail: string | null; level: string; duration: number; is_free: boolean; lesson_count: number; enrollment_count: number; average_rating: number };
type Enrollment = { id: number; course: number; course_title: string; lesson_count: number; completed_lessons: number; progress_percentage: number; completed: boolean };

export default function LearningScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const scope = `${user?.id}:${user?.role}`;
  const [courses, setCourses] = useScopedState<Course[]>(scope, []);
  const [enrollments, setEnrollments] = useScopedState<Enrollment[]>(scope, []);
  const [loading, setLoading] = useScopedState(scope, true);
  const [refreshing, setRefreshing] = useScopedState(scope, false);
  const [error, setError] = useScopedState(scope, '');
  const operation = useRef(0);
  const load = useCallback(async () => {
    const request = ++operation.current;
    setError('');
    try { const [list, mine] = await Promise.all([apiRequest<Course[]>('learning/courses/'), apiRequest<Enrollment[]>('learning/my-enrollments/')]); if (request !== operation.current) return; setCourses(list); setEnrollments(mine); }
    catch (e) { if (request === operation.current) setError(e instanceof Error ? e.message : 'Unable to load learning.'); }
    finally { if (request === operation.current) { setLoading(false); setRefreshing(false); } }
  }, [scope]);
  useFocusEffect(useCallback(() => { void load(); return () => { operation.current++; }; }, [load]));
  const enrolled = new Set(enrollments.map((item) => item.course));
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Learning', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="GROW YOUR SKILLS" title="Learning" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && courses.length === 0 && enrollments.length === 0 ? <EmptyState title="Learning unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        <View style={ui.hero}>
          <Text style={ui.eyebrow}>YOUR NEXT CHAPTER STARTS HERE</Text>
          <Text accessibilityRole="header" style={ui.heroTitle}>Build your skills.{"\n"}<Text style={ui.accent}>Shape what comes next.</Text></Text>
          <Text style={ui.body}>Learn at your pace, put new ideas into practice, and grow alongside your community.</Text>
          <View style={ui.row}>
            {['ATHLETE', 'ORGANIZATION', 'SCOUT', 'COACH', 'ADMIN'].includes(user?.role || '') && <Pressable accessibilityRole="button" onPress={() => router.push('/learning/studio')} style={[ui.button, ui.secondary]}><Text style={ui.secondaryText}>Create and manage courses</Text></Pressable>}
            <Pressable accessibilityRole="link" onPress={() => router.push('/learning/results')} style={[ui.button, ui.secondary]}><Text style={ui.secondaryText}>Certificates & quiz attempts</Text></Pressable>
          </View>
        </View>
        <View style={ui.sectionHeader}><Text style={ui.eyebrow}>PICK UP WHERE YOU LEFT OFF</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Continue Learning</Text></View>
        {enrollments.length === 0 ? <View style={ui.card}><Text style={ui.cardTitle}>Your next skill starts here</Text><Text style={ui.body}>Explore a course to begin. Your progress will be waiting here when you return.</Text></View> : enrollments.map(item => <Pressable accessibilityRole="button" accessibilityLabel={`${item.completed ? 'View' : 'Continue'} ${item.course_title}, ${item.completed_lessons} of ${item.lesson_count} lessons, ${item.progress_percentage}% complete`} key={item.id} onPress={() => router.push({ pathname: '/learning/[id]', params: { id: String(item.course) } })} style={[ui.card, styles.continueCard]}>
          <Text style={ui.badge}>{item.completed ? 'COMPLETED' : 'IN PROGRESS'}</Text><Text style={ui.cardTitle}>{item.course_title}</Text><Text style={ui.body}>{item.completed_lessons} of {item.lesson_count} lessons ? {item.progress_percentage}% complete</Text>
          <View accessibilityRole="progressbar" accessibilityLabel={`${item.course_title} progress`} accessibilityValue={{ min: 0, max: 100, now: Math.max(0, Math.min(100, item.progress_percentage)) }} style={ui.track}><View style={[ui.fill, { width: `${Math.max(0, Math.min(100, item.progress_percentage))}%` }]} /></View>
          <Text style={styles.courseLink}>{item.completed ? 'View course' : 'Continue learning'} ?</Text>
        </Pressable>)}
        <LoadMore items={enrollments} onChange={setEnrollments} label="Load more enrollments" />
        <View style={styles.liveCard}><Text style={ui.eyebrow}>BETTER TOGETHER</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Live sessions</Text><Text style={ui.body}>Explore your classrooms and find sessions with your learning community.</Text><Pressable accessibilityRole="button" onPress={() => router.push('/classrooms')} style={[ui.button, ui.secondary]}><Text style={ui.secondaryText}>View live classrooms ?</Text></Pressable></View>
        <View style={ui.sectionHeader}><Text style={ui.eyebrow}>MAKE ROOM FOR SOMETHING NEW</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Explore Courses</Text><Text style={ui.body}>Fresh perspectives. Practical skills. Your next step.</Text></View>
        <View style={styles.courseGrid}>
        {courses.length === 0 ? <EmptyState title="No courses available" message="Approved learning courses will appear here." /> : courses.map(course => <Pressable accessibilityRole="button" accessibilityLabel={`Explore ${course.title}`} key={course.id} onPress={() => router.push({ pathname: '/learning/[id]', params: { id: String(course.id) } })} style={styles.courseCard}>
          {course.thumbnail ? <Image accessibilityIgnoresInvertColors source={{ uri: course.thumbnail }} style={styles.thumbnail} /> : <View style={[styles.thumbnail, styles.thumbnailFallback]}><Text style={styles.thumbnailKicker}>AWINLINK LEARNING</Text><Text style={styles.thumbnailInitial}>{course.category_name || 'A new perspective'}</Text><Text style={styles.thumbnailCaption}>Learn something. Become more.</Text></View>}
          <View style={styles.courseBody}><View style={ui.row}><Text style={ui.badge}>{course.level.toLowerCase()}</Text>{course.is_free && <Text style={styles.freeBadge}>Free course</Text>}{enrolled.has(course.id) && <Text style={ui.badge}>ENROLLED</Text>}</View><Text style={ui.cardTitle}>{course.title}</Text><Text style={ui.body}>By {course.creator_name}</Text><Text numberOfLines={2} style={ui.body}>{course.description}</Text><Text style={styles.courseMeta}>{course.lesson_count} lessons ? {course.duration} min{course.average_rating > 0 ? ` ? ${course.average_rating.toFixed(1)} / 5` : ''}</Text><Text style={styles.courseLink}>Explore course ?</Text></View>
        </Pressable>)}
        </View>
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}

      <LoadMore items={courses} onChange={setCourses} label="Load more courses" />
    </Page>
  </>;
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  continueCard: { borderTopWidth: 3, borderTopColor: palette.blue },
  liveCard: { backgroundColor: '#f5f9ff', borderColor: '#d8e6fb', borderWidth: 1, borderRadius: 16, padding: 22, gap: 12 },
  courseGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 18 },
  courseCard: { backgroundColor: palette.white, borderColor: palette.line, borderWidth: 1, borderRadius: 16, overflow: 'hidden', flexBasis: 280, flexGrow: 1, flexShrink: 1, minWidth: 0, maxWidth: '100%' },
  thumbnail: { width: '100%', height: 160, backgroundColor: '#e4eeff' },
  thumbnailFallback: { padding: 22, gap: 12, justifyContent: 'center', backgroundColor: '#0752b6' },
  thumbnailKicker: { color: '#d8e9ff', fontSize: 10, fontWeight: '800', letterSpacing: 1.5 },
  thumbnailInitial: { color: '#fff', fontSize: 25, lineHeight: 31, fontWeight: '800' },
  thumbnailCaption: { color: '#d8e9ff', fontSize: 12 },
  courseBody: { padding: 20, gap: 12 },
  freeBadge: { color: '#22603c', fontSize: 11, fontWeight: '800' },
  courseMeta: { color: palette.muted, fontSize: 12, lineHeight: 19 },
  courseLink: { color: palette.blue, fontSize: 14, fontWeight: '800', paddingVertical: 6 },
  error: { color: colors.danger, fontSize: 13, lineHeight: 20 },
});
