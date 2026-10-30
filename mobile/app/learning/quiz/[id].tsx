import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { useScopedState } from '@/src/privacy-state';
import { LoadMore } from '@/src/components/LoadMore';
import { nextPage } from '@/src/pagination';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Quiz = { id: number; title: string; passing_score: number; question_count: number };
type Question = { id: number; question: string; option_a: string; option_b: string; option_c: string; option_d: string };
type QuestionFeedback = { question_id: number; question: string; selected_answer: Choice | null; selected_text: string | null; correct_answer: Choice; correct_text: string; is_correct: boolean };
type Attempt = { score: number; total_questions: number; percentage: number; passed: boolean; question_feedback: QuestionFeedback[] };
type Choice = 'A' | 'B' | 'C' | 'D';

export default function QuizScreen() {
  const { id: rawId } = useLocalSearchParams<{ id: string }>();
  const id = Number(rawId);
  const { user } = useAuth();
  const scope = `${user?.id}:${id}`;
  const [quiz, setQuiz] = useScopedState<Quiz | null>(scope, null);
  const [questions, setQuestions] = useScopedState<Question[]>(scope, []);
  const [answers, setAnswers] = useScopedState<Record<string, Choice>>(scope, {});
  const [result, setResult] = useScopedState<Attempt | null>(scope, null);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    if (!Number.isInteger(id) || id < 1) { setError('This quiz link is invalid.'); setLoading(false); return; }
    setError('');
    try {
      const quizData = await apiRequest<Quiz>(`learning/lessons/${id}/quiz/`);
      const questionList = await apiRequest<Question[]>(`learning/quizzes/${quizData.id}/questions/`);
      setQuiz(quizData); setQuestions(questionList);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load this quiz.'); }
    finally { setLoading(false); }
  }, [id, scope]);
  useEffect(() => { void load(); }, [load]);

  async function submit() {
    if (nextPage(questions) || !questions.length || questions.some((question) => !answers[String(question.id)]) || working) return;
    setWorking(true); setError('');
    try { if (!quiz) return; setResult(await apiRequest<Attempt>(`learning/quizzes/${quiz.id}/attempt/`, { method: 'POST', body: { answers } })); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to submit this quiz.'); }
    finally { setWorking(false); }
  }

  return <>
    <Stack.Screen options={{ headerShown: true, title: quiz?.title || 'Quiz', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="LEARNING" title={quiz?.title || 'Quiz'}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && !quiz ? <EmptyState title="Quiz unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        {quiz && <Text style={styles.meta}>Passing score: {quiz.passing_score}%</Text>}
        {result ? <View style={styles.result}>
          <Text accessibilityRole="header" style={styles.resultTitle}>{result.passed ? 'Quiz passed' : 'Not passed yet'}</Text>
          <Text accessibilityLiveRegion="polite" style={styles.meta}>{result.score} of {result.total_questions} correct · {result.percentage}% · Pass mark {quiz?.passing_score}%</Text>
          {result.passed ? <Text style={styles.meta}>You met the pass mark. Return to the course and mark this lesson complete to update progress and check certificate eligibility.</Text> : <Text style={styles.meta}>You need {quiz?.passing_score}% to pass. Review each answer and retry when you’re ready.</Text>}
          {result.question_feedback.map((item, index) => <View key={item.question_id} style={styles.feedback}>
            <Text accessibilityRole="header" style={styles.question}>{index + 1}. {item.question}</Text>
            <Text style={styles.meta}>{item.is_correct ? 'Correct.' : 'Not quite.'} Your answer: {item.selected_answer ? `${item.selected_answer}. ${item.selected_text}` : 'No answer selected'}</Text>
            {!item.is_correct && <Text style={styles.meta}>Correct answer: {item.correct_answer}. {item.correct_text}</Text>}
          </View>)}
          {!result.passed && <Pressable accessibilityRole="button" onPress={() => { setResult(null); setError(''); }}><Text style={styles.retry}>Try quiz again</Text></Pressable>}
        </View> : questions.length === 0 ? <EmptyState title="No questions available" message="The backend returned an empty quiz." /> : questions.map((question) => <View key={question.id} style={styles.card}><Text accessibilityRole="header" style={styles.question}>{question.question}</Text>{(['A', 'B', 'C', 'D'] as Choice[]).map((choice) => { const option = question[`option_${choice.toLowerCase()}` as 'option_a' | 'option_b' | 'option_c' | 'option_d']; const selected = answers[String(question.id)] === choice; return <Pressable key={choice} accessibilityRole="radio" accessibilityLabel={`${question.question}, ${choice}. ${option}`} accessibilityState={{ checked: selected }} onPress={() => setAnswers((current) => ({ ...current, [String(question.id)]: choice }))} style={[styles.option, selected && styles.optionSelected]}><Text style={[styles.optionText, selected && styles.optionTextSelected]}>{choice}. {option}</Text></Pressable>; })}</View>)}
        {!result && <LoadMore items={questions} onChange={setQuestions} label="Load more questions" />}
        {!result && !!nextPage(questions) && <Text style={styles.meta}>Load and answer the remaining questions before submitting.</Text>}
        {!result && questions.length > 0 && <Pressable disabled={working || !!nextPage(questions) || questions.some((question) => !answers[String(question.id)])} onPress={() => void submit()} style={[styles.submit, (working || !!nextPage(questions) || questions.some((question) => !answers[String(question.id)])) && styles.disabled]}><Text style={styles.submitText}>{working ? 'Submitting...' : 'Submit answers'}</Text></Pressable>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, meta: { color: colors.muted, fontSize: 12, lineHeight: 18 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 8, padding: 12 }, question: { color: colors.ink, fontSize: 14, fontWeight: '800', lineHeight: 20 }, option: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, padding: 10 }, optionSelected: { backgroundColor: colors.softBlue, borderColor: colors.primary }, optionText: { color: colors.ink, fontSize: 12 }, optionTextSelected: { color: colors.primary, fontWeight: '700' }, submit: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, padding: 13 }, submitText: { color: '#fff', fontSize: 13, fontWeight: '800' }, disabled: { opacity: 0.5 }, result: { backgroundColor: colors.softBlue, borderRadius: 12, gap: 8, padding: 14 }, resultTitle: { color: colors.primary, fontSize: 16, fontWeight: '800' }, feedback: { backgroundColor: colors.surface, borderRadius: 10, gap: 4, marginTop: 4, padding: 10 }, retry: { color: colors.primary, fontSize: 14, fontWeight: '800', paddingVertical: 8 }, error: { color: colors.danger, fontSize: 12 } });
