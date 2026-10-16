import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Quiz = { id: number; title: string; passing_score: number; question_count: number };
type Question = { id: number; question: string; option_a: string; option_b: string; option_c: string; option_d: string };
type Attempt = { score: number; total_questions: number; percentage: number; passed: boolean };
type Choice = 'A' | 'B' | 'C' | 'D';

export default function QuizScreen() {
  const { id: rawId } = useLocalSearchParams<{ id: string }>();
  const id = Number(rawId);
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, Choice>>({});
  const [result, setResult] = useState<Attempt | null>(null);
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
  }, [id]);
  useEffect(() => { void load(); }, [load]);

  async function submit() {
    if (!questions.length || questions.some((question) => !answers[String(question.id)]) || working) return;
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
        {result ? <View style={styles.result}><Text style={styles.resultTitle}>{result.passed ? 'Passed' : 'Attempt complete'}</Text><Text style={styles.meta}>{result.score} of {result.total_questions} correct · {result.percentage}%</Text></View> : questions.length === 0 ? <EmptyState title="No questions available" message="The backend returned an empty quiz." /> : questions.map((question) => <View key={question.id} style={styles.card}><Text style={styles.question}>{question.question}</Text>{(['A', 'B', 'C', 'D'] as Choice[]).map((choice) => { const option = question[`option_${choice.toLowerCase()}` as 'option_a' | 'option_b' | 'option_c' | 'option_d']; const selected = answers[String(question.id)] === choice; return <Pressable key={choice} accessibilityRole="radio" accessibilityState={{ checked: selected }} onPress={() => setAnswers((current) => ({ ...current, [String(question.id)]: choice }))} style={[styles.option, selected && styles.optionSelected]}><Text style={[styles.optionText, selected && styles.optionTextSelected]}>{choice}. {option}</Text></Pressable>; })}</View>)}
        {!result && questions.length > 0 && <Pressable disabled={working || questions.some((question) => !answers[String(question.id)])} onPress={() => void submit()} style={[styles.submit, (working || questions.some((question) => !answers[String(question.id)])) && styles.disabled]}><Text style={styles.submitText}>{working ? 'Submitting...' : 'Submit answers'}</Text></Pressable>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, meta: { color: colors.muted, fontSize: 12, lineHeight: 18 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 8, padding: 12 }, question: { color: colors.ink, fontSize: 14, fontWeight: '800', lineHeight: 20 }, option: { borderColor: colors.border, borderRadius: 10, borderWidth: 1, padding: 10 }, optionSelected: { backgroundColor: colors.softBlue, borderColor: colors.primary }, optionText: { color: colors.ink, fontSize: 12 }, optionTextSelected: { color: colors.primary, fontWeight: '700' }, submit: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, padding: 13 }, submitText: { color: '#fff', fontSize: 13, fontWeight: '800' }, disabled: { opacity: 0.5 }, result: { backgroundColor: colors.softBlue, borderRadius: 12, gap: 5, padding: 14 }, resultTitle: { color: colors.primary, fontSize: 16, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
