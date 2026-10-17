import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';

import { ApiError, apiRequest, mediaSource } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { VideoPlayer } from '@/src/components/MediaPlayer';
import { colors } from '@/src/theme';
import { useAuth } from '@/src/auth/AuthProvider';

type Course = { id: number; title: string; description: string; creator_name: string; category_name: string; level: string; duration: number; is_free: boolean; lesson_count: number };
type Lesson = { id: number; title: string; description: string; notes: string; video: string | null; order: number; duration: number };
type Progress = { progress_percentage: number; completed_lessons: number; total_lessons: number; completed: boolean; completed_lesson_ids?: number[] };
type Review = { id: number; user: number; user_name: string; rating: number; review: string; created_at: string };
type LessonQuiz = { id: number; title: string; passing_score: number; question_count: number };
type QuizAvailability = 'available' | 'none' | 'unknown';

export default function CourseScreen() {
  const { id: routeId } = useLocalSearchParams<{ id: string }>();
  const id = Number(routeId);
  const router = useRouter();
  const { user } = useAuth();
  const [course, setCourse] = useState<Course | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [completedLessonIds, setCompletedLessonIds] = useState<Set<number>>(new Set());
  const [quizAvailability, setQuizAvailability] = useState<Record<number, QuizAvailability>>({});
  const [reviews, setReviews] = useState<Review[]>([]);
  const [reviewDraft, setReviewDraft] = useState('');
  const [rating, setRating] = useState(5);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    if (!Number.isInteger(id) || id < 1) { setError('This course link is invalid.'); setLoading(false); return; }
    setError('');
    try {
      const info = await apiRequest<Course>(`learning/courses/${id}/`);
      setCourse(info);
      const [lessonList, courseProgress] = await Promise.all([
        apiRequest<Lesson[]>(`learning/courses/${id}/lessons/`),
        apiRequest<Progress>(`learning/courses/${id}/progress/`).catch((e: unknown) => {
          if (e instanceof ApiError && e.status === 404) return null;
          throw e;
        }),
      ]);
      const reviewList = await apiRequest<Review[]>(`learning/courses/${id}/reviews/`);
      setLessons(lessonList); setProgress(courseProgress); setReviews(reviewList);
      setCompletedLessonIds(new Set(courseProgress?.completed_lesson_ids || []));
      if (courseProgress) {
        const quizChecks = await Promise.all(lessonList.map(async (lesson): Promise<[number, QuizAvailability]> => {
          try {
            await apiRequest<LessonQuiz>(`learning/lessons/${lesson.id}/quiz/`);
            return [lesson.id, 'available'];
          } catch (quizError) {
            return [lesson.id, quizError instanceof ApiError && quizError.status === 404 ? 'none' : 'unknown'];
          }
        }));
        setQuizAvailability(Object.fromEntries(quizChecks));
      } else {
        setQuizAvailability({});
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load this course.'); }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { void load(); }, [load]);
  async function enroll() {
    setWorking(true); setError('');
    try { await apiRequest(`learning/courses/${id}/enroll/`, { method: 'POST' }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to enroll in this course.'); }
    finally { setWorking(false); }
  }
  async function markComplete(lesson: Lesson) {
    setWorking(true); setError('');
    try { await apiRequest(`learning/lessons/${lesson.id}/progress/`, { method: 'POST', body: { completed: true } }); setCompletedLessonIds((current) => new Set(current).add(lesson.id)); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update lesson progress.'); }
    finally { setWorking(false); }
  }
  async function submitReview() {
    setWorking(true); setError('');
    try { const review = await apiRequest<Review>(`learning/courses/${id}/reviews/`, { method: 'POST', body: { rating, review: reviewDraft.trim() } }); setReviews((current) => [review, ...current]); setReviewDraft(''); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to submit course review.'); }
    finally { setWorking(false); }
  }
  return <>
    <Stack.Screen options={{ headerShown: true, title: course?.title || 'Course', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="LEARNING" title={course?.title || 'Course'}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && !course ? <EmptyState title="Course unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : course ? <>
        <Text style={styles.meta}>{course.category_name} · {course.level.toLowerCase()} · {course.duration} minutes</Text>
        <Text style={styles.description}>{course.description}</Text>
        <Text style={styles.meta}>By {course.creator_name}</Text>
        {progress ? <View style={styles.progress}><Text style={styles.progressText}>{progress.progress_percentage}% complete ({progress.completed_lessons}/{progress.total_lessons} lessons)</Text></View> : <Pressable disabled={working || !course.is_free} onPress={() => void enroll()} style={styles.button}><Text style={styles.buttonText}>{working ? 'Working...' : course.is_free ? 'Enroll in course' : 'Paid enrollment unavailable'}</Text></Pressable>}
        <Text style={styles.section}>Course lessons</Text>
        {!progress && <Text style={styles.meta}>Enroll to track your lesson progress.</Text>}
        {lessons.map((lesson, index) => <View key={lesson.id} style={styles.lesson}><Text style={styles.lessonTitle}>{index + 1}. {lesson.title}</Text>{!!lesson.description && <Text style={styles.meta}>{lesson.description}</Text>}{!!lesson.notes && <Pressable accessibilityRole="link" onPress={() => { void mediaSource(lesson.notes).then(source => Linking.openURL(source.uri)).catch(() => setError("Unable to open lesson notes.")); }}><Text style={styles.lessonActionText}>Open lesson notes</Text></Pressable>}{!!lesson.video && <VideoPlayer uri={lesson.video} />}{progress && <View style={styles.lessonActions}><Pressable disabled={working || completedLessonIds.has(lesson.id) || progress.completed} onPress={() => void markComplete(lesson)} style={styles.lessonAction}><Text style={styles.lessonActionText}>{completedLessonIds.has(lesson.id) || progress.completed ? 'Completed' : 'Mark lesson complete'}</Text></Pressable>{quizAvailability[lesson.id] === 'available' ? <Pressable onPress={() => router.push({ pathname: '/learning/quiz/[id]', params: { id: String(lesson.id) } })} style={styles.lessonAction}><Text style={styles.lessonActionText}>Open quiz</Text></Pressable> : quizAvailability[lesson.id] === 'none' ? <Text style={styles.meta}>No quiz for this lesson.</Text> : quizAvailability[lesson.id] === 'unknown' ? <Text style={styles.meta}>Quiz availability could not be checked. Refresh to retry.</Text> : null}</View>}</View>)}
        <Text style={styles.section}>Reviews</Text>
        {!!progress && !reviews.some((review) => review.user === user?.id) && <View style={styles.lesson}><Text style={styles.meta}>Your rating: {rating} / 5</Text><View style={styles.lessonActions}>{[1, 2, 3, 4, 5].map((value) => <Pressable accessibilityRole="button" key={value} onPress={() => setRating(value)} style={styles.lessonAction}><Text style={styles.lessonActionText}>{value}{rating === value ? ' ★' : ''}</Text></Pressable>)}</View><TextInput accessibilityLabel="Course review" multiline onChangeText={setReviewDraft} placeholder="Share your course review" placeholderTextColor={colors.muted} style={styles.reviewInput} value={reviewDraft} /><Pressable disabled={working || !reviewDraft.trim()} onPress={() => void submitReview()} style={styles.lessonAction}><Text style={styles.lessonActionText}>{working ? 'Submitting...' : 'Submit review'}</Text></Pressable></View>}
        {reviews.length ? reviews.map((review) => <View key={review.id} style={styles.lesson}><Text style={styles.lessonTitle}>{review.user_name} · {review.rating}/5</Text><Text style={styles.meta}>{review.review}</Text></View>) : <Text style={styles.meta}>No reviews yet.</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </> : null}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, meta: { color: colors.muted, fontSize: 12, lineHeight: 18 }, description: { color: colors.ink, fontSize: 14, lineHeight: 21 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, progress: { backgroundColor: colors.softBlue, borderRadius: 12, padding: 13 }, progressText: { color: colors.primary, fontSize: 13, fontWeight: '800' }, button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, padding: 14 }, buttonText: { color: '#fff', fontSize: 13, fontWeight: '800' }, lesson: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 8, padding: 13 }, lessonTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' }, lessonActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, lessonAction: { alignSelf: 'flex-start', backgroundColor: colors.softBlue, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }, lessonActionText: { color: colors.primary, fontSize: 11, fontWeight: '800' }, reviewInput: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minHeight: 70, padding: 10, textAlignVertical: 'top' }, error: { color: colors.danger, fontSize: 12 } });
