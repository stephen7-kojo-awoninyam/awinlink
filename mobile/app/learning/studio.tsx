import { useCallback, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Category = { id: number; name: string };
type Course = { id: number; category: number; category_name: string; title: string; slug: string; description: string; level: string; duration: number; is_free: boolean; status: string; rejection_reason?: string | null; lesson_count: number };
type Lesson = { id: number; title: string; description: string; video: string | null; notes: string; order: number; duration: number };

const emptyCourse = { title: '', description: '', level: 'BEGINNER', duration: '' };
const emptyLesson = { title: '', description: '', video: '', notes: '', duration: '' };

export default function LearningStudioScreen() {
  const { user } = useAuth();
  const [categories, setCategories] = useState<Category[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [pendingCourses, setPendingCourses] = useState<Course[]>([]);
  const [reviewNotes, setReviewNotes] = useState<Record<number, string>>({});
  const [selected, setSelected] = useState<Course | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [courseForm, setCourseForm] = useState(emptyCourse);
  const [lessonForm, setLessonForm] = useState(emptyLesson);
  const [lessonFiles, setLessonFiles] = useState<Partial<Record<'video' | 'notes', DocumentPicker.DocumentPickerAsset>>>({});
  const [thumbnail, setThumbnail] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [categoryList, courseList, pendingList] = await Promise.all([
        apiRequest<Category[]>('learning/categories/'),
        apiRequest<Course[]>('learning/courses/me/'),
        user?.role === 'ADMIN' ? apiRequest<Course[]>('learning/courses/pending/') : Promise.resolve([]),
      ]);
      setCategories(categoryList); setCourses(courseList); setPendingCourses(pendingList);
      if (!categoryId && categoryList[0]) setCategoryId(categoryList[0].id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load your course studio.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [categoryId, user?.role]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  if (!user) return <Redirect href="/login" />;
  if (!['ATHLETE', 'ORGANIZATION', 'COACH', 'ADMIN'].includes(user.role)) return <Redirect href="/(tabs)" />;

  async function openCourse(course: Course) {
    setSelected(course); setError('');
    setLessonFiles({}); setLessonForm(emptyLesson);
    setCategoryId(course.category);
    setCourseForm({ title: course.title, description: course.description, level: course.level, duration: String(course.duration) });
    setThumbnail(null);
    try { setLessons(await apiRequest<Lesson[]>(`learning/courses/${course.id}/lessons/`)); }
    catch (e) { setLessons([]); setError(e instanceof Error ? e.message : 'Unable to load course lessons.'); }
  }

  async function createCourse() {
    if (!categoryId || !courseForm.title.trim() || !courseForm.description.trim()) { setError('Choose a category and complete the title and description.'); return; }
    setWorking(true); setError('');
    try {
      const slug = courseForm.title.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
      const courseData = { ...courseForm, slug, category: categoryId, duration: Number(courseForm.duration) || 0, is_free: true };
      let body: unknown = courseData;
      if (thumbnail) {
        const form = new FormData();
        Object.entries(courseData).forEach(([key, value]) => form.append(key, String(value)));
        form.append('thumbnail', { uri: thumbnail.uri, name: thumbnail.name, type: thumbnail.mimeType || 'image/jpeg' } as unknown as Blob);
        body = form;
      }
      const course = await apiRequest<Course>('learning/courses/create/', { method: 'POST', body });
      setCourses(current => [course, ...current]); setCourseForm(emptyCourse); setThumbnail(null); setSelected(course); setLessons([]);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to create course.'); }
    finally { setWorking(false); }
  }

  async function createLesson() {
    if (!selected || !lessonForm.title.trim()) { setError('Enter a lesson title.'); return; }
    setWorking(true); setError('');
    try {
      const body = new FormData();
      body.append('title', lessonForm.title.trim());
      body.append('description', lessonForm.description.trim());
      body.append('duration', String(Number(lessonForm.duration) || 0));
      body.append('order', String(Math.max(0, ...lessons.map(item => item.order)) + 1));
      for (const field of ['video', 'notes'] as const) {
        const file = lessonFiles[field];
        if (file) body.append(field, Platform.OS === 'web' && file.file ? file.file : { uri: file.uri, name: file.name, type: file.mimeType || 'application/octet-stream' } as unknown as Blob);
      }
      const lesson = await apiRequest<Lesson>(`learning/courses/${selected.id}/lessons/create/`, { method: 'POST', body });
      setLessonFiles({});
      setLessons(current => [...current, lesson]); setCourses(current => current.map(course => course.id === selected.id ? { ...course, lesson_count: course.lesson_count + 1 } : course)); setLessonForm(emptyLesson);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to add lesson.'); }
    finally { setWorking(false); }
  }

  async function pickLessonFile(field: 'video' | 'notes') {
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: field === 'video' ? 'video/*' : ['application/pdf', 'text/plain'], copyToCacheDirectory: true });
      if (!result.canceled) setLessonFiles(current => ({ ...current, [field]: result.assets[0] }));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to select this file.'); }
  }

  async function submitCourse(course: Course) {
    setWorking(true); setError('');
    try {
      const updated = await apiRequest<Course>(`learning/courses/${course.id}/submit/`, { method: 'POST' });
      setCourses(current => current.map(item => item.id === updated.id ? updated : item)); setSelected(updated);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to submit course for review.'); }
    finally { setWorking(false); }
  }

  async function saveCourseChanges(course: Course) {
    if (!categoryId || !courseForm.title.trim() || !courseForm.description.trim()) { setError('Choose a category and complete the title and description.'); return; }
    setWorking(true); setError('');
    try {
      const data = { ...courseForm, slug: courseForm.title.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''), category: categoryId, duration: Number(courseForm.duration) || 0, is_free: true };
      let body: unknown = data;
      if (thumbnail) {
        const form = new FormData();
        Object.entries(data).forEach(([key, value]) => form.append(key, String(value)));
        form.append('thumbnail', { uri: thumbnail.uri, name: thumbnail.name, type: thumbnail.mimeType || 'image/jpeg' } as unknown as Blob);
        body = form;
      }
      const updated = await apiRequest<Course>(`learning/courses/${course.id}/`, { method: 'PATCH', body });
      setSelected(updated); setCourses(current => current.map(item => item.id === updated.id ? updated : item)); setThumbnail(null);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save course changes.'); }
    finally { setWorking(false); }
  }

  async function moderateCourse(course: Course, action: 'approve' | 'reject') {
    setWorking(true); setError('');
    try {
      const updated = await apiRequest<Course>(`learning/courses/${course.id}/${action}/`, { method: 'POST', body: action === 'reject' ? { rejection_reason: reviewNotes[course.id]?.trim() || '' } : {} });
      setPendingCourses(current => current.filter(item => item.id !== updated.id));
    } catch (e) { setError(e instanceof Error ? e.message : `Unable to ${action} this course.`); }
    finally { setWorking(false); }
  }

  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Course studio', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="LEARNING CREATOR" title={selected ? selected.title : 'Course studio'} refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {selected ? <>
        <Pressable accessibilityRole="button" onPress={() => { setSelected(null); setError(''); }}><Text style={styles.back}>← My courses</Text></Pressable>
        <Text style={styles.status}>Status: {selected.status} · {lessons.length} lessons</Text>
        {!!selected.rejection_reason && <Text style={styles.error}>Review feedback: {selected.rejection_reason}</Text>}
        {['DRAFT', 'REJECTED'].includes(selected.status) && <>
          <Text style={styles.section}>Course details</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categoryRow}>{categories.map(category => <Pressable key={category.id} accessibilityRole="button" onPress={() => setCategoryId(category.id)} style={[styles.category, category.id === categoryId && styles.categorySelected]}><Text style={[styles.categoryText, category.id === categoryId && styles.categoryTextSelected]}>{category.name}</Text></Pressable>)}</ScrollView>
          <TextInput accessibilityLabel="Course title" onChangeText={title => setCourseForm(current => ({ ...current, title }))} placeholder="Course title" placeholderTextColor={colors.muted} style={styles.input} value={courseForm.title} />
          <TextInput accessibilityLabel="Course description" multiline onChangeText={description => setCourseForm(current => ({ ...current, description }))} placeholder="Course description" placeholderTextColor={colors.muted} style={[styles.input, styles.multiline]} value={courseForm.description} />
          <View style={styles.row}><Pressable onPress={() => setCourseForm(current => ({ ...current, level: 'BEGINNER' }))} style={[styles.category, courseForm.level === 'BEGINNER' && styles.categorySelected]}><Text style={styles.categoryText}>Beginner</Text></Pressable><Pressable onPress={() => setCourseForm(current => ({ ...current, level: 'INTERMEDIATE' }))} style={[styles.category, courseForm.level === 'INTERMEDIATE' && styles.categorySelected]}><Text style={styles.categoryText}>Intermediate</Text></Pressable><Pressable onPress={() => setCourseForm(current => ({ ...current, level: 'ADVANCED' }))} style={[styles.category, courseForm.level === 'ADVANCED' && styles.categorySelected]}><Text style={styles.categoryText}>Advanced</Text></Pressable></View>
          <TextInput accessibilityLabel="Course duration in minutes" keyboardType="number-pad" onChangeText={duration => setCourseForm(current => ({ ...current, duration }))} placeholder="Total duration in minutes" placeholderTextColor={colors.muted} style={styles.input} value={courseForm.duration} />
          <Pressable accessibilityRole="button" onPress={async () => { const picked = await DocumentPicker.getDocumentAsync({ type: 'image/*', copyToCacheDirectory: true }); if (!picked.canceled) setThumbnail(picked.assets[0]); }} style={styles.category}><Text style={styles.categoryText}>{thumbnail?.name || 'Replace thumbnail (optional)'}</Text></Pressable>
          <Text style={styles.meta}>Courses are free at launch.</Text>
          <Pressable accessibilityRole="button" disabled={working} onPress={() => void saveCourseChanges(selected)} style={styles.button}><Text style={styles.buttonText}>{working ? 'Saving...' : 'Save course changes'}</Text></Pressable>
          <Pressable accessibilityRole="button" disabled={working || lessons.length === 0} onPress={() => void submitCourse(selected)} style={[styles.button, (working || lessons.length === 0) && styles.disabled]}><Text style={styles.buttonText}>{working ? 'Submitting...' : lessons.length === 0 ? 'Add a lesson before submitting' : 'Submit for admin review'}</Text></Pressable>
        </>}
        <Text style={styles.section}>Lessons</Text>
        {lessons.map((lesson, index) => <View key={lesson.id} style={styles.card}><Text style={styles.itemTitle}>{index + 1}. {lesson.title}</Text>{!!lesson.description && <Text style={styles.meta}>{lesson.description}</Text>}</View>)}
        {!['PENDING', 'APPROVED'].includes(selected.status) && <>
          <Text style={styles.section}>Add lesson</Text>
          <TextInput accessibilityLabel="Lesson title" onChangeText={title => setLessonForm(current => ({ ...current, title }))} placeholder="Lesson title" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.title} />
          <TextInput accessibilityLabel="Lesson description" onChangeText={description => setLessonForm(current => ({ ...current, description }))} placeholder="Description" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.description} />
          {(['video', 'notes'] as const).map(field => <View key={field}>
            <Pressable accessibilityRole="button" disabled={working} onPress={() => void pickLessonFile(field)} style={styles.category}><Text style={styles.categoryText}>{lessonFiles[field]?.name || `Choose lesson ${field} (optional)`}</Text></Pressable>
            {!!lessonFiles[field] && <Pressable disabled={working} onPress={() => setLessonFiles(current => ({ ...current, [field]: undefined }))}><Text style={styles.meta}>Remove {field}</Text></Pressable>}
          </View>)}
          <TextInput accessibilityLabel="Lesson duration in minutes" keyboardType="number-pad" onChangeText={duration => setLessonForm(current => ({ ...current, duration }))} placeholder="Duration in minutes" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.duration} />
          <Pressable accessibilityRole="button" disabled={working} onPress={() => void createLesson()} style={styles.button}><Text style={styles.buttonText}>{working ? 'Saving...' : 'Add lesson'}</Text></Pressable>
        </>}
      </> : <>
        {user.role === 'ADMIN' && <>
          <Text style={styles.section}>Courses awaiting review</Text>
          {pendingCourses.length === 0 ? <Text style={styles.meta}>No courses are pending review.</Text> : pendingCourses.map(course => <View key={course.id} style={styles.card}>
            <Text style={styles.itemTitle}>{course.title}</Text><Text style={styles.meta}>{course.category_name} · {course.lesson_count} lessons</Text><Text style={styles.meta}>{course.description}</Text>
            <TextInput accessibilityLabel={`Rejection reason for ${course.title}`} onChangeText={value => setReviewNotes(current => ({ ...current, [course.id]: value }))} placeholder="Required reason if rejecting" placeholderTextColor={colors.muted} style={styles.input} value={reviewNotes[course.id] || ''} />
            <View style={styles.row}><Pressable accessibilityRole="button" disabled={working} onPress={() => void moderateCourse(course, 'approve')} style={styles.button}><Text style={styles.buttonText}>Approve</Text></Pressable><Pressable accessibilityRole="button" disabled={working || !reviewNotes[course.id]?.trim()} onPress={() => void moderateCourse(course, 'reject')} style={[styles.rejectButton, (!reviewNotes[course.id]?.trim() || working) && styles.disabled]}><Text style={styles.rejectText}>Reject</Text></Pressable></View>
          </View>)}
        </>}
        <Text style={styles.section}>Create course</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.categoryRow}>{categories.map(category => <Pressable key={category.id} accessibilityRole="button" onPress={() => setCategoryId(category.id)} style={[styles.category, category.id === categoryId && styles.categorySelected]}><Text style={[styles.categoryText, category.id === categoryId && styles.categoryTextSelected]}>{category.name}</Text></Pressable>)}</ScrollView>
        <TextInput accessibilityLabel="Course title" onChangeText={title => setCourseForm(current => ({ ...current, title }))} placeholder="Course title" placeholderTextColor={colors.muted} style={styles.input} value={courseForm.title} />
        <TextInput accessibilityLabel="Course description" multiline onChangeText={description => setCourseForm(current => ({ ...current, description }))} placeholder="Course description" placeholderTextColor={colors.muted} style={[styles.input, styles.multiline]} value={courseForm.description} />
        <View style={styles.row}><Pressable onPress={() => setCourseForm(current => ({ ...current, level: 'BEGINNER' }))} style={[styles.category, courseForm.level === 'BEGINNER' && styles.categorySelected]}><Text style={styles.categoryText}>Beginner</Text></Pressable><Pressable onPress={() => setCourseForm(current => ({ ...current, level: 'INTERMEDIATE' }))} style={[styles.category, courseForm.level === 'INTERMEDIATE' && styles.categorySelected]}><Text style={styles.categoryText}>Intermediate</Text></Pressable><Pressable onPress={() => setCourseForm(current => ({ ...current, level: 'ADVANCED' }))} style={[styles.category, courseForm.level === 'ADVANCED' && styles.categorySelected]}><Text style={styles.categoryText}>Advanced</Text></Pressable></View>
        <TextInput accessibilityLabel="Course duration in minutes" keyboardType="number-pad" onChangeText={duration => setCourseForm(current => ({ ...current, duration }))} placeholder="Total duration in minutes" placeholderTextColor={colors.muted} style={styles.input} value={courseForm.duration} />
        <Pressable accessibilityRole="button" onPress={async () => { const picked = await DocumentPicker.getDocumentAsync({ type: 'image/*', copyToCacheDirectory: true }); if (!picked.canceled) setThumbnail(picked.assets[0]); }} style={styles.category}><Text style={styles.categoryText}>{thumbnail?.name || 'Choose course thumbnail (optional)'}</Text></Pressable>
        <Text style={styles.meta}>Courses are free at launch.</Text>
        <Pressable accessibilityRole="button" disabled={working || categories.length === 0} onPress={() => void createCourse()} style={[styles.button, working && styles.disabled]}><Text style={styles.buttonText}>{working ? 'Creating...' : 'Create draft course'}</Text></Pressable>
        <Text style={styles.section}>My courses</Text>
        {loading ? <ActivityIndicator color={colors.primary} /> : courses.length === 0 ? <EmptyState title="No courses yet" message="Create a course, add lessons, then submit it for review." /> : courses.map(course => <Pressable accessibilityRole="button" key={course.id} onPress={() => void openCourse(course)} style={styles.card}><Text style={styles.itemTitle}>{course.title}</Text><Text style={styles.meta}>{course.status} · {course.lesson_count} lessons</Text><Text style={styles.open}>Manage course</Text></Pressable>)}
      </>}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ back: { color: colors.primary, fontSize: 13, fontWeight: '800' }, status: { color: colors.muted, fontSize: 12 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 7, padding: 13 }, itemTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' }, meta: { color: colors.muted, fontSize: 12 }, open: { color: colors.primary, fontSize: 12, fontWeight: '800' }, input: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, minHeight: 44, paddingHorizontal: 12 }, multiline: { minHeight: 90, paddingVertical: 10, textAlignVertical: 'top' }, categoryRow: { flexDirection: 'row', gap: 8 }, category: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 10, borderWidth: 1, padding: 10 }, categorySelected: { backgroundColor: colors.softBlue, borderColor: colors.primary }, categoryText: { color: colors.muted, fontSize: 11 }, categoryTextSelected: { color: colors.primary, fontWeight: '800' }, row: { alignItems: 'center', flexDirection: 'row', gap: 8 }, button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 11, minHeight: 44, justifyContent: 'center', padding: 11 }, buttonText: { color: '#fff', fontSize: 12, fontWeight: '800' }, rejectButton: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 11, flex: 1, justifyContent: 'center', minHeight: 44, padding: 11 }, rejectText: { color: colors.danger, fontSize: 12, fontWeight: '800' }, disabled: { opacity: 0.55 }, error: { color: colors.danger, fontSize: 12, lineHeight: 18 } });
