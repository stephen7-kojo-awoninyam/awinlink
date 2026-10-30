import { usePagedState } from '@/src/paged-state';
import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Platform, Pressable, RefreshControl, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect, useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

import { ApiError, apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';
import { courseCategoryDefault } from '@/src/course-category';
import { learningColors as palette } from '@/src/learning-theme';

type Category = { id: number; name: string; is_default?: boolean };
type Course = { id: number; creator: number; category: number; category_name: string; title: string; slug: string; description: string; level: string; duration: number; is_free: boolean; status: string; rejection_reason?: string | null; lesson_count: number };
type Lesson = { id: number; title: string; description: string; video: string | null; notes: string | null; captions: string | null; caption_language: string; transcript: string; module?: number | null; order: number; duration: number };
type CourseModule = { id: number; title: string; description: string; order: number };
type QuizSummary = { id: number; lesson: number; title: string; passing_score: number; question_count: number };
type StudioQuestion = { id: number; quiz: number; question: string; option_a: string; option_b: string; option_c: string; option_d: string; correct_answer: string };
type SubmissionCheck = { key: string; label: string; ready: boolean; detail: string };

const emptyCourse = { title: '', description: '', level: 'BEGINNER', duration: '' };
const emptyLesson = { title: '', description: '', video: '', notes: '', caption_language: '', transcript: '', duration: '', module: '' };
const emptyQuiz = { title: '', passing_score: '70' };
const emptyQuestion = { question: '', option_a: '', option_b: '', option_c: '', option_d: '', correct_answer: 'A' };

export default function LearningStudioScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [categories, setCategories] = usePagedState<Category>([]);
  const [courses, setCourses] = usePagedState<Course>([]);
  const [pendingCourses, setPendingCourses] = usePagedState<Course>([]);
  const [reviewNotes, setReviewNotes] = useState<Record<number, string>>({});
  const [selected, setSelected] = useState<Course | null>(null);
  const [lessons, setLessons] = usePagedState<Lesson>([]);
  const [modules, setModules] = useState<CourseModule[]>([]);
  const [moduleTitle, setModuleTitle] = useState('');
  const [moduleDrafts, setModuleDrafts] = useState<Record<number, { title: string; order: string }>>({});
  const [readiness, setReadiness] = useState<SubmissionCheck[]>([]);
  const [quizByLesson, setQuizByLesson] = useState<Record<number, QuizSummary | null>>({});
  const [editingLesson, setEditingLesson] = useState<number | null>(null);
  const [quizLesson, setQuizLesson] = useState<number | null>(null);
  const [editingQuizId, setEditingQuizId] = useState<number | null>(null);
  const [quizDraft, setQuizDraft] = useState(emptyQuiz);
  const [activeQuiz, setActiveQuiz] = useState<QuizSummary | null>(null);
  const [questions, setQuestions] = usePagedState<StudioQuestion>([]);
  const [questionDraft, setQuestionDraft] = useState(emptyQuestion);
  const [editingQuestion, setEditingQuestion] = useState<number | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [courseForm, setCourseForm] = useState(emptyCourse);
  const [lessonForm, setLessonForm] = useState(emptyLesson);
  const [lessonFiles, setLessonFiles] = useState<Partial<Record<'video' | 'notes' | 'captions', DocumentPicker.DocumentPickerAsset>>>({});
  const [thumbnail, setThumbnail] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const lessonRequest = useRef(0);

  const load = useCallback(async () => {
    setError('');
    try {
      const [categoryList, courseList, pendingList] = await Promise.all([
        apiRequest<Category[]>('learning/categories/'),
        apiRequest<Course[]>('learning/courses/me/'),
        user?.role === 'ADMIN' ? apiRequest<Course[]>('learning/courses/pending/') : Promise.resolve([]),
      ]);
      setCategories(categoryList); setCourses(courseList); setPendingCourses(pendingList);
      setCategoryId(current => courseCategoryDefault(categoryList, current));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load your course studio.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [user?.role]);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  if (!user) return <Redirect href="/login" />;
  if (!['ATHLETE', 'ORGANIZATION', 'SCOUT', 'COACH', 'ADMIN'].includes(user.role)) return <Redirect href="/(tabs)" />;

  async function openCourse(course: Course) {
    const request = ++lessonRequest.current;
    setSelected(course); setError('');
    setLessons([]); setModules([]); setModuleDrafts({});
    setReadiness([]); setQuizByLesson({}); setActiveQuiz(null); setQuestions([]);
    setQuizLesson(null); setEditingLesson(null); setEditingQuestion(null);
    setLessonFiles({}); setLessonForm(emptyLesson);
    setCategoryId(course.category);
    setCourseForm({ title: course.title, description: course.description, level: course.level, duration: String(course.duration) });
    setThumbnail(null);
    try {
      const [rows, moduleRows] = await Promise.all([
        apiRequest<Lesson[]>(`learning/courses/${course.id}/lessons/`),
        apiRequest<CourseModule[]>(`learning/courses/${course.id}/modules/`).catch(error => {
          if (error instanceof ApiError && error.status === 404) return [];
          throw error;
        }),
      ]);
      const [checks, quizRows] = await Promise.all([
        ['DRAFT', 'REJECTED'].includes(course.status)
          ? apiRequest<{ checks: SubmissionCheck[] }>(`learning/courses/${course.id}/readiness/`).then(value => value.checks)
          : Promise.resolve([] as SubmissionCheck[]),
        Promise.all(rows.map(async lesson => {
          try { const value = await apiRequest<{ quiz: QuizSummary | null }>(`learning/studio/lessons/${lesson.id}/quiz/`); return [lesson.id, value.quiz] as const; }
          catch { return [lesson.id, null] as const; }
        })),
      ]);
      if (request === lessonRequest.current) {
        setLessons(rows); setModules(moduleRows); setModuleTitle('');
        setModuleDrafts(Object.fromEntries(moduleRows.map(module => [module.id, { title: module.title, order: String(module.order) }])));
        setReadiness(checks); setQuizByLesson(Object.fromEntries(quizRows));
      }
    }
    catch (e) { if (request === lessonRequest.current) { setLessons([]); setError(e instanceof Error ? e.message : 'Unable to load course lessons.'); } }
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
        form.append('thumbnail', Platform.OS === 'web' && thumbnail.file ? thumbnail.file : { uri: thumbnail.uri, name: thumbnail.name, type: thumbnail.mimeType || 'image/jpeg' } as unknown as Blob);
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
      body.append('module', lessonForm.module || 'none');
      body.append('caption_language', lessonForm.caption_language.trim()); body.append('transcript', lessonForm.transcript);
      for (const field of ['video', 'notes', 'captions'] as const) {
        const file = lessonFiles[field];
        if (file) body.append(field, Platform.OS === 'web' && file.file ? file.file : { uri: file.uri, name: file.name, type: file.mimeType || 'application/octet-stream' } as unknown as Blob);
      }
      const lesson = await apiRequest<Lesson>(`learning/courses/${selected.id}/lessons/create/`, { method: 'POST', body });
      setLessonFiles({});
      setSelected(current => current?.id === selected.id ? { ...current, lesson_count: current.lesson_count + 1 } : current);
      setLessons(current => [...current, lesson]); setQuizByLesson(current => ({ ...current, [lesson.id]: null }));
      setCourses(current => current.map(course => course.id === selected.id ? { ...course, lesson_count: course.lesson_count + 1 } : course)); setLessonForm(emptyLesson);
      await refreshReadiness(selected.id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to add lesson.'); }
    finally { setWorking(false); }
  }

  async function refreshReadiness(courseId: number) {
    try { const value = await apiRequest<{ checks: SubmissionCheck[] }>(`learning/courses/${courseId}/readiness/`); setReadiness(value.checks); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to refresh publishing checklist.'); }
  }

  function beginEditLesson(lesson: Lesson) {
    setEditingLesson(lesson.id); setLessonForm({ title: lesson.title, description: lesson.description, duration: String(lesson.duration), video: '', notes: '', caption_language: lesson.caption_language || '', transcript: lesson.transcript || '', module: lesson.module ? String(lesson.module) : '' }); setLessonFiles({});
  }

  async function saveLessonChanges(lesson: Lesson) {
    if (!selected || !lessonForm.title.trim()) { setError('Enter a lesson title.'); return; }
    setWorking(true); setError('');
    try {
      const body = new FormData();
      body.append('title', lessonForm.title.trim()); body.append('description', lessonForm.description.trim()); body.append('duration', String(Number(lessonForm.duration) || 0));
      body.append('module', lessonForm.module || 'none');
      body.append('caption_language', lessonForm.caption_language.trim()); body.append('transcript', lessonForm.transcript);
      for (const field of ['video', 'notes', 'captions'] as const) {
        const file = lessonFiles[field];
        if (file) body.append(field, Platform.OS === 'web' && file.file ? file.file : { uri: file.uri, name: file.name, type: file.mimeType || 'application/octet-stream' } as unknown as Blob);
      }
      const updated = await apiRequest<Lesson>(`learning/lessons/${lesson.id}/`, { method: 'PATCH', body });
      setLessons(current => current.map(row => row.id === updated.id ? updated : row)); setEditingLesson(null); setLessonForm(emptyLesson); setLessonFiles({});
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save lesson changes.'); }
    finally { setWorking(false); }
  }

  async function createQuiz(lessonId: number) {
    if (!quizDraft.title.trim()) { setError('Enter a quiz title.'); return; }
    setWorking(true); setError('');
    try {
      const quiz = await apiRequest<QuizSummary>(`learning/studio/lessons/${lessonId}/quiz/`, { method: editingQuizId ? 'PATCH' : 'POST', body: { title: quizDraft.title.trim(), passing_score: Number(quizDraft.passing_score) } });
      setQuizByLesson(current => ({ ...current, [lessonId]: quiz })); setQuizLesson(null); setEditingQuizId(null); setQuizDraft(emptyQuiz); setActiveQuiz(quiz);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to create the lesson quiz.'); }
    finally { setWorking(false); }
  }

  async function loadQuizQuestions(quiz: QuizSummary) {
    setActiveQuiz(quiz); setEditingQuestion(null); setQuestionDraft(emptyQuestion); setError('');
    try { setQuestions(await apiRequest<StudioQuestion[]>(`learning/studio/quizzes/${quiz.id}/questions/`)); }
    catch (e) { setQuestions([]); setError(e instanceof Error ? e.message : 'Unable to load quiz questions.'); }
  }

  async function saveQuestion() {
    if (!activeQuiz || !questionDraft.question.trim() || !['option_a', 'option_b', 'option_c', 'option_d'].every(key => questionDraft[key as keyof typeof questionDraft].trim())) {
      setError('Complete the question and all four answer choices.'); return;
    }
    setWorking(true); setError('');
    try {
      const url = editingQuestion ? `learning/studio/questions/${editingQuestion}/` : `learning/studio/quizzes/${activeQuiz.id}/questions/`;
      const question = await apiRequest<StudioQuestion>(url, { method: editingQuestion ? 'PATCH' : 'POST', body: questionDraft });
      if (editingQuestion) setQuestions(current => current.map(item => item.id === question.id ? question : item));
      else {
        setQuestions(current => [...current, question]);
        const updated = { ...activeQuiz, question_count: activeQuiz.question_count + 1 };
        setActiveQuiz(updated); setQuizByLesson(current => ({ ...current, [updated.lesson]: updated }));
      }
      setEditingQuestion(null); setQuestionDraft(emptyQuestion); if (selected) await refreshReadiness(selected.id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save this quiz question.'); }
    finally { setWorking(false); }
  }

  async function pickLessonFile(field: 'video' | 'notes' | 'captions') {
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: field === 'video' ? 'video/*' : field === 'captions' ? ['text/vtt', 'text/plain'] : ['application/pdf', 'text/plain'], copyToCacheDirectory: true });
      if (!result.canceled) setLessonFiles(current => ({ ...current, [field]: result.assets[0] }));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to select this file.'); }
  }

  async function addModule() {
    if (!selected || !moduleTitle.trim()) { setError('Enter a section title.'); return; }
    setWorking(true); setError('');
    try {
      const module = await apiRequest<CourseModule>(`learning/courses/${selected.id}/modules/`, { method: 'POST', body: { title: moduleTitle.trim() } });
      setModules(current => [...current, module].sort((a, b) => a.order - b.order || a.id - b.id));
      setModuleDrafts(current => ({ ...current, [module.id]: { title: module.title, order: String(module.order) } }));
      setModuleTitle('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to create course section.'); }
    finally { setWorking(false); }
  }

  async function saveModule(module: CourseModule) {
    if (!selected) return;
    const draft = moduleDrafts[module.id] || { title: module.title, order: String(module.order) };
    const order = Number(draft.order);
    if (!draft.title.trim() || !Number.isInteger(order) || order < 1) { setError('Enter a section title and order of at least 1.'); return; }
    setWorking(true); setError('');
    try {
      const updated = await apiRequest<CourseModule>(`learning/modules/${module.id}/`, { method: 'PATCH', body: { title: draft.title.trim(), order } });
      setModules(current => current.map(row => row.id === updated.id ? updated : row).sort((a, b) => a.order - b.order || a.id - b.id));
      setModuleDrafts(current => ({ ...current, [updated.id]: { title: updated.title, order: String(updated.order) } }));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save section changes.'); }
    finally { setWorking(false); }
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
      const data = { ...courseForm, slug: courseForm.title.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, ''), category: categoryId, duration: Number(courseForm.duration) || 0, is_free: course.is_free };
      let body: unknown = data;
      if (thumbnail) {
        const form = new FormData();
        Object.entries(data).forEach(([key, value]) => form.append(key, String(value)));
        form.append('thumbnail', Platform.OS === 'web' && thumbnail.file ? thumbnail.file : { uri: thumbnail.uri, name: thumbnail.name, type: thumbnail.mimeType || 'image/jpeg' } as unknown as Blob);
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
        <Pressable accessibilityRole="button" disabled={working} onPress={() => { lessonRequest.current++; setSelected(null); setCourseForm(emptyCourse); setThumbnail(null); setCategoryId(courseCategoryDefault(categories)); setError(''); }}><Text style={styles.back}>← My courses</Text></Pressable>
        <View style={styles.studioHero}><Text style={styles.eyebrow}>CREATOR DASHBOARD</Text><Text style={styles.heroTitle}>{selected.title}</Text><Text style={styles.heroMeta}>{selected.status} · {selected.lesson_count} lessons · {selected.duration} min</Text><Pressable accessibilityRole="link" onPress={() => router.push({ pathname: '/learning/[id]', params: { id: String(selected.id) } })} style={styles.previewButton}><Text style={styles.previewText}>Preview as learner</Text></Pressable></View>
        {!!selected.rejection_reason && <View accessibilityRole="alert" style={styles.feedback}><Text style={styles.feedbackTitle}>Moderator feedback</Text><Text style={styles.feedbackText}>{selected.rejection_reason}</Text></View>}
        {['DRAFT', 'REJECTED'].includes(selected.status) && <View style={styles.checklist}><Text style={styles.section}>Publishing checklist</Text>{readiness.map(check => <View key={check.key} style={styles.checkRow}><Text style={[styles.checkMark, check.ready && styles.checkReady]}>{check.ready ? '✓' : '!'}</Text><View style={styles.copy}><Text style={styles.itemTitle}>{check.label}</Text><Text style={styles.meta}>{check.detail}</Text></View></View>)}<Text style={styles.meta}>Complete all required checks before moderation review.</Text>{!selected.is_free && <Text accessibilityRole="alert" style={styles.error}>This existing paid course is preserved, but cannot be submitted until billing is available.</Text>}<Pressable accessibilityRole="button" accessibilityState={{ disabled: working || !selected.is_free || !readiness.length || !readiness.every(check => check.ready) }} disabled={working || !selected.is_free || !readiness.length || !readiness.every(check => check.ready)} onPress={() => void submitCourse(selected)} style={[styles.button, (working || !selected.is_free || !readiness.length || !readiness.every(check => check.ready)) && styles.disabled]}><Text style={styles.buttonText}>{working ? 'Submitting...' : !selected.is_free ? 'Paid publishing unavailable' : selected.lesson_count === 0 ? 'Add a lesson before submitting' : readiness.length && readiness.every(check => check.ready) ? 'Submit for admin review' : 'Complete checklist to submit'}</Text></Pressable></View>}
        {selected.status === 'PENDING' && <View style={styles.notice}><Text style={styles.noticeText}>Waiting for administrator review. Editing is locked until an administrator records a decision.</Text></View>}
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
        </>}
        <Text accessibilityRole="header" style={styles.section}>Curriculum management</Text>
        {['DRAFT', 'REJECTED'].includes(selected.status) && <View style={styles.nestedForm}>
          <Text style={styles.itemTitle}>Optional sections</Text>
          <Text style={styles.meta}>Lessons keep their saved order. Sections only group navigation; unassigned lessons remain available.</Text>
          <TextInput accessibilityLabel="New section title" onChangeText={setModuleTitle} placeholder="New section title" placeholderTextColor={colors.muted} style={styles.input} value={moduleTitle} />
          <Pressable accessibilityRole="button" disabled={working || !moduleTitle.trim()} onPress={() => void addModule()} style={[styles.button, (working || !moduleTitle.trim()) && styles.disabled]}><Text style={styles.buttonText}>Add section</Text></Pressable>
          {modules.map(module => <View key={module.id} style={styles.moduleDraft}>
            <TextInput accessibilityLabel={`Section ${module.title} title`} onChangeText={title => setModuleDrafts(current => ({ ...current, [module.id]: { ...(current[module.id] || { title: module.title, order: String(module.order) }), title } }))} placeholder="Section title" placeholderTextColor={colors.muted} style={[styles.input, styles.moduleTitleInput]} value={(moduleDrafts[module.id] || { title: module.title, order: String(module.order) }).title} />
            <TextInput accessibilityLabel={`Section ${module.title} order`} keyboardType="number-pad" onChangeText={order => setModuleDrafts(current => ({ ...current, [module.id]: { ...(current[module.id] || { title: module.title, order: String(module.order) }), order } }))} placeholder="Order" placeholderTextColor={colors.muted} style={[styles.input, styles.moduleOrderInput]} value={(moduleDrafts[module.id] || { title: module.title, order: String(module.order) }).order} />
            <Pressable accessibilityRole="button" disabled={working} onPress={() => void saveModule(module)} style={styles.secondaryButton}><Text style={styles.secondaryText}>Save section</Text></Pressable>
          </View>)}
        </View>}
        {lessons.slice().sort((a, b) => a.order - b.order || a.id - b.id).map((lesson, index) => {
          const quiz = quizByLesson[lesson.id];
          const editable = ['DRAFT', 'REJECTED'].includes(selected.status);
          return <View key={lesson.id} style={styles.card}><View style={styles.lessonHeader}><Text style={styles.number}>{String(index + 1).padStart(2, '0')}</Text><View style={styles.copy}><Text accessibilityRole="header" style={styles.itemTitle}>{lesson.title}</Text><Text style={styles.meta}>{modules.find(module => module.id === lesson.module)?.title || 'Other lessons'} · {lesson.duration} min · {lesson.video ? 'Video ready' : 'No video'} · {lesson.notes ? 'Notes ready' : 'No notes'}</Text></View></View>{!!lesson.description && <Text style={styles.meta}>{lesson.description}</Text>}
            {editable && <Pressable accessibilityRole="button" onPress={() => beginEditLesson(lesson)} style={styles.secondaryButton}><Text style={styles.secondaryText}>Edit lesson</Text></Pressable>}
            {quiz ? <View style={styles.quizInfo}><Text style={styles.itemTitle}>{quiz.title}</Text><Text style={styles.meta}>{quiz.question_count} question(s) · pass score {quiz.passing_score}%{quiz.question_count ? ' · Ready' : ' · Needs questions'}</Text><View style={styles.row}><Pressable accessibilityRole="button" onPress={() => void loadQuizQuestions(quiz)} style={styles.secondaryButton}><Text style={styles.secondaryText}>{activeQuiz?.id === quiz.id ? 'Refresh questions' : 'Manage questions'}</Text></Pressable>{editable && <Pressable accessibilityRole="button" onPress={() => { setQuizLesson(lesson.id); setEditingQuizId(quiz.id); setQuizDraft({ title: quiz.title, passing_score: String(quiz.passing_score) }); }} style={styles.secondaryButton}><Text style={styles.secondaryText}>Edit quiz settings</Text></Pressable>}</View></View> : editable ? <Pressable accessibilityRole="button" onPress={() => { setQuizLesson(lesson.id); setEditingQuizId(null); setQuizDraft(emptyQuiz); }} style={styles.secondaryButton}><Text style={styles.secondaryText}>Add optional quiz</Text></Pressable> : <Text style={styles.meta}>No quiz · optional</Text>}
            {quizLesson === lesson.id && <View style={styles.nestedForm}><Text accessibilityRole="header" style={styles.itemTitle}>{editingQuizId ? 'Edit quiz settings' : 'Create lesson quiz'}</Text><TextInput accessibilityLabel="Quiz title" onChangeText={title => setQuizDraft(current => ({ ...current, title }))} placeholder="Quiz title" placeholderTextColor={colors.muted} style={styles.input} value={quizDraft.title} /><TextInput accessibilityLabel="Quiz passing score" keyboardType="number-pad" onChangeText={passing_score => setQuizDraft(current => ({ ...current, passing_score }))} placeholder="Passing score (1–100)" placeholderTextColor={colors.muted} style={styles.input} value={quizDraft.passing_score} /><Pressable accessibilityRole="button" disabled={working} onPress={() => void createQuiz(lesson.id)} style={styles.button}><Text style={styles.buttonText}>{working ? 'Saving...' : editingQuizId ? 'Save quiz settings' : 'Create quiz'}</Text></Pressable><Pressable accessibilityRole="button" disabled={working} onPress={() => { setQuizLesson(null); setEditingQuizId(null); setQuizDraft(emptyQuiz); }} style={styles.secondaryButton}><Text style={styles.secondaryText}>Cancel</Text></Pressable></View>}
            {quiz && activeQuiz?.id === quiz.id && <View style={styles.nestedForm}><Text accessibilityRole="header" style={styles.itemTitle}>Quiz questions</Text>{questions.map((question, qIndex) => <View key={question.id} style={styles.questionRow}><Text style={styles.meta}>{qIndex + 1}. {question.question}</Text><Text style={styles.meta}>Correct answer: {question.correct_answer}</Text><Pressable accessibilityRole="button" onPress={() => { setEditingQuestion(question.id); setQuestionDraft({ question: question.question, option_a: question.option_a, option_b: question.option_b, option_c: question.option_c, option_d: question.option_d, correct_answer: question.correct_answer }); }} style={styles.secondaryButton}><Text style={styles.secondaryText}>Edit question</Text></Pressable></View>)}<TextInput accessibilityLabel="Quiz question" multiline onChangeText={question => setQuestionDraft(current => ({ ...current, question }))} placeholder="Question" placeholderTextColor={colors.muted} style={[styles.input, styles.multiline]} value={questionDraft.question} />{(['option_a', 'option_b', 'option_c', 'option_d'] as const).map((key, choiceIndex) => <View key={key} style={styles.choiceRow}><TextInput accessibilityLabel={`Answer choice ${String.fromCharCode(65 + choiceIndex)}`} onChangeText={value => setQuestionDraft(current => ({ ...current, [key]: value }))} placeholder={`Choice ${String.fromCharCode(65 + choiceIndex)}`} placeholderTextColor={colors.muted} style={[styles.input, styles.choiceInput]} value={questionDraft[key]} /><Pressable accessibilityRole="radio" accessibilityLabel={`Mark choice ${String.fromCharCode(65 + choiceIndex)} correct`} accessibilityState={{ checked: questionDraft.correct_answer === String.fromCharCode(65 + choiceIndex) }} onPress={() => setQuestionDraft(current => ({ ...current, correct_answer: String.fromCharCode(65 + choiceIndex) }))} style={[styles.category, questionDraft.correct_answer === String.fromCharCode(65 + choiceIndex) && styles.categorySelected]}><Text style={styles.categoryText}>{questionDraft.correct_answer === String.fromCharCode(65 + choiceIndex) ? 'Correct' : 'Set correct'}</Text></Pressable></View>)}<Pressable accessibilityRole="button" disabled={working} onPress={() => void saveQuestion()} style={styles.button}><Text style={styles.buttonText}>{working ? 'Saving...' : editingQuestion ? 'Save question changes' : 'Add quiz question'}</Text></Pressable><LoadMore items={questions} onChange={setQuestions} label="Load more quiz questions" /></View>}
          </View>;
        })}
        <LoadMore items={lessons} onChange={setLessons} label="Load more lessons" />
        {!['PENDING', 'APPROVED'].includes(selected.status) && <>
          <Text accessibilityRole="header" style={styles.section}>{editingLesson ? 'Edit lesson' : 'Add lesson'}</Text>
          <TextInput accessibilityLabel="Lesson title" onChangeText={title => setLessonForm(current => ({ ...current, title }))} placeholder="Lesson title" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.title} />
          <TextInput accessibilityLabel="Lesson description" onChangeText={description => setLessonForm(current => ({ ...current, description }))} placeholder="Description" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.description} />
          <Text style={styles.meta}>Section (optional)</Text>
          <View style={styles.row}>
            <Pressable accessibilityRole="radio" accessibilityLabel="No section" accessibilityState={{ checked: !lessonForm.module }} onPress={() => setLessonForm(current => ({ ...current, module: '' }))} style={[styles.category, !lessonForm.module && styles.categorySelected]}><Text style={styles.categoryText}>No section</Text></Pressable>
            {modules.map(module => <Pressable key={module.id} accessibilityRole="radio" accessibilityLabel={`Assign lesson to section ${module.title}`} accessibilityState={{ checked: lessonForm.module === String(module.id) }} onPress={() => setLessonForm(current => ({ ...current, module: String(module.id) }))} style={[styles.category, lessonForm.module === String(module.id) && styles.categorySelected]}><Text style={styles.categoryText}>{module.title}</Text></Pressable>)}
          </View>
          {(['video', 'notes', 'captions'] as const).map(field => <View key={field}>
            <Pressable accessibilityRole="button" disabled={working} onPress={() => void pickLessonFile(field)} style={styles.category}><Text style={styles.categoryText}>{lessonFiles[field]?.name || `Choose lesson ${field} (optional)`}</Text></Pressable>
            {!!lessonFiles[field] && <Pressable disabled={working} onPress={() => setLessonFiles(current => ({ ...current, [field]: undefined }))}><Text style={styles.meta}>Remove {field}</Text></Pressable>}
          </View>)}
          <TextInput accessibilityLabel="Caption language" autoCapitalize="none" onChangeText={caption_language => setLessonForm(current => ({ ...current, caption_language }))} placeholder="Caption language tag, such as en or en-US" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.caption_language} />
          <TextInput accessibilityLabel="Lesson transcript" multiline onChangeText={transcript => setLessonForm(current => ({ ...current, transcript }))} placeholder="Transcript (optional, up to 100,000 characters)" placeholderTextColor={colors.muted} style={[styles.input, styles.multiline]} value={lessonForm.transcript} maxLength={100000} />
          <TextInput accessibilityLabel="Lesson duration in minutes" keyboardType="number-pad" onChangeText={duration => setLessonForm(current => ({ ...current, duration }))} placeholder="Duration in minutes" placeholderTextColor={colors.muted} style={styles.input} value={lessonForm.duration} />
          <Pressable accessibilityRole="button" disabled={working} onPress={() => { const lesson = lessons.find(item => item.id === editingLesson); if (lesson) void saveLessonChanges(lesson); else void createLesson(); }} style={styles.button}><Text style={styles.buttonText}>{working ? 'Saving...' : editingLesson ? 'Save lesson changes' : 'Add lesson'}</Text></Pressable>
          {!!editingLesson && <Pressable accessibilityRole="button" disabled={working} onPress={() => { setEditingLesson(null); setLessonForm(emptyLesson); setLessonFiles({}); }} style={styles.secondaryButton}><Text style={styles.secondaryText}>Cancel edit</Text></Pressable>}
        </>}
      </> : <>
        <View style={styles.studioHero}><Text style={styles.eyebrow}>A WINNING LEARNING EXPERIENCE STARTS HERE</Text><Text accessibilityRole="header" style={styles.heroTitle}>Your course dashboard</Text><Text style={styles.heroMeta}>{courses.filter(course => course.status === 'DRAFT' || course.status === 'REJECTED').length} editable · {courses.filter(course => course.status === 'PENDING').length} in review · {courses.filter(course => course.status === 'APPROVED').length} published</Text><Text style={styles.meta}>Build the curriculum, check quiz readiness, preview the learner experience, then submit for review.</Text></View>
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
        {loading ? <ActivityIndicator color={colors.primary} /> : courses.length === 0 ? <EmptyState title="No courses yet" message="Create a course, add lessons, then submit it for review." /> : courses.map(course => <Pressable accessibilityRole="button" key={course.id} disabled={working} onPress={() => void openCourse(course)} style={styles.card}><Text style={styles.itemTitle}>{course.title}</Text><Text style={styles.meta}>{course.status} · {course.lesson_count} lessons</Text><Text style={styles.open}>Manage course</Text></Pressable>)}
      </>}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}

      <LoadMore items={categories} onChange={setCategories} label="Load more categories" />
      <LoadMore items={courses} onChange={setCourses} label="Load more courses" />
      <LoadMore items={pendingCourses} onChange={setPendingCourses} label="Load more pending courses" />
      <LoadMore items={lessons} onChange={setLessons} label="Load more lessons" />
    </Page>
  </>;
}

const styles = StyleSheet.create({
  back: { color: palette.blue, fontSize: 14, fontWeight: '800', minHeight: 44, textAlignVertical: 'center' },
  status: { color: colors.muted, fontSize: 12 },
  section: { color: palette.ink, fontSize: 18, fontWeight: '800', marginTop: 12, marginBottom: 5 },
  card: { backgroundColor: '#fff', borderColor: palette.line, borderRadius: 14, borderWidth: 1, gap: 10, padding: 15 },
  itemTitle: { color: palette.ink, fontSize: 14, fontWeight: '800' },
  meta: { color: palette.muted, fontSize: 12, lineHeight: 18 },
  open: { color: palette.blue, fontSize: 12, fontWeight: '800' },
  input: { backgroundColor: '#fff', borderColor: palette.line, borderRadius: 11, borderWidth: 1, color: palette.ink, minHeight: 46, paddingHorizontal: 12, fontSize: 16 },
  multiline: { minHeight: 90, paddingVertical: 10, textAlignVertical: 'top' },
  categoryRow: { flexDirection: 'row', gap: 8 },
  category: { backgroundColor: '#fff', borderColor: palette.line, borderRadius: 10, borderWidth: 1, padding: 10, minHeight: 44, justifyContent: 'center' },
  categorySelected: { backgroundColor: palette.pale, borderColor: palette.blue },
  categoryText: { color: palette.muted, fontSize: 12 },
  categoryTextSelected: { color: palette.blue, fontWeight: '800' },
  row: { alignItems: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  button: { alignItems: 'center', backgroundColor: palette.blue, borderRadius: 10, minHeight: 46, justifyContent: 'center', padding: 12 },
  buttonText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  rejectButton: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 11, flex: 1, justifyContent: 'center', minHeight: 44, padding: 11 },
  rejectText: { color: colors.danger, fontSize: 12, fontWeight: '800' },
  disabled: { opacity: 0.5 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 18 },
  studioHero: { backgroundColor: '#eef5ff', borderColor: '#d7e6fc', borderRadius: 18, borderWidth: 1, gap: 9, padding: 20 },
  eyebrow: { color: '#315a91', fontSize: 10, fontWeight: '800', letterSpacing: 1.5 },
  heroTitle: { color: palette.ink, fontSize: 24, fontWeight: '800', lineHeight: 30 },
  heroMeta: { color: palette.muted, fontSize: 13 },
  previewButton: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center', paddingHorizontal: 14, backgroundColor: '#fff', borderColor: '#bfd3f3', borderWidth: 1, borderRadius: 9 },
  previewText: { color: palette.blue, fontSize: 13, fontWeight: '800' },
  feedback: { backgroundColor: '#fff8ec', borderColor: '#f2d8aa', borderWidth: 1, borderRadius: 12, gap: 5, padding: 14 },
  feedbackTitle: { color: '#754e09', fontSize: 13, fontWeight: '800' },
  feedbackText: { color: palette.ink, fontSize: 13, lineHeight: 19 },
  checklist: { backgroundColor: '#fff', borderColor: palette.line, borderTopColor: palette.blue, borderTopWidth: 4, borderWidth: 1, borderRadius: 14, gap: 9, padding: 15 },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, paddingVertical: 9, borderBottomColor: palette.line, borderBottomWidth: 1 },
  checkMark: { color: '#845500', backgroundColor: '#fff3dc', width: 25, height: 25, borderRadius: 13, textAlign: 'center', textAlignVertical: 'center', overflow: 'hidden', fontWeight: '900' },
  checkReady: { color: '#216844', backgroundColor: '#e8f7ee' },
  copy: { flex: 1, minWidth: 0, gap: 3 },
  notice: { backgroundColor: '#edf4ff', borderRadius: 12, padding: 14 },
  noticeText: { color: '#294b7d', fontSize: 13, lineHeight: 19 },
  lessonHeader: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  number: { backgroundColor: palette.pale, color: palette.blue, borderRadius: 9, overflow: 'hidden', padding: 9, fontSize: 13, fontWeight: '900' },
  secondaryButton: { alignSelf: 'flex-start', minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, paddingVertical: 8, backgroundColor: palette.pale, borderRadius: 9 },
  secondaryText: { color: palette.blue, fontSize: 12, fontWeight: '800' },
  quizInfo: { backgroundColor: '#f5f9ff', borderColor: '#d9e7fb', borderWidth: 1, borderRadius: 11, padding: 12, gap: 7 },
  nestedForm: { backgroundColor: '#f7faff', borderRadius: 11, padding: 12, gap: 9 },
  questionRow: { borderBottomWidth: 1, borderBottomColor: palette.line, paddingVertical: 9, gap: 6 },
  choiceRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  moduleDraft: { alignItems: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  moduleTitleInput: { flexGrow: 1, flexBasis: 180 },
  moduleOrderInput: { width: 88 },
  choiceInput: { flex: 1, minWidth: 0 },
});
