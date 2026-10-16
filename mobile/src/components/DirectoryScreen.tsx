import { useCallback, useMemo, useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

export type DirectoryKind = 'competitions' | 'events';
type DirectoryItem = {
  id: number;
  title: string;
  description: string;
  status?: string;
  organization_name?: string;
  organizer_name?: string;
  category?: string;
  category_name?: string;
  discipline?: string;
  location?: string;
  online?: boolean;
  registration_start?: string;
  registration_end?: string;
  registration_deadline?: string | null;
  competition_start?: string;
  competition_end?: string;
  start_date?: string;
  end_date?: string;
  registration_open?: boolean;
  participant_count?: number;
  registrations_count?: number;
  prizes?: string;
  requirements?: string;
  rules?: string;
};
type Registration = { id: number; event?: number; competition?: number; status?: string; attendance_marked?: boolean; submission?: string; submission_url?: string; submitted_at?: string | null };
type CompetitionResult = { id: number; position: number | null; score: string | null; award: string; participant: { id: number; talent: { id: number; name: string } } };
type EventFeedback = { id: number; reviewer_name: string; rating: number; comment: string };
type EventMedia = { id: number; media_type: string; file: string; caption: string };

export function DirectoryScreen({ kind }: { kind: DirectoryKind }) {
  const { user } = useAuth();
  const router = useRouter();
  const [items, setItems] = useState<DirectoryItem[]>([]);
  const [registered, setRegistered] = useState<Set<number>>(new Set());
  const [myEntries, setMyEntries] = useState<Registration[]>([]);
  const [results, setResults] = useState<CompetitionResult[]>([]);
  const [submission, setSubmission] = useState('');
  const [submissionUrl, setSubmissionUrl] = useState('');
  const [feedback, setFeedback] = useState<EventFeedback[]>([]);
  const [media, setMedia] = useState<EventMedia[]>([]);
  const [rating, setRating] = useState('5');
  const [comment, setComment] = useState('');
  const [mediaWorking, setMediaWorking] = useState(false);
  const [selected, setSelected] = useState<DirectoryItem | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const noun = kind === 'competitions' ? 'competition' : 'event';
  const title = kind === 'competitions' ? 'Competitions' : 'Events';
  const endpoint = kind === 'competitions' ? 'competitions/' : 'events/';
  const registrationsEndpoint = kind === 'competitions' ? 'competitions/my/' : 'events/my-registrations/';

  const load = useCallback(async () => {
    setError('');
    try {
      const results = await apiRequest<DirectoryItem[]>(endpoint);
      setItems(results);
      if (user?.role === 'ATHLETE') {
        const mine = await apiRequest<Registration[]>(registrationsEndpoint);
        setMyEntries(mine);
        setRegistered(new Set(mine.filter((registration) => !['CANCELLED', 'REJECTED', 'WITHDRAWN'].includes(registration.status || '')).map((registration) =>
          kind === 'competitions' ? registration.competition : registration.event,
        ).filter((id): id is number => typeof id === 'number')));
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : `Unable to load ${title.toLowerCase()}.`);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [endpoint, kind, registrationsEndpoint, title, user?.role]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const visibleItems = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return items.filter((item) =>
      [item.title, item.description, item.organization_name, item.organizer_name, item.category_name, item.discipline, item.location]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase()
        .includes(term),
    );
  }, [items, query]);

  async function register() {
    if (!selected || working) return;
    setWorking(true);
    setActionError('');
    try {
      await apiRequest(`${kind}/${selected.id}/register/`, { method: 'POST' });
      setRegistered((current) => new Set(current).add(selected.id));
    } catch (registerError) {
      setActionError(registerError instanceof Error ? registerError.message : `Unable to register for this ${noun}.`);
    } finally {
      setWorking(false);
    }
  }

  async function saveSubmission() {
    if (!selected || working) return;
    setWorking(true);
    setActionError('');
    try {
      const result = await apiRequest<Registration>(`competitions/${selected.id}/submission/`, {
        method: 'PATCH',
        body: { submission: submission.trim(), submission_url: submissionUrl.trim() },
      });
      setMyEntries((current) => current.map((entry) => entry.competition === selected.id ? { ...entry, ...result } : entry));
      setActionError('Submission saved.');
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Unable to save submission.');
    } finally {
      setWorking(false);
    }
  }

  async function loadResults(item: DirectoryItem) {
    if (kind !== 'competitions' || !['RESULTS', 'COMPLETED'].includes(item.status || '')) return;
    try {
      setResults(await apiRequest<CompetitionResult[]>(`competitions/${item.id}/results/`));
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Unable to load results.');
    }
  }

  async function loadEventDetails(item: DirectoryItem) {
    if (kind !== 'events') return;
    const [feedbackResult, mediaResult] = await Promise.allSettled([
      apiRequest<EventFeedback[]>(`events/${item.id}/feedback/list/`),
      apiRequest<EventMedia[]>(`events/${item.id}/media/`),
    ]);
    if (feedbackResult.status === 'fulfilled') setFeedback(feedbackResult.value);
    if (mediaResult.status === 'fulfilled') setMedia(mediaResult.value);
  }

  async function cancelEventRegistration() {
    if (!selected || working) return;
    setWorking(true); setActionError('');
    try {
      await apiRequest(`events/${selected.id}/cancel-registration/`, { method: 'POST' });
      setRegistered((current) => { const next = new Set(current); next.delete(selected.id); return next; });
      setMyEntries((current) => current.map((entry) => entry.event === selected.id ? { ...entry, status: 'CANCELLED' } : entry));
    } catch (e) { setActionError(e instanceof Error ? e.message : 'Unable to cancel registration.'); }
    finally { setWorking(false); }
  }

  async function submitEventFeedback() {
    if (!selected || working) return;
    setWorking(true); setActionError('');
    try {
      const item = await apiRequest<EventFeedback>(`events/${selected.id}/feedback/`, { method: 'POST', body: { rating: Number(rating), comment: comment.trim() } });
      setFeedback((current) => [item, ...current]); setComment(''); setActionError('Feedback submitted.');
    } catch (e) { setActionError(e instanceof Error ? e.message : 'Unable to submit feedback.'); }
    finally { setWorking(false); }
  }

  async function uploadEventMedia() {
    if (!selected || mediaWorking) return;
    const selection = await DocumentPicker.getDocumentAsync({ type: ['image/*', 'video/*'], copyToCacheDirectory: true });
    if (selection.canceled || !selection.assets[0]) return;
    const file = selection.assets[0];
    const form = new FormData();
    form.append('media_type', file.mimeType?.startsWith('video/') ? 'VIDEO' : 'IMAGE');
    form.append('caption', '');
    form.append('file', { uri: file.uri, name: file.name, type: file.mimeType || 'application/octet-stream' } as unknown as Blob);
    setMediaWorking(true); setActionError('');
    try {
      const uploaded = await apiRequest<EventMedia>(`events/${selected.id}/media/upload/`, { method: 'POST', body: form });
      setMedia((current) => [uploaded, ...current]);
    } catch (e) { setActionError(e instanceof Error ? e.message : 'Unable to upload event media.'); }
    finally { setMediaWorking(false); }
  }

  const openForRegistration = kind === 'competitions'
    ? selected?.registration_open === true
    : selected?.status === 'PUBLISHED';

  return (
    <Page eyebrow="EXPLORE YOUR ECOSYSTEM" title={title}
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary}
        onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {kind === 'events' && user?.role === 'ORGANIZATION' && <Pressable accessibilityRole="button" onPress={() => router.push('/event-management')} style={styles.button}><Text style={styles.buttonText}>Manage my events</Text></Pressable>}
      <TextInput accessibilityLabel={`Search ${title.toLowerCase()}`} value={query} onChangeText={setQuery}
        placeholder={`Search ${title.toLowerCase()}`} placeholderTextColor={colors.muted}
        style={styles.search} />
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
        error && items.length === 0 ? <EmptyState title={`${title} unavailable`} message={error}
          actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> :
        selected ? (
          <View style={styles.card}>
            <Pressable accessibilityRole="button" onPress={() => { setSelected(null); setActionError(''); }}>
              <Text style={styles.back}>Back to {title.toLowerCase()}</Text>
            </Pressable>
            <Text style={styles.title}>{selected.title}</Text>
            <Text style={styles.meta}>
              {kind === 'competitions'
                ? [selected.organization_name, selected.category, selected.discipline].filter(Boolean).join(' | ')
                : [selected.organizer_name, selected.category_name].filter(Boolean).join(' | ')}
            </Text>
            <Text style={styles.meta}>
              {kind === 'competitions'
                ? [selected.registration_start, selected.registration_end && `Registration ends ${selected.registration_end}`, selected.competition_start && `Starts ${selected.competition_start}`, selected.competition_end && `Ends ${selected.competition_end}`].filter(Boolean).join(' | ')
                : [selected.start_date, selected.end_date && `Ends ${selected.end_date}`, selected.registration_deadline && `Register by ${selected.registration_deadline}`].filter(Boolean).join(' | ')}
            </Text>
            {!!selected.location && <Text style={styles.meta}>{selected.online ? 'Online' : selected.location}</Text>}
            {!!selected.description && <Text style={styles.description}>{selected.description}</Text>}
            {!!selected.requirements && <Text style={styles.meta}>Requirements: {selected.requirements}</Text>}
            {!!selected.prizes && <Text style={styles.meta}>Prizes: {selected.prizes}</Text>}
            {!!selected.rules && <Text style={styles.meta}>Rules: {selected.rules}</Text>}
            {kind === 'competitions' && typeof selected.participant_count === 'number' &&
              <Text style={styles.meta}>{selected.participant_count} registered</Text>}
            {kind === 'events' && typeof selected.registrations_count === 'number' &&
              <Text style={styles.meta}>{selected.registrations_count} registered</Text>}
            {user?.role === 'ATHLETE' && (registered.has(selected.id) ?
              <Text style={styles.success}>You are registered.</Text> :
              openForRegistration ? (
                <Pressable accessibilityRole="button" disabled={working} onPress={() => void register()}
                  style={[styles.button, working && styles.disabled]}>
                  <Text style={styles.buttonText}>{working ? 'Registering...' : `Register for ${noun}`}</Text>
                </Pressable>
              ) : <Text style={styles.meta}>Registration is not open.</Text>)}
            {kind === 'events' && user?.role === 'ATHLETE' && registered.has(selected.id) && myEntries.find((entry) => entry.event === selected.id)?.status !== 'ATTENDED' && <Pressable accessibilityRole="button" disabled={working} onPress={() => void cancelEventRegistration()} style={styles.secondaryButton}><Text style={styles.secondaryText}>{working ? 'Working...' : 'Cancel registration'}</Text></Pressable>}
            {kind === 'events' && user?.role === 'ATHLETE' && myEntries.find((entry) => entry.event === selected.id)?.status === 'ATTENDED' && <View style={styles.form}>
              <Text style={styles.title}>Leave event feedback</Text>
              <TextInput accessibilityLabel="Rating from 1 to 5" keyboardType="number-pad" onChangeText={setRating} placeholder="Rating (1 to 5)" placeholderTextColor={colors.muted} style={styles.input} value={rating} />
              <TextInput accessibilityLabel="Event feedback comment" onChangeText={setComment} placeholder="Comment" placeholderTextColor={colors.muted} style={styles.input} value={comment} />
              <Pressable accessibilityRole="button" disabled={working} onPress={() => void submitEventFeedback()} style={styles.button}><Text style={styles.buttonText}>Submit feedback</Text></Pressable>
            </View>}
            {kind === 'events' && <View style={styles.form}>
              <Text style={styles.title}>Event media</Text>
              {media.map((item) => <View key={item.id} style={styles.mediaItem}>{item.media_type === 'IMAGE' ? <Image source={{ uri: item.file }} style={styles.mediaImage} /> : <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(item.file)}><Text style={styles.back}>Open video</Text></Pressable>}{!!item.caption && <Text style={styles.meta}>{item.caption}</Text>}</View>)}
              {user?.role === 'ORGANIZATION' && <Pressable accessibilityRole="button" disabled={mediaWorking} onPress={() => void uploadEventMedia()} style={styles.secondaryButton}><Text style={styles.secondaryText}>{mediaWorking ? 'Uploading...' : 'Upload image or video'}</Text></Pressable>}
            </View>}
            {kind === 'events' && feedback.map((item) => <View key={item.id} style={styles.feedbackItem}><Text style={styles.meta}>{item.reviewer_name} · {item.rating}/5</Text><Text style={styles.description}>{item.comment}</Text></View>)}
            {kind === 'competitions' && user?.role === 'ATHLETE' && registered.has(selected.id) && selected.status === 'ONGOING' && (() => {
              const entry = myEntries.find((value) => value.competition === selected.id);
              const deadlineOpen = !selected.competition_end || new Date(`${selected.competition_end}T23:59:59`).getTime() >= Date.now();
              return deadlineOpen ? <View style={styles.form}>
                {!!entry?.submitted_at && <Text style={styles.success}>Last submitted {new Date(entry.submitted_at).toLocaleString()}</Text>}
                <TextInput accessibilityLabel="Competition submission" multiline onChangeText={setSubmission} placeholder="Describe or submit your work" placeholderTextColor={colors.muted} style={styles.input} value={submission} />
                <TextInput accessibilityLabel="Submission URL" autoCapitalize="none" onChangeText={setSubmissionUrl} placeholder="Submission link (optional)" placeholderTextColor={colors.muted} style={styles.input} value={submissionUrl} />
                <Pressable accessibilityRole="button" disabled={working} onPress={() => void saveSubmission()} style={[styles.button, working && styles.disabled]}><Text style={styles.buttonText}>{working ? 'Saving...' : 'Save submission'}</Text></Pressable>
              </View> : <Text style={styles.meta}>The submission deadline has passed.</Text>;
            })()}
            {kind === 'competitions' && ['RESULTS', 'COMPLETED'].includes(selected.status || '') && <View style={styles.form}>
              {results.length === 0 ? <Text style={styles.meta}>No results published.</Text> : results.map((result) => <Text key={result.id} style={styles.meta}>{result.position ? `#${result.position} · ` : ''}{result.participant.talent.name}{result.award ? ` · ${result.award}` : ''}{result.score ? ` · ${result.score}` : ''}</Text>)}
            </View>}
            {!!actionError && <Text accessibilityRole="alert" style={styles.error}>{actionError}</Text>}
          </View>
        ) : visibleItems.length === 0 ? <EmptyState title={`No ${title.toLowerCase()} found`}
          message={items.length ? 'Try another search.' : `New ${title.toLowerCase()} will appear here.`} /> :
        visibleItems.map((item) => (
          <Pressable accessibilityRole="button" key={item.id} onPress={() => { setSelected(item); setResults([]); setFeedback([]); setMedia([]); setSubmission(''); setSubmissionUrl(''); setActionError(''); void loadResults(item); void loadEventDetails(item); }} style={styles.card}>
            <Text style={styles.title}>{item.title}</Text>
            <Text style={styles.meta}>
              {kind === 'competitions'
                ? [item.organization_name, item.category, item.discipline].filter(Boolean).join(' | ')
                : [item.organizer_name, item.category_name, item.start_date].filter(Boolean).join(' | ')}
            </Text>
            <Text numberOfLines={3} style={styles.description}>{item.description}</Text>
            <Text style={styles.open}>View details</Text>
          </Pressable>
        ))}
      {user?.role !== 'ATHLETE' && <Text style={styles.meta}>Registration is available to talent accounts.</Text>}
    </Page>
  );
}

const styles = StyleSheet.create({
  search: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.ink, minHeight: 48, paddingHorizontal: 13 },
  loader: { marginTop: 28 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 9, padding: 15 },
  back: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  title: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  meta: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  description: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  open: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, justifyContent: 'center', minHeight: 46 },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  success: { color: colors.success, fontSize: 13, fontWeight: '700' },
  error: { color: colors.danger, fontSize: 13 },
  form: { gap: 8 },
  input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minHeight: 44, padding: 10, textAlignVertical: 'top' },
  secondaryButton: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 10, minHeight: 42, justifyContent: 'center', paddingHorizontal: 10 },
  secondaryText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  mediaItem: { borderTopColor: colors.border, borderTopWidth: StyleSheet.hairlineWidth, gap: 6, paddingVertical: 8 },
  mediaImage: { borderRadius: 10, height: 190, width: '100%' },
  feedbackItem: { backgroundColor: colors.softBlue, borderRadius: 10, gap: 4, padding: 10 },
});
