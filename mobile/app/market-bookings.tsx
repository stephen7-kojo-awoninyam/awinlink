import { useEffect, useState } from 'react';
import { Button, Platform, Switch, Text, TextInput, View } from 'react-native';
import { Link, Redirect, useLocalSearchParams } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page } from '@/src/components/Page';
import { savePrivateArtifact } from '@/src/marketplace/files';

type Results<T> = { results: T[]; next: string | null };
type Window = { id: number; starts_at: string; ends_at: string; timezone: string };
type Booking = { id: number; title: string; status: string; amount: string; currency: string;
  starts_at: string; ends_at: string; snapshot: { terms: string }; capabilities: Record<string, boolean>;
  review: { rating: number; text: string; published: boolean } | null };
type Messages = { messages: { id: number; author: number; body: string }[]; next_before: number | null };
type Submission = { id: number; sequence: number; summary: string; artifact_name: string };
type Activity = { id: number; action: string; reason: string; created_at: string };
const relative = (next: string | null) => next ? next.split('/api/marketplace/')[1] : null;

export default function MarketBookings() {
  const { user, isLoading } = useAuth(), params = useLocalSearchParams<{ booking?: string }>();
  const [items, setItems] = useState<Booking[]>([]), [next, setNext] = useState<string | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [windows, setWindows] = useState<Window[]>([]), [windowNext, setWindowNext] = useState<string | null>(null);
  const [start, setStart] = useState(''), [end, setEnd] = useState(''), [zone, setZone] = useState('UTC');
  const [messages, setMessages] = useState<Messages>({ messages: [], next_before: null }), [body, setBody] = useState('');
  const [submissions, setSubmissions] = useState<Submission[]>([]), [submissionNext, setSubmissionNext] = useState<string | null>(null);
  const [summary, setSummary] = useState(''), [reason, setReason] = useState(''), [rating, setRating] = useState('5'), [review, setReview] = useState('');
  const [publish, setPublish] = useState(false), [file, setFile] = useState<DocumentPicker.DocumentPickerAsset | null>(null);
  const [events, setEvents] = useState<Activity[]>([]), [eventNext, setEventNext] = useState<string | null>(null);
  async function request<T>(path: string, body?: object, method = 'POST') {
    return apiRequest<T>('marketplace/' + path, body ? { method, body } : method === 'DELETE' ? { method } : undefined);
  }
  async function run(fn: () => Promise<void>) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); } finally { setBusy(false); } }
  async function load(path = 'bookings/') { const d = await request<Results<Booking>>(path); setItems(d.results); setNext(relative(d.next)); }
  async function loadWindows(path = 'availability/') { const d = await request<Results<Window>>(path); setWindows(d.results); setWindowNext(relative(d.next)); }
  async function open(id: number) {
    const data = await request<Booking>(`bookings/${id}/`);
    const [chat, deliveries, activity] = await Promise.all([request<Messages>(`bookings/${id}/messages/`), request<Results<Submission>>(`bookings/${id}/submissions/`), request<Results<Activity>>(`bookings/${id}/events/`)]);
    setBooking(data); setMessages(chat); setSubmissions(deliveries.results); setSubmissionNext(relative(deliveries.next)); setReason('');
    setEvents(activity.results); setEventNext(relative(activity.next));
  }
  useEffect(() => { if (user) void run(async () => { await load(); if (params.booking && /^\d+$/.test(params.booking)) await open(Number(params.booking)); }); }, [user, params.booking]);
  if (!isLoading && !user) return <Redirect href="/login" />;
  const input = (label: string, value: string, setter: (v: string) => void) => <TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={setter} multiline style={{ borderWidth: 1, padding: 10, marginVertical: 5, color: '#172b4d', backgroundColor: '#fff' }} />;
  const button = (title: string, fn: () => Promise<void>) => <Button title={title} disabled={busy} onPress={() => void run(fn)} />;
  return <Page title="Talent Market bookings"><Link href="/marketplace">Listings and pricing</Link><Text>No online payments.</Text><Text accessibilityRole="alert">{error}</Text>
    <Text style={{ fontSize: 22 }}>My availability</Text><Text>Enter ISO dates with Z or an explicit UTC offset. Openings apply across all your listings.</Text>
    {input('Opening starts', start, setStart)}{input('Opening ends', end, setEnd)}{input('Display timezone', zone, setZone)}
    {button('Add opening', async () => { await request('availability/', { starts_at: start, ends_at: end, timezone: zone }); await loadWindows(); })}
    {button('My openings', () => loadWindows())}{windows.map(w => <View key={w.id}><Text>{w.starts_at} - {w.ends_at} ({w.timezone})</Text>{button('Delete opening', async () => { await request(`availability/${w.id}/`, undefined, 'DELETE'); await loadWindows(); })}</View>)}
    {windowNext && button('Next openings', () => loadWindows(windowNext))}
    {button('My bookings', () => load())}{items.map(b => <View key={b.id}>{button(`#${b.id}: ${b.title} - ${b.status}`, () => open(b.id))}</View>)}{next && button('Next bookings', () => load(next))}
    {booking && <View><Text style={{ fontSize: 22 }}>Booking #{booking.id}: {booking.title}</Text><Text>{booking.status}: {booking.amount} {booking.currency}</Text><Text>{booking.starts_at} - {booking.ends_at}</Text><Text>{booking.snapshot.terms}</Text>
      <Text>Either participant may cancel before the appointment starts. No cancellation after work starts.</Text>
      {button('Refresh booking', () => open(booking.id))}{input('Reason for cancellation or changes', reason, setReason)}
      {(['START', 'COMPLETE', 'REQUEST_CHANGES', 'CANCEL'] as const).filter(action => booking.capabilities[action.toLowerCase()]).map(action => <View key={action}>{button(action, async () => { await request(`bookings/${booking.id}/`, { action, reason }); await open(booking.id); await load(); })}</View>)}
      <Text style={{ fontSize: 20 }}>Activity</Text>{events.map(e => <Text key={e.id}>{e.created_at}: {e.action} {e.reason}</Text>)}
      {eventNext && button('Older activity', async () => { const d = await request<Results<Activity>>(eventNext); setEvents(current => [...current, ...d.results]); setEventNext(relative(d.next)); })}
      <Text style={{ fontSize: 20 }}>Fulfillment conversation</Text>{messages.messages.map(m => <Text key={m.id}>{m.author}: {m.body}</Text>)}
      {messages.next_before !== null && button('Load older messages', async () => { const d = await request<Messages>(`bookings/${booking.id}/messages/?before=${messages.next_before}`); setMessages(current => ({ messages: [...d.messages, ...current.messages], next_before: d.next_before })); })}
      {booking.capabilities.message && <>{input('Message', body, setBody)}{button('Send message', async () => { await request(`bookings/${booking.id}/messages/`, { body }); setBody(''); await open(booking.id); })}</>}
      <Text style={{ fontSize: 20 }}>Deliveries</Text>{submissions.map(s => <View key={s.id}><Text>Delivery {s.sequence}: {s.summary}</Text>{!!s.artifact_name && button(`Save ${s.artifact_name}`, async () => { const data = await request<{filename: string; content: string}>(`bookings/${booking.id}/submissions/${s.id}/artifact/?encoding=base64`); await savePrivateArtifact(data); })}</View>)}
      {submissionNext && button('Older deliveries', async () => { const d = await request<Results<Submission>>(submissionNext); setSubmissions(current => [...current, ...d.results]); setSubmissionNext(relative(d.next)); })}
      {booking.capabilities.submit && <>{input('Delivery summary', summary, setSummary)}{button(file ? `Attached: ${file.name}` : 'Attach private file (up to 2 MiB)', async () => { const d = await DocumentPicker.getDocumentAsync({ copyToCacheDirectory: true }); if (!d.canceled) { if ((d.assets[0].size || 0) > 2 * 1024 * 1024) throw Error('Attachments may be at most 2 MiB.'); setFile(d.assets[0]); } })}
        {file && button('Remove attachment', async () => setFile(null))}
        {button('Submit delivery', async () => { const data = new FormData(); data.append('summary', summary); if (file) data.append('artifact', Platform.OS === 'web' && file.file ? file.file : { uri: file.uri, name: file.name, type: file.mimeType || 'application/octet-stream' } as unknown as Blob); await request(`bookings/${booking.id}/submissions/`, data); setSummary(''); setFile(null); await open(booking.id); })}</>}
      {booking.review && <Text>{booking.review.rating}/5: {booking.review.text}</Text>}
      {booking.capabilities.manage_review && button(booking.review?.published ? 'Make review private' : 'Publish review', async () => { await request(`bookings/${booking.id}/reviews/`, { publish: !booking.review?.published }, 'PATCH'); await open(booking.id); })}
      {booking.capabilities.review && <>{input('Rating (1-5)', rating, setRating)}{input('Review', review, setReview)}<Text>Publish as a verified buyer</Text><Switch accessibilityLabel="Publish review" value={publish} onValueChange={setPublish} />{button('Save review', async () => { await request(`bookings/${booking.id}/reviews/`, { rating: Number(rating), text: review, publish }); setReview(''); setPublish(false); await open(booking.id); })}</>}
    </View>}
  </Page>;
}
