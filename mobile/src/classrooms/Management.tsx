import { useEffect, useRef, useState } from 'react';
import { Alert, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { apiRequest } from '@/src/api/client';
import { colors } from '@/src/theme';

type Item = { id: number; title: string };
type Invitation = { id: number; classroom_title: string; recipient: number; recipient_username: string; status: string; is_expired: boolean; message: string };
type Staff = { id: number; user: number; username: string; display_name: string; role: string };
export type Room = Item & { course: number; capacity: number; capabilities: { manage: boolean; staff: boolean } };
type Result<T> = { results: T[]; next: string | null };
function path(value: string) { const result = value.replace(/^https?:\/\/[^/]+\/api\//, '').replace(/^\/api\//, ''); if (!result.startsWith('learning/')) throw new Error('Invalid pagination URL.'); return result; }
function Button({ label, action, disabled = false }: { label: string; action: () => void; disabled?: boolean }) { return <Pressable accessibilityRole="button" disabled={disabled} onPress={action} style={[styles.button, disabled && { opacity: .5 }]}><Text style={styles.link}>{label}</Text></Pressable>; }
function Input({ label, value, change, numeric = false, limit = 250 }: { label: string; value: string; change: (v: string) => void; numeric?: boolean; limit?: number }) { return <View><Text>{label}</Text><TextInput accessibilityLabel={label} value={value} onChangeText={change} keyboardType={numeric ? 'number-pad' : 'default'} autoCapitalize="none" maxLength={limit} style={styles.input} /></View>; }
function useOperation() {
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const run = async (action: () => Promise<void>) => { if (busy) return; setBusy(true); setMessage(''); try { await action(); } catch(e) { setMessage(e instanceof Error ? e.message : 'Classroom request failed.'); } finally { setBusy(false); } };
  return { busy, message, setMessage, run };
}
function positive(value: string) { const number = Number(value); if (!Number.isSafeInteger(number) || number < 1) throw new Error('Enter a positive whole number for seats.'); return number; }
function date(value: string) { if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(value) || !Number.isFinite(Date.parse(value))) throw new Error('Enter a valid date and time, for example 2026-11-01T14:30.'); return new Date(value).toISOString(); }
function confirmChange(title: string, action: () => void) {
  if (Platform.OS === 'web') { if (window.confirm(title)) action(); }
  else Alert.alert(title, 'This changes classroom staff permissions.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Confirm', style: 'destructive', onPress: action }]);
}
type SearchUser = { id: number; username: string; display_name: string };
function UsernamePicker({ room, purpose, label, selected, onSelect }: { room: number; purpose: 'invite' | 'cohost'; label: string; selected: SearchUser | null; onSelect: (user: SearchUser | null) => void }) {
  const [query, setQuery] = useState(''), [results, setResults] = useState<SearchUser[]>([]), [next, setNext] = useState<string | null>(null);
  const [busy, setBusy] = useState(false), [status, setStatus] = useState('');
  const generation = useRef(0);
  useEffect(() => () => { generation.current++; }, []);
  async function search(more = false) {
    const current = ++generation.current;
    if (query.trim().length < 2) { setStatus('Enter at least 2 username characters.'); return; }
    setBusy(true); setStatus(''); onSelect(null);
    try {
      const page = await apiRequest<Result<SearchUser>>(more && next ? path(next) : `learning/classrooms/${room}/users/?purpose=${purpose}&q=${encodeURIComponent(query.trim())}`);
      if (current !== generation.current) return;
      setResults(previous => more ? [...previous, ...page.results] : page.results); setNext(page.next);
      setStatus(page.results.length ? 'Choose a username below.' : 'No eligible users found.');
    } catch (e) { if (current === generation.current) setStatus(e instanceof Error ? e.message : 'Username search failed.'); }
    finally { if (current === generation.current) setBusy(false); }
  }
  return <View style={styles.panel}>
    <Input label={label} value={query} limit={150} change={value => { generation.current++; setQuery(value); onSelect(null); setResults([]); setNext(null); setStatus(''); setBusy(false); }} />
    <Button label="Search usernames" disabled={busy || query.trim().length < 2} action={() => void search()} />
    {!!status && <Text accessibilityRole="alert">{status}</Text>}
    {results.map(result => <Button key={result.id} label={`@${result.username} (${result.display_name})`} action={() => onSelect(result)} />)}
    {!!next && <Button label="More usernames" disabled={busy} action={() => void search(true)} />}
    {selected && <Text>Selected @{selected.username}</Text>}
  </View>;
}
export function ClassroomSetup({ refresh }: { refresh: () => Promise<void> }) {
  const op = useOperation();
  const [courses, setCourses] = useState<Item[] | null>(null), [selected, setSelected] = useState<number | null>(null), [title, setTitle] = useState(''), [capacity, setCapacity] = useState('50');
  const [invitations, setInvitations] = useState<Invitation[]>([]), [next, setNext] = useState<string | null>(null);
  async function loadInvitations(more = false) { const page = await apiRequest<Result<Invitation>>(more && next ? path(next) : 'learning/classroom-invitations/'); setInvitations(current => more ? [...current, ...page.results] : page.results); setNext(page.next); }
  return <View style={styles.panel}>
    <Text style={styles.heading}>Classroom invitations</Text>
    <Text>Accepting an invitation enrolls you in its course. Session admission is separate.</Text>
    <Button label="Refresh invitations" disabled={op.busy} action={() => void op.run(() => loadInvitations())} />
    {invitations.map(invitation => <View key={invitation.id} style={styles.panel}><Text>{invitation.classroom_title} · {invitation.status}{invitation.is_expired ? ' · expired' : ''}</Text><Text>{invitation.message}</Text>
      {invitation.status === 'PENDING' && !invitation.is_expired && <View style={styles.row}>{['accept', 'decline'].map(action => <Button key={action} label={action === 'accept' ? 'Accept invitation' : 'Decline invitation'} disabled={op.busy} action={() => void op.run(async () => { await apiRequest(`learning/classroom-invitations/${invitation.id}/${action}/`, { method: 'POST', body: {} }); await loadInvitations(); await refresh(); })} />)}</View>}
    </View>)}
    {!!next && <Button label="More invitations" disabled={op.busy} action={() => void op.run(() => loadInvitations(true))} />}
    <Button label="Create classroom" disabled={op.busy} action={() => void op.run(async () => { setCourses(await apiRequest<Item[]>('learning/courses/me/')); })} />
    {courses && <><Text style={styles.heading}>Choose your course</Text>{!courses.length && <Text>Create a course in Learning Studio first.</Text>}{courses.map(course => <Button key={course.id} label={`${selected === course.id ? '✓ ' : ''}${course.title}`} action={() => setSelected(course.id)} />)}
      <Input label="Classroom title" value={title} change={setTitle} /><Input label="Seats" value={capacity} change={setCapacity} numeric />
      <Button label="Save classroom" disabled={op.busy || !selected || !title.trim()} action={() => void op.run(async () => { await apiRequest('learning/classrooms/', { method: 'POST', body: { course: selected, title, capacity: positive(capacity) } }); setCourses(null); setTitle(''); await refresh(); })} />
    </>}
    {!!op.message && <Text accessibilityRole="alert">{op.message}</Text>}
  </View>;
}
export function RoomManagement({ room, refresh }: { room: Room; refresh: () => Promise<void> }) {
  const op = useOperation();
  const [lessons, setLessons] = useState<Item[] | null>(null), [lesson, setLesson] = useState<number | null>(null), [title, setTitle] = useState(''), [start, setStart] = useState(''), [end, setEnd] = useState('');
  const [inviteOpen, setInviteOpen] = useState(false), [recipient, setRecipient] = useState<SearchUser | null>(null), [message, setMessage] = useState('');
  const [staffOpen, setStaffOpen] = useState(false), [user, setUser] = useState<SearchUser | null>(null), [staff, setStaff] = useState<Staff[]>([]), [staffNext, setStaffNext] = useState<string | null>(null);
  const [sent, setSent] = useState<Invitation[]>([]), [sentNext, setSentNext] = useState<string | null>(null);
  const base = `learning/classrooms/${room.id}/`;
  async function loadStaff(more = false) { const page = await apiRequest<Result<Staff>>(more && staffNext ? path(staffNext) : base + 'staff/'); setStaff(current => more ? [...current, ...page.results] : page.results); setStaffNext(page.next); }
  async function loadSent(more = false) { const page = await apiRequest<Result<Invitation>>(more && sentNext ? path(sentNext) : base + 'invitations/'); setSent(current => more ? [...current, ...page.results] : page.results); setSentNext(page.next); }
  if (!room.capabilities?.manage && !room.capabilities?.staff) return null;
  return <View style={styles.panel}>
    {room.capabilities.manage && <>
      <Button label="Schedule session" disabled={op.busy} action={() => void op.run(async () => { setLessons(await apiRequest<Item[]>(`learning/courses/${room.course}/lessons/`)); })} />
      {lessons && <><Text style={styles.heading}>Schedule session</Text>{!lessons.length && <Text>Add a course lesson before scheduling.</Text>}{lessons.map(item => <Button key={item.id} label={`${lesson === item.id ? '✓ ' : ''}${item.title}`} action={() => setLesson(item.id)} />)}
        <Input label="Session title" value={title} change={setTitle} /><Text>Enter local times as YYYY-MM-DDTHH:mm, or include an explicit timezone offset.</Text>
        <Input label="Starts" value={start} change={setStart} /><Input label="Ends" value={end} change={setEnd} />
        <Button label="Save session" disabled={op.busy || !lesson || !title.trim()} action={() => void op.run(async () => { await apiRequest(base + 'sessions/', { method: 'POST', body: { lesson, title, scheduled_start: date(start), scheduled_end: date(end) } }); setLessons(null); await refresh(); })} />
      </>}
      <Button label="Invite learner" action={() => setInviteOpen(!inviteOpen)} />
      {inviteOpen && <><UsernamePicker room={room.id} purpose="invite" label="Recipient username" selected={recipient} onSelect={setRecipient} /><Input label="Invitation message" value={message} change={setMessage} limit={1000} />
        <Button label="Send invitation" disabled={op.busy || !recipient} action={() => void op.run(async () => { if (!recipient) return; await apiRequest(base + 'invitations/', { method: 'POST', body: { recipient: recipient.id, message } }); setRecipient(null); setMessage(''); await loadSent(); op.setMessage('Invitation sent.'); })} /></>}
      <Button label="Refresh sent invitations" disabled={op.busy} action={() => void op.run(() => loadSent())} />
      {sent.map(invitation => <View key={invitation.id}><Text>@{invitation.recipient_username} · {invitation.status}{invitation.is_expired ? ' · expired' : ''}</Text>
        {invitation.status === 'PENDING' && !invitation.is_expired && <Button label="Revoke invitation" disabled={op.busy} action={() => void op.run(async () => { await apiRequest(base + `invitations/${invitation.id}/revoke/`, { method: 'POST', body: {} }); await loadSent(); })} />}</View>)}
      {!!sentNext && <Button label="More sent invitations" disabled={op.busy} action={() => void op.run(() => loadSent(true))} />}
    </>}
    {room.capabilities.staff && <>
      <Button label="Manage cohosts" disabled={op.busy} action={() => void op.run(async () => { await loadStaff(); setStaffOpen(!staffOpen); })} />
      {staffOpen && <><Text>Staff changes are available while no session is live.</Text><UsernamePicker room={room.id} purpose="cohost" label="Cohost username" selected={user} onSelect={setUser} />
        <Button label="Add cohost" disabled={op.busy || !user} action={() => void op.run(async () => { if (!user) return; await apiRequest(base + 'staff/', { method: 'POST', body: { user: user.id, role: 'COHOST' } }); setUser(null); await loadStaff(); })} />
        {staff.map(member => <View key={member.id}><Text>@{member.username} ({member.display_name}) · {member.role}</Text>{member.role === 'COHOST' && <View style={styles.row}>{[['Remove cohost', 'REMOVE'], ['Make host (current host becomes cohost)', 'HOST']].map(([label, role]) => <Button key={role} label={label} disabled={op.busy} action={() => confirmChange(`${label}: ${member.display_name}?`, () => void op.run(async () => { await apiRequest(base + 'staff/', { method: 'POST', body: { user: member.user, role } }); await loadStaff(); }))} />)}</View>}</View>)}
        {!!staffNext && <Button label="More staff" disabled={op.busy} action={() => void op.run(() => loadStaff(true))} />}
      </>}
    </>}
    {!!op.message && <Text accessibilityRole="alert">{op.message}</Text>}
  </View>;
}
const styles = StyleSheet.create({ panel: { paddingVertical: 10, gap: 10 }, heading: { color: colors.ink, fontSize: 17, fontWeight: '700' }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, button: { backgroundColor: colors.softBlue, padding: 12, borderRadius: 9 }, link: { color: colors.primary, fontWeight: '700' }, input: { borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 10, color: colors.ink } });
