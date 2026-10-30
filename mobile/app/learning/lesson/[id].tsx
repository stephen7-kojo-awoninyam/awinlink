import { useScopedState } from '@/src/privacy-state';
import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { ApiError, apiRequest } from '@/src/api/client';
import { VideoPlayer } from '@/src/components/MediaPlayer';
import { downloadMedia } from '@/src/media-download';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { useAuth } from '@/src/auth/AuthProvider';
import { learningStyles as ui, learningColors as palette } from '@/src/learning-theme';

type Lesson = { id: number; course: number; course_title: string; module?: number | null; module_title?: string | null; title: string; description: string; video: string | null; notes: string | null; captions: string | null; caption_language: string; transcript: string; order: number; duration: number };
type Course = { id: number; title: string; lesson_count: number };
type CourseModule = { id: number; title: string; order: number };
type LearningSession = { id: number; classroom_title: string; lesson: number; module_title: string | null; title: string; status: 'SCHEDULED' | 'LIVE'; scheduled_start: string | null };
type SessionPage = { results: LearningSession[]; next: string | null };
type Progress = { progress_percentage: number; completed_lessons: number; total_lessons: number; completed_lesson_ids?: number[] };
type Quiz = { id: number; title: string; passing_score: number };
type Attempt = { quiz: number; percentage: number; passed: boolean };

