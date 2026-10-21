import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect, useRouter } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { Page } from '@/src/components/Page';
import { EmptyState } from '@/src/components/EmptyState';
import { colors } from '@/src/theme';
import type { Session } from '@/src/classrooms/client';

import { ClassroomSetup, RoomManagement, type Room } from '@/src/classrooms/Management';
type PageResult<T> = { results: T[]; next: string | null };
function nextPath(value: string) { const path = value.replace(/^https?:\/\/[^/]+\/api\//, '').replace(/^\/api\//, ''); if (!path.startsWith('learning/')) throw new Error('Invalid classroom pagination.'); return path; }
export default function ClassroomsScreen() {
  const router = useRouter();
  const [rooms, setRooms] = useState<Room[]>([]), [sessions, setSessions] = useState<Record<number, Session[]>>({});
  const [next, setNext] = useState<string | null>(null), [sessionNext, setSessionNext] = useState<Record<number, string | null>>({});
  const [loading, setLoading] = useState(true), [working, setWorking] = useState(false), [error, setError] = useState('');
  const load = useCallback(async () => { setLoading(true); setError(''); try { const result = await apiRequest<PageResult<Room>>('learning/classrooms/'); setRooms(result.results); setNext(result.next); setSessions({}); setSessionNext({}); } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load classrooms.'); } finally { setLoading(false); } }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  async function loadSessions(room: Room) {
    if (working) return; setWorking(true); setError('');
    try { const path = sessionNext[room.id] ? nextPath(sessionNext[room.id]!) : `learning/classrooms/${room.id}/sessions/`; const result = await apiRequest<PageResult<Session>>(path); setSessions(current => ({ ...current, [room.id]: [...(current[room.id] || []), ...result.results] })); setSessionNext(current => ({ ...current, [room.id]: result.next })); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load sessions.'); } finally { setWorking(false); }
  }
  return <><Stack.Screen options={{ headerShown: true, title: 'Live classrooms' }} /><Page title="Live classrooms" eyebrow="LEARNING TOGETHER" refreshControl={<RefreshControl refreshing={loading} onRefresh={() => void load()} />}>
    {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    <ClassroomSetup refresh={load} />
    {loading ? <ActivityIndicator color={colors.primary} /> : !rooms.length ? <EmptyState title="No classrooms available" message="Enroll in a course to discover its classrooms." actionLabel="Refresh" onAction={() => void load()} /> : rooms.map(room => <View key={room.id} style={styles.card}>
      <Text style={styles.title}>{room.title}</Text><Text>{room.capacity} seats</Text>
      <RoomManagement room={room} refresh={load} />
      {sessions[room.id]?.map(session => <Pressable accessibilityRole="button" key={session.id} onPress={() => router.push({ pathname: '/classroom/[id]', params: { id: String(session.id) } })} style={styles.button}><Text style={styles.link}>{session.title} · {session.status.toLowerCase()}{session.scheduled_start ? ' | ' + new Date(session.scheduled_start).toLocaleString() : ''}</Text></Pressable>)}
      {sessions[room.id]?.length === 0 && <Text>No sessions scheduled.</Text>}
      {(!sessions[room.id] || sessionNext[room.id]) && <Pressable accessibilityRole="button" disabled={working} onPress={() => void loadSessions(room)} style={styles.button}><Text style={styles.link}>{sessions[room.id] ? 'More sessions' : 'View sessions'}</Text></Pressable>}
    </View>)}
    {!!next && <Pressable accessibilityRole="button" disabled={working} style={styles.button} onPress={() => { setWorking(true); void apiRequest<PageResult<Room>>(nextPath(next)).then(result => { setRooms(current => [...current, ...result.results]); setNext(result.next); }).catch(e => setError(e.message)).finally(() => setWorking(false)); }}><Text style={styles.link}>More classrooms</Text></Pressable>}
  </Page></>;
}
const styles = StyleSheet.create({ card: { backgroundColor: colors.surface, padding: 16, borderRadius: 14, gap: 9 }, title: { color: colors.ink, fontSize: 17, fontWeight: '800' }, button: { backgroundColor: colors.softBlue, padding: 12, borderRadius: 9 }, link: { color: colors.primary, fontWeight: '700' }, error: { color: colors.danger } });
