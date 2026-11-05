import { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { apiRequest } from '@/src/api/client';
import { nextPage } from '@/src/pagination';
import { ui } from '@/src/components/Page';

export type GuardianGrants = {
  id: number;
  contacts?: { username: string; allow_calls: boolean }[];
  courses?: { course_id: number; title: string; allow_live: boolean }[];
};
type Course = { id: number; title: string; minimum_age?: number };
type Progress = { course_id: number; title: string; completed: boolean; completed_lessons: number; lesson_count: number };

export function GuardianPermissions({ item, onChanged }: { item: GuardianGrants; onChanged: () => Promise<void> }) {
  const [username, setUsername] = useState('');
  const [calls, setCalls] = useState(false);
  const [live, setLive] = useState(false);
  const [courses, setCourses] = useState<Course[]>([]);
  const [continuation, setContinuation] = useState<string | null>(null);
  const [progress, setProgress] = useState<Progress[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function change(action: string, data: Record<string, unknown>) {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await apiRequest(`auth/guardians/${item.id}/`, { method: 'POST', body: { action, ...data } });
      setUsername(''); setCalls(false); setProgress([]); await onChanged();
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update guardian permission.'); }
    finally { setBusy(false); }
  }
  async function loadCourses(path = `auth/guardians/${item.id}/courses/`, append = false) {
    setBusy(true); setError('');
    try {
      const rows = await apiRequest<Course[]>(path);
      setCourses(current => append ? [...current, ...rows] : rows); setContinuation(nextPage(rows));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load courses.'); }
    finally { setBusy(false); }
  }
  async function loadProgress() {
    setBusy(true); setProgress([]); setError('');
    try { setProgress(await apiRequest<Progress[]>(`auth/guardians/${item.id}/learning/`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load learning progress.'); }
    finally { setBusy(false); }
  }
  return <View style={{ gap: 12 }}>
    <Text style={{ fontWeight: '700' }}>Approved contacts</Text>
    <Text>Messaging requires your approval. Calls require a separate choice. Withdrawing permission ends affected calls and removes access to the conversation.</Text>
    {(item.contacts || []).map(contact => <View key={contact.username} style={ui.card}>
      <Text>@{contact.username} · Messages{contact.allow_calls ? ' and calls' : ' only'}</Text>
      <Pressable disabled={busy} onPress={() => void change('remove_contact', { username: contact.username })}><Text>Withdraw contact permission</Text></Pressable>
    </View>)}
    <TextInput accessibilityLabel="Contact username" placeholder="Contact username" value={username} onChangeText={setUsername} autoCapitalize="none" editable={!busy} />
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: calls }} disabled={busy} onPress={() => setCalls(value => !value)}><Text>{calls ? '[x]' : '[ ]'} Also allow voice and video calls</Text></Pressable>
    <Pressable disabled={busy || !username.trim()} onPress={() => void change('allow_contact', { username: username.trim(), allow_calls: calls })}><Text>Approve contact</Text></Pressable>
    <Text style={{ fontWeight: '700' }}>Learning approvals</Text>
    <Text>Live approval includes interaction with the class's instructor, staff and other admitted learners. It does not allow private messaging or calls outside that class.</Text>
    {(item.courses || []).map(course => <View key={course.course_id} style={ui.card}>
      <Text>{course.title} · {course.allow_live ? 'Lessons and live classes' : 'Lessons only'}</Text>
      <Pressable disabled={busy} onPress={() => void change('remove_course', { course_id: course.course_id })}><Text>Withdraw learning permission</Text></Pressable>
    </View>)}
    <Pressable disabled={busy} onPress={() => void loadCourses()}><Text>Choose a course to approve</Text></Pressable>
    {!!courses.length && <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: live }} disabled={busy} onPress={() => setLive(value => !value)}><Text>{live ? '[x]' : '[ ]'} Also approve live classroom participation</Text></Pressable>}
    {courses.map(course => <Pressable key={course.id} disabled={busy} onPress={() => void change('allow_course', { course_id: course.id, allow_live: live })}><Text>Approve {course.title}{course.minimum_age ? ` · Ages ${course.minimum_age}+` : ''}</Text></Pressable>)}
    {!!continuation && <Pressable disabled={busy} onPress={() => void loadCourses(continuation!, true)}><Text>More courses</Text></Pressable>}
    <Pressable disabled={busy} onPress={() => void loadProgress()}><Text>View learning progress</Text></Pressable>
    {progress.map(row => <Text key={row.course_id}>{row.title}: {row.completed_lessons}/{row.lesson_count} lessons{row.completed ? ' · Completed' : ''}</Text>)}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}
