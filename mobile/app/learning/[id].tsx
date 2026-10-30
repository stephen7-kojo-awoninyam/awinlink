import { useScopedState } from '@/src/privacy-state';
import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useEffect, useRef } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';

import { ApiError, apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';
import { learningStyles as ui, learningColors as palette } from '@/src/learning-theme';
import { useAuth } from '@/src/auth/AuthProvider';

type Course = { id: number; creator: number; title: string; description: string; creator_name: string; category_name: string; level: string; duration: number; is_free: boolean; lesson_count: number; status?: string };
type Lesson = { id: number; title: string; description: string; notes: string | null; video: string | null; module?: number | null; order: number; duration: number; is_locked?: boolean };
type CourseModule = { id: number; title: string; description: string; order: number };
type LearningSession = { id: number; classroom: number; classroom_title: string; lesson: number; lesson_title: string; module: number | null; module_title: string | null; title: string; status: 'SCHEDULED' | 'LIVE'; scheduled_start: string | null };
type SessionPage = { results: LearningSession[]; next: string | null };
type Progress = { progress_percentage: number; completed_lessons: number; total_lessons: number; completed: boolean; completed_lesson_ids?: number[] };
type Review = { id: number; user: number; user_name: string; rating: number; review: string; created_at: string };
type LessonQuiz = { id: number; title: string; passing_score: number; question_count: number };
type QuizAvailability = 'available' | 'none' | 'unknown';

export default function CourseScreen() {
  const { id: routeId } = useLocalSearchParams<{ id: string }>();
  const id = Number(routeId);
  const router = useRouter();
  const { user } = useAuth();
  const scope = `${user?.id}:${user?.role}:${id}`;
  const [course, setCourse] = useScopedState<Course | null>(scope, null);
  const [lessons, setLessons] = useScopedState<Lesson[]>(scope, []);
  const [modules, setModules] = useScopedState<CourseModule[]>(scope, []);
  const [liveSessions, setLiveSessions] = useScopedState<LearningSession[]>(scope, []);
  const [classroomNotice, setClassroomNotice] = useScopedState(scope, '');
  const [progress, setProgress] = useScopedState<Progress | null>(scope, null);
  const [completedLessonIds, setCompletedLessonIds] = useScopedState<Set<number>>(scope, () => new Set());
  const [quizAvailability, setQuizAvailability] = useScopedState<Record<number, QuizAvailability>>(scope, {});
  const [quizRefresh, setQuizRefresh] = useScopedState(scope, 0);
  const [reviews, setReviews] = useScopedState<Review[]>(scope, []);
  const [reviewDraft, setReviewDraft] = useScopedState(scope, '');
  const [rating, setRating] = useScopedState(scope, 5);
  const [loading, setLoading] = useScopedState(scope, true);
  const [working, setWorking] = useScopedState(scope, false);
  const [error, setError] = useScopedState(scope, '');
  const [refreshing, setRefreshing] = useScopedState(scope, false);
  const operation = useRef(0);
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const load = useCallback(async () => {
    if (currentScope.current !== scope) return;
    if (!Number.isInteger(id) || id < 1) { setError('This course link is invalid.'); setLoading(false); return; }
    const request = ++operation.current;
    setError('');
    setClassroomNotice('');
    let optionalNotice = '';
    try {
      const info = await apiRequest<Course>(`learning/courses/${id}/`);
      const [lessonList, courseProgress, moduleList, sessionPage] = await Promise.all([
        apiRequest<Lesson[]>(`learning/courses/${id}/lessons/`),
        apiRequest<Progress>(`learning/courses/${id}/progress/`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }),
        apiRequest<CourseModule[]>(`learning/courses/${id}/modules/`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return [];
          optionalNotice = 'Course sections are temporarily unavailable.';
          return [];
        }),
        apiRequest<SessionPage>(`learning/courses/${id}/live-sessions/?page_size=100`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return { results: [], next: null };
          optionalNotice = 'Live classroom information is temporarily unavailable.';
          return { results: [], next: null };
        }),
      ]);
      if (request !== operation.current) return;
      setClassroomNotice(optionalNotice);
      setCourse(info); setLessons(lessonList); setModules(moduleList); setLiveSessions(sessionPage.results); setProgress(courseProgress);
      setCompletedLessonIds(new Set(courseProgress?.completed_lesson_ids || []));
      setQuizAvailability({});
      setQuizRefresh(current => current + 1);
      try {
        const reviewList = await apiRequest<Review[]>(`learning/courses/${id}/reviews/`);
        if (request === operation.current) setReviews(reviewList);
      } catch {
        if (request === operation.current) setError('Unable to load course reviews. Refresh to retry.');
      }
    } catch (e) {
      if (request === operation.current) {
        // Failed authorization/refresh must not leave stale media or enrollment controls.
        setCourse(null); setLessons([]); setModules([]); setLiveSessions([]); setProgress(null); setReviews([]); setQuizAvailability({});
        setError(e instanceof Error ? e.message : 'Unable to load this course.');
      }
    } finally { if (request === operation.current) { setLoading(false); setRefreshing(false); } }
  }, [id, scope]);
  useFocusEffect(useCallback(() => { void load(); return () => { operation.current++; }; }, [load]));
  useEffect(() => {
    let active = true;
    if (!progress) return;
    // Includes lessons merged by LoadMore, without treating an unchecked quiz as absent.
    void Promise.all(lessons.filter(lesson => !quizAvailability[lesson.id]).map(async lesson => {
      let availability: QuizAvailability;
      try { await apiRequest<LessonQuiz>(`learning/lessons/${lesson.id}/quiz/`); availability = 'available'; }
      catch (e) { availability = e instanceof ApiError && e.status === 404 ? 'none' : 'unknown'; }
      if (active) setQuizAvailability(current => ({ ...current, [lesson.id]: availability }));
    }));
    return () => { active = false; };
  }, [lessons, progress, scope, quizRefresh]);
  async function enroll() {
    setWorking(true); setError('');
    try { await apiRequest(`learning/courses/${id}/enroll/`, { method: 'POST' }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to enroll in this course.'); }
    finally { setWorking(false); }
  }
  async function markComplete(lesson: Lesson) {
    if (working) return;
    setWorking(true); setError('');
    try { await apiRequest(`learning/lessons/${lesson.id}/progress/`, { method: 'POST', body: { completed: true } }); await load(); }
    catch (e) {
      // PDF generation can fail after durable progress is saved. Reconcile first,
      // then retain the actionable server error instead of hiding it in refresh.
      await load(); setError(e instanceof Error ? e.message : 'Unable to update lesson progress.');
    }
    finally { setWorking(false); }
  }
  async function submitReview() {
    setWorking(true); setError('');
    try { const review = await apiRequest<Review>(`learning/courses/${id}/reviews/`, { method: 'POST', body: { rating, review: reviewDraft.trim() } }); setReviews((current) => [review, ...current]); setReviewDraft(''); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to submit course review.'); }
    finally { setWorking(false); }
  }
  const isLocked = (lesson: Lesson) => lesson.is_locked ?? (!!course && !course.is_free && !progress && course.creator !== user?.id && user?.role !== 'ADMIN');
  const creatorPreview = !!course && course.creator === user?.id && course.status !== 'APPROVED';
  const curriculumGroups = modules.length ? [
    ...modules.map(module => ({ id: module.id, title: module.title, lessons: lessons.filter(lesson => lesson.module === module.id) })).filter(group => group.lessons.length),
    { id: 0, title: 'Other lessons', lessons: lessons.filter(lesson => !lesson.module || !modules.some(module => module.id === lesson.module)) },
  ].filter(group => group.lessons.length) : [{ id: 0, title: '', lessons }];
  return <>
    <Stack.Screen options={{ headerShown: true, title: course?.title || 'Course', headerTintColor: palette.blue, headerShadowVisible: false }} />
    <Page eyebrow="AWINLINK LEARNING" title="Course details" refreshControl={<RefreshControl refreshing={refreshing} tintColor={palette.blue} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={palette.blue} style={styles.loader} /> : error && !course ? <EmptyState title="Course unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : course ? <>
        <View style={ui.hero}>
          <Text style={ui.eyebrow}>{course.category_name} / {course.level.toLowerCase()}</Text>
          <Text accessibilityRole="header" style={ui.heroTitle}>{course.title}</Text>
          <Text style={ui.body}>Learn with {course.creator_name}</Text>
          <View style={ui.row}><Text style={ui.badge}>{course.lesson_count} lessons</Text><Text style={ui.badge}>{course.duration} minutes</Text><Text style={ui.badge}>{course.level.toLowerCase()}</Text>{course.is_free && <Text style={ui.badge}>Free course</Text>}</View>
        </View>
        <View style={[ui.card, styles.enrollCard]}>
          <Text style={ui.eyebrow}>{creatorPreview ? 'LEARNER PREVIEW' : progress ? 'YOUR LEARNING JOURNEY' : 'MAKE TIME FOR YOUR TALENT'}</Text>
          <Text style={ui.cardTitle}>{creatorPreview ? 'Preview learner access' : progress ? progress.completed ? 'Course completed' : 'Keep your momentum' : 'Your next skill starts here'}</Text>
          {creatorPreview && <><Text style={ui.body}>Preview this course and its lessons without enrolling or changing learner progress.</Text><Pressable accessibilityRole="link" onPress={() => router.push('/learning/studio')} style={styles.lessonAction}><Text style={styles.lessonActionText}>Return to Creator Studio</Text></Pressable></>}
          {progress ? <>
            <Text style={ui.body}>{progress.progress_percentage}% complete ({progress.completed_lessons}/{progress.total_lessons} lessons)</Text>
            <View accessibilityRole="progressbar" accessibilityLabel="Course progress" accessibilityValue={{ min: 0, max: 100, now: Math.max(0, Math.min(100, progress.progress_percentage)) }} style={ui.track}><View style={[ui.fill, { width: `${Math.max(0, Math.min(100, progress.progress_percentage))}%` }]} /></View>
          </> : !creatorPreview && <><Text style={ui.body}>Enroll to track your progress, complete lessons and take included quizzes.</Text><Pressable accessibilityRole="button" accessibilityState={{ disabled: working || !course.is_free }} disabled={working || !course.is_free} onPress={() => void enroll()} style={[ui.button, (working || !course.is_free) && styles.disabled]}><Text style={ui.buttonText}>{working ? 'Working...' : course.is_free ? 'Enroll in course' : 'Paid enrollment unavailable'}</Text></Pressable></>}
          {progress && (progress.completed || (progress.total_lessons > 0 && progress.completed_lessons >= progress.total_lessons)) && <View style={styles.lessonActions}>
            <Pressable accessibilityRole="link" onPress={() => router.push('/learning/results')} style={styles.lessonAction}><Text style={styles.lessonActionText}>View certificates and quiz attempts</Text></Pressable>
            {!!lessons.length && <Pressable accessibilityRole="button" disabled={working} onPress={() => void markComplete(lessons[0])} style={[styles.lessonAction, working && styles.disabled]}><Text style={styles.lessonActionText}>{working ? 'Working...' : progress.completed ? 'Retry certificate generation' : 'Refresh course completion'}</Text></Pressable>}
          </View>}
        </View>
        <View style={ui.sectionHeader}><Text style={ui.eyebrow}>A NEW PERSPECTIVE STARTS HERE</Text><Text accessibilityRole="header" style={ui.sectionTitle}>About this course</Text></View>
        <Text style={ui.body}>{course.description}</Text>
        <View style={ui.sectionHeader}><Text style={ui.eyebrow}>STEP BY STEP, AT YOUR PACE</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Course curriculum</Text><Text style={ui.body}>{course.lesson_count} lessons ? {course.duration} minutes{!progress ? ' ? Enroll to track your lesson progress.' : ''}</Text></View>
        {lessons.length === 0 && <EmptyState title="Lessons are being prepared" message="Check back soon for course materials." />}
        {curriculumGroups.map(group => <View key={`module-${group.id}`}>
        {!!group.title && <Text accessibilityRole="header" style={ui.cardTitle}>{group.title}</Text>}
        {group.lessons.map((lesson, index) => <View key={lesson.id} style={ui.card}>
          <View style={styles.lessonHeading}><Text style={styles.lessonNumber}>{String(index + 1).padStart(2, '0')}</Text><View style={ui.copy}><Text accessibilityRole="header" style={ui.cardTitle}>{lesson.title}</Text><Text style={ui.body}>{lesson.duration} min{completedLessonIds.has(lesson.id) || progress?.completed ? ' ? Completed' : ''}</Text></View></View>
          {!!lesson.description && <Text style={ui.body}>{lesson.description}</Text>}
          {liveSessions.filter(session => session.lesson === lesson.id).map(session => <View key={`session-${session.id}`} style={styles.sessionCard}>
            <Text accessibilityRole="header" style={styles.sessionTitle}>{session.title}</Text>
            <Text style={ui.body}>{session.status === 'LIVE' ? 'Live now' : 'Scheduled'} · {session.classroom_title}{session.scheduled_start ? ` · ${new Date(session.scheduled_start).toLocaleString()}` : ''}</Text>
            {!!session.module_title && <Text style={ui.body}>Section: {session.module_title}</Text>}
            <Pressable accessibilityRole="link" accessibilityLabel={`${session.status === 'LIVE' ? 'Open live' : 'View scheduled'} classroom session ${session.title}`} onPress={() => router.push({ pathname: '/classroom/[id]', params: { id: String(session.id) } })} style={styles.sessionAction}><Text style={styles.sessionActionText}>{session.status === 'LIVE' ? 'Open live classroom' : 'View session'}</Text></Pressable>
          </View>)}
          {isLocked(lesson) && <View style={styles.lockedNotice}><Text style={styles.lockedTitle}>Locked lesson preview</Text><Text style={ui.body}>Enrollment is required to open videos and notes.</Text></View>}
          {!isLocked(lesson) && <Pressable accessibilityRole="link" accessibilityLabel={`Open lesson ${lesson.order}: ${lesson.title}`} onPress={() => router.push({ pathname: '/learning/lesson/[id]', params: { id: String(lesson.id) } })} style={styles.lessonAction}><Text style={styles.lessonActionText}>Open lesson workspace</Text></Pressable>}
          {progress && <View style={styles.lessonActions}>
            <Pressable accessibilityRole="button" disabled={working || completedLessonIds.has(lesson.id) || progress.completed} onPress={() => void markComplete(lesson)} style={[styles.lessonAction, (working || completedLessonIds.has(lesson.id) || progress.completed) && styles.disabled]}><Text style={styles.lessonActionText}>{completedLessonIds.has(lesson.id) || progress.completed ? 'Completed' : 'Mark lesson complete'}</Text></Pressable>
            {quizAvailability[lesson.id] === 'available' ? <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: '/learning/quiz/[id]', params: { id: String(lesson.id) } })} style={styles.lessonAction}><Text style={styles.lessonActionText}>Open quiz</Text></Pressable> : quizAvailability[lesson.id] === 'none' ? <Text style={ui.body}>No quiz for this lesson.</Text> : quizAvailability[lesson.id] === 'unknown' ? <Text style={ui.body}>Quiz availability could not be checked. Refresh to retry.</Text> : <Text style={ui.body}>Checking quiz availability...</Text>}
          </View>}
        </View>)}</View>)}
        {course.creator === user?.id && <Pressable accessibilityRole="link" onPress={() => router.push({ pathname: '/classrooms', params: { courseId: String(course.id) } })} style={styles.manageSessions}><Text style={styles.sessionActionText}>Manage this course’s live classrooms</Text></Pressable>}
        <LoadMore items={lessons} onChange={setLessons} label="Load more lessons" />
        <View style={ui.sectionHeader}><Text style={ui.eyebrow}>LEARN FROM YOUR COMMUNITY</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Meet your instructor</Text></View>
        <View style={ui.card}><View style={ui.row}><View style={ui.avatar} accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants"><Text style={ui.avatarText}>{(course.creator_name || 'A').charAt(0).toUpperCase()}</Text></View><View style={ui.copy}><Text style={ui.cardTitle}>{course.creator_name}</Text><Text style={ui.body}>Course creator ? {course.category_name}</Text></View></View></View>
        <View style={styles.liveCard}><Text style={ui.eyebrow}>LEARNING TOGETHER</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Live sessions</Text><Text style={ui.body}>Find your classrooms and explore available sessions.</Text><Pressable accessibilityRole="button" onPress={() => router.push('/classrooms')} style={[ui.button, ui.secondary]}><Text style={ui.secondaryText}>View live classrooms ?</Text></Pressable></View>
        {!!classroomNotice && <Text accessibilityRole="alert" style={styles.error}>{classroomNotice} Refresh to retry.</Text>}
        <View style={ui.sectionHeader}><Text style={ui.eyebrow}>LEARNING, IN THEIR WORDS</Text><Text accessibilityRole="header" style={ui.sectionTitle}>Learner reviews</Text></View>
        {!!progress && !reviews.some(review => review.user === user?.id) && <View style={ui.card}>
          <Text style={ui.cardTitle}>Share your experience</Text><Text style={ui.body}>Your rating: {rating} / 5</Text>
          <View accessibilityRole="radiogroup" accessibilityLabel="Course rating" style={styles.lessonActions}>{[1, 2, 3, 4, 5].map(value => <Pressable accessibilityRole="radio" accessibilityLabel={`${value} of 5 stars`} accessibilityState={{ checked: rating === value }} key={value} onPress={() => setRating(value)} style={[styles.lessonAction, rating === value && styles.selectedRating]}><Text style={styles.lessonActionText}>{value} ?</Text></Pressable>)}</View>
          <TextInput accessibilityLabel="Course review" multiline onChangeText={setReviewDraft} placeholder="Share your course review" placeholderTextColor={palette.muted} style={styles.reviewInput} value={reviewDraft} />
          <Pressable accessibilityRole="button" disabled={working || !reviewDraft.trim()} onPress={() => void submitReview()} style={[ui.button, (working || !reviewDraft.trim()) && styles.disabled]}><Text style={ui.buttonText}>{working ? 'Submitting...' : 'Submit review'}</Text></Pressable>
        </View>}
        {reviews.length ? reviews.map(review => <View key={review.id} style={ui.card}><Text style={ui.cardTitle}>{review.user_name}</Text><Text accessibilityLabel={`Rated ${review.rating} out of 5`} style={ui.badge}>{review.rating} / 5</Text><Text style={ui.body}>{review.review}</Text></View>) : <Text style={ui.body}>No reviews yet. Share your experience after enrolling.</Text>}
        <LoadMore items={reviews} onChange={setReviews} label="Load more reviews" />
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </> : null}
    </Page>
  </>;
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  sessionCard: { backgroundColor: '#f5f9ff', borderColor: palette.line, borderWidth: 1, borderRadius: 10, padding: 12, gap: 7, marginTop: 10 },
  sessionTitle: { color: palette.ink, fontSize: 14, fontWeight: '800' },
  sessionAction: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center', backgroundColor: palette.pale, borderRadius: 8, paddingHorizontal: 14 },
  sessionActionText: { color: palette.blue, fontSize: 13, fontWeight: '800' },
  manageSessions: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start', paddingHorizontal: 8 },
  enrollCard: { borderTopWidth: 4, borderTopColor: palette.blue },
  lessonHeading: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  lessonNumber: { color: palette.blue, backgroundColor: palette.pale, borderRadius: 8, padding: 10, fontSize: 13, fontWeight: '800', overflow: 'hidden' },
  lessonActions: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  lessonAction: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start', backgroundColor: palette.pale, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 12 },
  lessonActionText: { color: palette.blue, fontSize: 13, fontWeight: '800' },
  lockedNotice: { backgroundColor: '#f4f7fb', borderColor: palette.line, borderWidth: 1, padding: 14, borderRadius: 10, gap: 5 },
  lockedTitle: { color: palette.ink, fontSize: 13, fontWeight: '800' },
  selectedRating: { borderColor: palette.blue, borderWidth: 2 },
  reviewInput: { backgroundColor: '#fbfcfe', borderColor: palette.line, borderRadius: 10, borderWidth: 1, color: palette.ink, minHeight: 90, padding: 14, fontSize: 16, textAlignVertical: 'top' },
  liveCard: { backgroundColor: '#f5f9ff', borderColor: '#d8e6fb', borderWidth: 1, borderRadius: 16, padding: 22, gap: 12 },
  disabled: { opacity: 0.55 },
  error: { color: colors.danger, fontSize: 13, lineHeight: 20 },
});
