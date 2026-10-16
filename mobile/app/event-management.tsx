import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Category = { id: number; name: string };
type EventItem = { id: number; organizer: number; title: string; status: string; start_date: string; registrations_count: number };
type Registration = { id: number; event: number; event_title: string; talent_name: string; status: string; attendance_marked: boolean };
type Org = { id: number };

const initialForm = { title: '', description: '', event_type: '', location: '', start_date: '', end_date: '', registration_deadline: '', capacity: '' };
const eventTypes = ['WORKSHOP', 'BOOTCAMP', 'AUDITION', 'CONFERENCE', 'TRIAL', 'WEBINAR'];

export default function EventManagementScreen() {
  const { user } = useAuth();
  const [organizationId, setOrganizationId] = useState<number | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [registrations, setRegistrations] = useState<Registration[]>([]);
  const [form, setForm] = useState(initialForm);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [online, setOnline] = useState(false);
  const [meetingLink, setMeetingLink] = useState('');
  const [eventImage, setEventImage] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const [org, categoryList, eventList, registrationList] = await Promise.all([
        apiRequest<Org>('organizations/me/'),
        apiRequest<Category[]>('events/categories/'),
        apiRequest<EventItem[]>('events/my/'),
        apiRequest<Registration[]>('events/registrations/'),
      ]);
      setOrganizationId(org.id);
      setCategories(categoryList);
      setEvents(eventList);
      setRegistrations(registrationList);
      if (!categoryId && categoryList[0]) setCategoryId(categoryList[0].id);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load event management.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, [categoryId]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ORGANIZATION') return <Redirect href="/(tabs)" />;

  function update(field: keyof typeof initialForm, value: string) { setForm((current) => ({ ...current, [field]: value })); }

  async function createEvent() {
    if (working || !categoryId || !form.title.trim() || !form.event_type.trim() || !form.location.trim() || !form.start_date || !form.end_date || !form.registration_deadline) {
      setError('Complete the required event details and choose a category. Use ISO dates, for example 2026-12-31T18:00:00Z.'); return;
    }
    setWorking(true); setError('');
    try {
      const slug = form.title.toLowerCase().trim().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
      const eventData = {
        ...form, slug, category: categoryId, online, meeting_link: online ? meetingLink.trim() : '',
        capacity: form.capacity ? Number(form.capacity) : null, status: 'DRAFT',
      };
      let body: unknown = eventData;
      if (eventImage) {
        const multipart = new FormData();
        Object.entries(eventData).forEach(([key, value]) => {
          if (value !== null && value !== undefined && value !== '') multipart.append(key, String(value));
        });
        multipart.append('image', { uri: eventImage.uri, name: eventImage.name, type: eventImage.mimeType || 'image/jpeg' } as unknown as Blob);
        body = multipart;
      }
      const created = await apiRequest<EventItem>('events/create/', { method: 'POST', body });
      setEvents((current) => [created, ...current]);
      setForm(initialForm); setMeetingLink(''); setOnline(false); setEventImage(null);
      setError('Event draft saved.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to create the event.'); }
    finally { setWorking(false); }
  }

  async function changeEventStatus(event: EventItem, status: string) {
    setWorking(true); setError('');
    try {
      const updated = await apiRequest<EventItem>(`events/${event.id}/update/`, { method: 'PUT', body: { status } });
      setEvents((current) => current.map((item) => item.id === updated.id ? updated : item));
      if (status === 'PUBLISHED') setError('Event published.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update event status.'); }
    finally { setWorking(false); }
  }

  async function setRegistrationStatus(registration: Registration, status: 'APPROVED' | 'REJECTED') {
    setWorking(true); setError('');
    try {
      const updated = await apiRequest<Registration>(`events/registrations/${registration.id}/status/`, { method: 'PATCH', body: { status } });
      setRegistrations((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update registration.'); }
    finally { setWorking(false); }
  }

  async function markAttendance(registration: Registration) {
    setWorking(true); setError('');
    try {
      await apiRequest(`events/registrations/${registration.id}/attendance/`, { method: 'POST' });
      setRegistrations((current) => current.map((item) => item.id === registration.id ? { ...item, status: 'ATTENDED', attendance_marked: true } : item));
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to mark attendance.'); }
    finally { setWorking(false); }
  }

  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Manage events', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="ORGANIZATION" title="Manage events" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && !organizationId ? <EmptyState title="Event management unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        <Text style={styles.section}>Create an event draft</Text>
        {categories.length === 0 ? <Text style={styles.meta}>No event categories are available from the backend.</Text> : <View style={styles.categoryRow}>{categories.map((category) => <Pressable key={category.id} onPress={() => setCategoryId(category.id)} style={[styles.category, categoryId === category.id && styles.categorySelected]}><Text style={[styles.categoryText, categoryId === category.id && styles.categoryTextSelected]}>{category.name}</Text></Pressable>)}</View>}
        <TextInput placeholder="Event title" placeholderTextColor={colors.muted} style={styles.input} value={form.title} onChangeText={(v) => update('title', v)} />
        <Text style={styles.meta}>Event type</Text><View style={styles.categoryRow}>{eventTypes.map((type) => <Pressable key={type} onPress={() => update('event_type', type)} style={[styles.category, form.event_type === type && styles.categorySelected]}><Text style={[styles.categoryText, form.event_type === type && styles.categoryTextSelected]}>{type.replaceAll('_', ' ')}</Text></Pressable>)}</View>
        <TextInput placeholder="Description" placeholderTextColor={colors.muted} multiline style={[styles.input, styles.multiline]} value={form.description} onChangeText={(v) => update('description', v)} />
        <TextInput placeholder="Location" placeholderTextColor={colors.muted} style={styles.input} value={form.location} onChangeText={(v) => update('location', v)} />
        {(['start_date', 'end_date', 'registration_deadline'] as const).map((field) => <TextInput key={field} accessibilityLabel={field.replaceAll('_', ' ')} placeholder={`${field.replaceAll('_', ' ')} (ISO 8601)`} placeholderTextColor={colors.muted} style={styles.input} value={form[field]} onChangeText={(v) => update(field, v)} />)}
        <TextInput keyboardType="number-pad" placeholder="Capacity (optional)" placeholderTextColor={colors.muted} style={styles.input} value={form.capacity} onChangeText={(v) => update('capacity', v)} />
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: online }} onPress={() => setOnline((value) => !value)} style={styles.toggle}><Text style={styles.meta}>{online ? 'Online event' : 'In-person event'} — tap to change</Text></Pressable>
        {online && <TextInput placeholder="Meeting link" placeholderTextColor={colors.muted} style={styles.input} value={meetingLink} onChangeText={setMeetingLink} />}
        <Pressable accessibilityRole="button" onPress={async () => { const picked = await DocumentPicker.getDocumentAsync({ type: 'image/*', copyToCacheDirectory: true }); if (!picked.canceled) setEventImage(picked.assets[0]); }} style={styles.toggle}><Text style={styles.meta}>{eventImage?.name || 'Choose event image (optional)'}</Text></Pressable>
        <Pressable disabled={working} onPress={() => void createEvent()} style={[styles.button, working && styles.disabled]}><Text style={styles.buttonText}>{working ? 'Saving...' : 'Save draft'}</Text></Pressable>
        <Text style={styles.section}>My events and drafts</Text>
        {events.length ? events.map((event) => <View key={event.id} style={styles.card}><Text style={styles.cardTitle}>{event.title}</Text><Text style={styles.meta}>{event.status} · {event.registrations_count} registrations</Text>{event.status === 'DRAFT' && <Pressable disabled={working} onPress={() => void changeEventStatus(event, 'PUBLISHED')} style={styles.button}><Text style={styles.buttonText}>Publish event</Text></Pressable>}{event.status === 'PUBLISHED' && <Pressable disabled={working} onPress={() => void changeEventStatus(event, 'CLOSED')} style={styles.secondary}><Text style={styles.secondaryText}>Close registration</Text></Pressable>}</View>) : <Text style={styles.meta}>Create an event draft above; your organization’s events will remain available here.</Text>}
        <Text style={styles.section}>Registration management</Text>
        {registrations.length ? registrations.map((item) => <View key={item.id} style={styles.card}><Text style={styles.cardTitle}>{item.talent_name}</Text><Text style={styles.meta}>{item.event_title} · {item.status}</Text><View style={styles.actions}>{item.status === 'REGISTERED' && <><Pressable disabled={working} onPress={() => void setRegistrationStatus(item, 'APPROVED')} style={styles.button}><Text style={styles.buttonText}>Approve</Text></Pressable><Pressable disabled={working} onPress={() => void setRegistrationStatus(item, 'REJECTED')} style={styles.secondary}><Text style={styles.secondaryText}>Reject</Text></Pressable></>}{item.status === 'APPROVED' && !item.attendance_marked && <Pressable disabled={working} onPress={() => void markAttendance(item)} style={styles.button}><Text style={styles.buttonText}>Mark attended</Text></Pressable>}</View></View>) : <Text style={styles.meta}>No event registrations yet.</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.notice}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, meta: { color: colors.muted, fontSize: 12, lineHeight: 18 }, input: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, minHeight: 44, paddingHorizontal: 12 }, multiline: { minHeight: 90, paddingVertical: 10, textAlignVertical: 'top' }, categoryRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 }, category: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, padding: 9 }, categorySelected: { backgroundColor: colors.softBlue, borderColor: colors.primary }, categoryText: { color: colors.muted, fontSize: 11 }, categoryTextSelected: { color: colors.primary, fontWeight: '800' }, toggle: { backgroundColor: colors.softBlue, borderRadius: 10, padding: 11 }, button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 10, flex: 1, justifyContent: 'center', minHeight: 42, paddingHorizontal: 10 }, buttonText: { color: '#fff', fontSize: 11, fontWeight: '800' }, secondary: { alignItems: 'center', backgroundColor: '#fff0ef', borderRadius: 10, flex: 1, justifyContent: 'center', minHeight: 42, paddingHorizontal: 10 }, secondaryText: { color: colors.danger, fontSize: 11, fontWeight: '800' }, disabled: { opacity: 0.55 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 14, borderWidth: 1, gap: 8, padding: 12 }, cardTitle: { color: colors.ink, fontSize: 13, fontWeight: '800' }, actions: { flexDirection: 'row', gap: 8 }, notice: { color: colors.primary, fontSize: 12 } });