export default function LessonWorkspaceScreen() {
  const { id: routeId } = useLocalSearchParams<{ id: string }>();
  const id = Number(routeId);
  const router = useRouter();
  const { user } = useAuth();
  const scope = `${user?.id}:${user?.role}:lesson:${id}`;
  const [lesson, setLesson] = useScopedState<Lesson | null>(scope, null);
  const [course, setCourse] = useScopedState<Course | null>(scope, null);
  const [lessons, setLessons] = useScopedState<Lesson[]>(scope, []);
  const [modules, setModules] = useScopedState<CourseModule[]>(scope, []);
  const [liveSessions, setLiveSessions] = useScopedState<LearningSession[]>(scope, []);
  const [sessionError, setSessionError] = useScopedState(scope, '');
  const [progress, setProgress] = useScopedState<Progress | null>(scope, null);
  const [quiz, setQuiz] = useScopedState<Quiz | null>(scope, null);
  const [attempt, setAttempt] = useScopedState<Attempt | null>(scope, null);
  const [loading, setLoading] = useScopedState(scope, true);
  const [refreshing, setRefreshing] = useScopedState(scope, false);
  const [working, setWorking] = useScopedState(scope, false);
  const [error, setError] = useScopedState(scope, '');
  const [transcriptOpen, setTranscriptOpen] = useState(false);
  const operation = useRef(0);
  const load = useCallback(async () => {
    const request = ++operation.current;
    setSessionError('');
    if (!Number.isInteger(id) || id < 1) { setError('This lesson link is invalid.'); setLoading(false); return; }
    setError('');
    try {
      const current = await apiRequest<Lesson>(`learning/lessons/${id}/`);
      if (request !== operation.current) return;
      setLesson(current);
      const [courseInfo, lessonPage, courseProgress, moduleList, sessionPage] = await Promise.all([
        apiRequest<Course>(`learning/courses/${current.course}/`),
        apiRequest<Lesson[]>(`learning/courses/${current.course}/lessons/`),
        apiRequest<Progress>(`learning/courses/${current.course}/progress/`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }),
        apiRequest<CourseModule[]>(`learning/courses/${current.course}/modules/`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return [];
          setSessionError('Course sections are temporarily unavailable. Refresh to retry.');
          return [];
        }),
        apiRequest<SessionPage>(`learning/courses/${current.course}/live-sessions/?lesson=${id}&page_size=100`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return { results: [], next: null };
          setSessionError('Unable to load live sessions for this lesson. Refresh to retry.');
          return { results: [], next: null };
        }),
      ]);
      if (request !== operation.current) return;
      setCourse(courseInfo); setLessons(lessonPage); setModules(moduleList); setLiveSessions(sessionPage.results); setProgress(courseProgress);
      if (courseProgress) {
        const [quizResult, attempts] = await Promise.all([
          apiRequest<Quiz>(`learning/lessons/${id}/quiz/`).catch((e: unknown) => {
            if (e instanceof ApiError && e.status === 404) return null;
            throw e;
          }),
          apiRequest<Attempt[]>('learning/quiz-attempts/me/'),
        ]);
        if (request === operation.current) {
          setQuiz(quizResult);
          setAttempt(quizResult ? attempts.find(value => value.quiz === quizResult.id) || null : null);
        }
      } else { setQuiz(null); setAttempt(null); }
    } catch (e) {
      if (request === operation.current) {
        setLesson(null); setCourse(null); setLessons([]); setModules([]); setLiveSessions([]); setProgress(null); setQuiz(null); setAttempt(null);
        setError(e instanceof Error ? e.message : 'Unable to load this lesson.');
      }
    } finally { if (request === operation.current) { setLoading(false); setRefreshing(false); } }
  }, [id, scope]);
  useFocusEffect(useCallback(() => { void load(); return () => { operation.current++; }; }, [load]));

  const curriculumGroups = modules.length ? [
    ...modules.map(module => ({ id: module.id, title: module.title, lessons: lessons.filter(item => item.module === module.id) })).filter(group => group.lessons.length),
    { id: 0, title: 'Other lessons', lessons: lessons.filter(item => !item.module || !modules.some(module => module.id === item.module)) },
  ].filter(group => group.lessons.length) : [{ id: 0, title: '', lessons }];
  const curriculum = curriculumGroups.flatMap(group => group.lessons);
  const index = curriculum.findIndex(item => item.id === lesson?.id);
  const previous = index > 0 ? curriculum[index - 1] : null;
  const next = index >= 0 && index + 1 < curriculum.length ? curriculum[index + 1] : null;
  const completed = !!progress?.completed_lesson_ids?.includes(id);
  const go = (target: Lesson) => router.replace({ pathname: '/learning/lesson/[id]', params: { id: String(target.id) } });
  async function markComplete() {
    if (working || completed) return;
    setWorking(true); setError('');
    try { await apiRequest(`learning/lessons/${id}/progress/`, { method: 'POST', body: { completed: true } }); await load(); }
    catch (e) { await load(); setError(e instanceof Error ? e.message : 'Unable to update lesson progress.'); }
    finally { setWorking(false); }
  }
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Lesson', headerTintColor: palette.blue, headerShadowVisible: false }} />
    <Page eyebrow="AWINLINK LEARNING" title={lesson?.title || 'Lesson workspace'} refreshControl={<RefreshControl refreshing={refreshing} tintColor={palette.blue} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={palette.blue} style={styles.loader} /> : error && !lesson ? <EmptyState title="Lesson unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : lesson && course ? <>
        <View style={ui.hero}>
          <Pressable accessibilityRole="link" onPress={() => router.replace({ pathname: '/learning/[id]', params: { id: String(course.id) } })} style={styles.back}><Text style={styles.backText}>‹  {course.title}</Text></Pressable>
          <Text style={ui.eyebrow}>LESSON {lesson.order} · {lesson.duration} MIN</Text>
          <Text accessibilityRole="header" style={ui.heroTitle}>{lesson.title}</Text>
          {!!lesson.module_title && <Text style={ui.body}>Section: {lesson.module_title}</Text>}
          {progress && <><Text style={ui.body}>{progress.progress_percentage}% course progress · {completed ? 'Lesson complete' : 'In progress'}</Text><View accessibilityRole="progressbar" accessibilityLabel="Course progress" accessibilityValue={{ min: 0, max: 100, now: Math.max(0, Math.min(100, progress.progress_percentage)) }} style={ui.track}><View style={[ui.fill, { width: `${Math.max(0, Math.min(100, progress.progress_percentage))}%` }]} /></View></>}
        </View>
        <View style={[ui.card, styles.player]}>
          {lesson.video ? <VideoPlayer uri={lesson.video} captionsUri={lesson.captions} captionLanguage={lesson.caption_language} /> : <Text style={ui.body}>This lesson has no video. Read the lesson description and resources below.</Text>}
        </View>
        {!!lesson.transcript && <View style={ui.card}><Pressable accessibilityRole="button" accessibilityState={{ expanded: transcriptOpen }} onPress={() => setTranscriptOpen(value => !value)} style={styles.action}><Text style={styles.actionText}>{transcriptOpen ? 'Hide transcript' : 'Read transcript'}</Text></Pressable>{transcriptOpen && <Text selectable style={[ui.body, { marginTop: 12 }]}>{lesson.transcript}</Text>}</View>}
        {!!lesson.description && <View style={ui.card}><Text accessibilityRole="header" style={ui.cardTitle}>About this lesson</Text><Text style={ui.body}>{lesson.description}</Text></View>}
        {liveSessions.length > 0 && <View style={ui.card}><Text accessibilityRole="header" style={ui.cardTitle}>Live sessions for this lesson</Text>{liveSessions.map(session => <View key={session.id} style={styles.sessionCard}><Text style={styles.strong}>{session.title}</Text><Text style={ui.body}>{session.status === 'LIVE' ? 'Live now' : 'Scheduled'} · {session.classroom_title}{session.scheduled_start ? ` · ${new Date(session.scheduled_start).toLocaleString()}` : ''}</Text>{!!session.module_title && <Text style={ui.body}>Section: {session.module_title}</Text>}<Pressable accessibilityRole="link" onPress={() => router.push({ pathname: '/classroom/[id]', params: { id: String(session.id) } })} style={styles.action}><Text style={styles.actionText}>{session.status === 'LIVE' ? 'Open live classroom' : 'View session'}</Text></Pressable></View>)}</View>}
        <View style={ui.card}>
          <Text accessibilityRole="header" style={ui.cardTitle}>Resources and quiz</Text>
          {lesson.notes ? <Pressable accessibilityRole="button" onPress={() => { void downloadMedia(lesson.notes!).catch(() => setError('Unable to open lesson notes.')); }} style={styles.action}><Text style={styles.actionText}>Open lesson notes</Text></Pressable> : <Text style={ui.body}>No additional resources for this lesson.</Text>}
          {progress && (quiz ? <View style={styles.quizRow}><View style={ui.copy}><Text style={styles.strong}>{quiz.title}</Text><Text style={ui.body}>{attempt?.passed ? `Passed · ${attempt.percentage}%` : attempt ? `Latest attempt · ${attempt.percentage}% · Pass ${quiz.passing_score}% to complete` : `Not attempted · Pass ${quiz.passing_score}% to complete`}</Text></View><Pressable accessibilityRole="button" accessibilityLabel={`Open quiz: ${quiz.title}`} onPress={() => router.push({ pathname: '/learning/quiz/[id]', params: { id: String(lesson.id) } })} style={styles.action}><Text style={styles.actionText}>{attempt?.passed ? 'Review quiz' : 'Take quiz'}</Text></Pressable></View> : <Text style={ui.body}>No quiz for this lesson.</Text>)}
          {!progress && <Text style={ui.body}>Enroll in this course to take quizzes and track lesson completion.</Text>}
          {progress && <Pressable accessibilityRole="button" accessibilityState={{ disabled: completed || working }} disabled={completed || working} onPress={() => void markComplete()} style={[ui.button, (completed || working) && styles.disabled]}><Text style={ui.buttonText}>{completed ? 'Lesson completed' : working ? 'Saving progress...' : quiz && !attempt?.passed ? 'Pass quiz to complete lesson' : 'Mark lesson complete'}</Text></Pressable>}
        </View>
        {progress && <View style={ui.card}>
          <Text accessibilityRole="header" style={ui.cardTitle}>Course curriculum</Text>
          <Text style={ui.body}>{lessons.length} lessons loaded · {progress.completed_lessons}/{progress.total_lessons} complete</Text>
          {curriculumGroups.map(group => <View key={`lesson-module-${group.id}`}>{!!group.title && <Text accessibilityRole="header" style={ui.cardTitle}>{group.title}</Text>}{group.lessons.map(item => <View key={item.id}><Pressable accessibilityRole="link" accessibilityState={{ selected: item.id === id }} accessibilityLabel={`Lesson ${item.order}: ${item.title}${progress.completed_lesson_ids?.includes(item.id) ? ', completed' : ''}${item.id === id ? ', current lesson' : ''}`} onPress={() => go(item)} style={[styles.lessonRow, item.id === id && styles.current]}><Text style={styles.number}>{String(item.order).padStart(2, '0')}</Text><View style={ui.copy}><Text style={styles.strong}>{item.title}</Text><Text style={ui.body}>{item.duration} min · {progress.completed_lesson_ids?.includes(item.id) ? 'Completed' : item.id === id ? 'In progress' : 'Up next'}</Text></View>{item.id === id && <Text accessibilityLabel="Current lesson">▶</Text>}</Pressable>{liveSessions.filter(session => session.lesson === item.id).map(session => <Text key={`session-label-${session.id}`} style={ui.body}>{session.title} · {session.module_title || group.title || 'Course session'}</Text>)}</View>)}</View>)}
          <LoadMore items={lessons} onChange={setLessons} label="Load more lessons" />
        </View>}
        {!!sessionError && <Text accessibilityRole="alert" style={styles.error}>{sessionError}</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
        <View style={styles.navigation}>
          <Pressable accessibilityRole="button" disabled={!previous} accessibilityState={{ disabled: !previous }} onPress={() => previous && go(previous)} style={[styles.action, !previous && styles.disabled]}><Text style={styles.actionText}>Previous lesson</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={!next} accessibilityState={{ disabled: !next }} onPress={() => next && go(next)} style={[ui.button, !next && styles.disabled]}><Text style={ui.buttonText}>{next ? 'Next lesson' : 'Last lesson'}</Text></Pressable>
        </View>
      </> : null}
    </Page>
  </>;
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  back: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start' },
  backText: { color: palette.blue, fontSize: 14, fontWeight: '700' },
  player: { padding: 8, overflow: 'hidden' },
  action: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start', backgroundColor: palette.pale, borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10 },
  actionText: { color: palette.blue, fontSize: 13, fontWeight: '800' },
  quizRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginTop: 16 },
  strong: { color: palette.ink, fontSize: 14, fontWeight: '800' },
  sessionCard: { backgroundColor: '#f5f9ff', borderColor: palette.line, borderWidth: 1, borderRadius: 10, padding: 12, gap: 8, marginTop: 10 },
  lessonRow: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: 12, borderBottomWidth: 1, borderBottomColor: palette.line, paddingVertical: 10 },
  current: { backgroundColor: palette.pale, borderRadius: 9, paddingHorizontal: 10 },
  number: { color: palette.blue, fontSize: 13, fontWeight: '800' },
  navigation: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, marginVertical: 12 },
  disabled: { opacity: 0.5 },
  error: { color: '#b42318', fontSize: 13, lineHeight: 20 },
});
