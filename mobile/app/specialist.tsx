import { useScopedState } from '@/src/privacy-state';
import { LoadMore } from '@/src/components/LoadMore';
import { useSearchPath } from '@/src/search-query';
import { useCallback, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useFocusEffect, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';
import type { TalentProfile } from '@/src/types';

type Bookmark = { id: number; talent: number; talent_name: string; notes: string };
type Follow = { id: number; talent: number; talent_name: string };

export default function SpecialistScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const role = user?.role;
  const base = role === 'SCOUT' ? 'scouts' : 'coaches';
  const title = role === 'SCOUT' ? 'Scout tools' : 'Coach tools';
  const scope = `${user?.id}:${role}`;
  const [profiles, setProfiles] = useScopedState<TalentProfile[]>(scope, []);
  const [bookmarks, setBookmarks] = useScopedState<Bookmark[]>(scope, []);
  const [following, setFollowing] = useScopedState<Follow[]>(scope, []);
  const [query, setQuery] = useState('');
  const endpoint = useSearchPath(`${base}/talents/`, query);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const [error, setError] = useState('');
  const dataRevision = useRef(0);
  const loadGeneration = useRef(0);
  const load = useCallback(async () => {
    if (role !== 'SCOUT' && role !== 'COACH') return;
    const revision = dataRevision.current;
    const generation = ++loadGeneration.current;
    setError('');
    try {
      const [talents, saved, followed] = await Promise.all([
        apiRequest<TalentProfile[]>(endpoint),
        apiRequest<Bookmark[]>(`${base}/talents/bookmarks/`),
        apiRequest<Follow[]>(`${base}/talents/following/`),
      ]);
      if (revision === dataRevision.current && generation === loadGeneration.current) {
        setProfiles(talents); setBookmarks(saved); setFollowing(followed);
      }
    } catch (e) {
      if (revision === dataRevision.current && generation === loadGeneration.current) {
        setError(e instanceof Error ? e.message : 'Unable to load specialist tools.');
      }
    }
    finally {
      if (generation === loadGeneration.current) { setLoading(false); setRefreshing(false); }
    }
  }, [base, role, endpoint, scope]);
  useFocusEffect(useCallback(() => { void load(); return () => { ++loadGeneration.current; }; }, [load]));
  const filtered = useMemo(() => {
    const needle = query.trim().replace(/^@/, '').toLowerCase();
    return profiles.filter((p) => !needle || [p.user.username, p.user.first_name, p.user.last_name, p.headline, p.talent_area, p.talent_category, p.country].filter(Boolean).join(' ').toLowerCase().includes(needle));
  }, [profiles, query]);
  if (!user) return <Redirect href="/login" />;
  if (role !== 'SCOUT' && role !== 'COACH') return <Redirect href="/(tabs)" />;

  async function toggleBookmark(profile: Pick<TalentProfile, 'id' | 'specialist_bookmark_id'>) {
    const existing = bookmarks.find((item) => item.talent === profile.id)
      || (profile.specialist_bookmark_id ? { id: profile.specialist_bookmark_id } : null);
    setWorkingId(profile.id); setError('');
    try {
      if (existing) {
        await apiRequest(`${base}/bookmarks/${existing.id}/delete/`, { method: 'DELETE' });
        setBookmarks((current) => current.filter((item) => item.id !== existing.id));
        setProfiles(current => current.map(item => item.id === profile.id ? { ...item, specialist_bookmark_id: null } : item));
      } else {
        const saved = await apiRequest<Bookmark>(`${base}/talents/${profile.id}/bookmark/`, { method: 'POST', body: { notes: '' } });
        setBookmarks((current) => [saved, ...current]);
        setProfiles(current => current.map(item => item.id === profile.id ? { ...item, specialist_bookmark_id: saved.id } : item));
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update saved talents.'); }
    finally { setWorkingId(null); }
  }

  async function toggleFollow(profile: Pick<TalentProfile, 'id' | 'specialist_follow_id'>) {
    const existing = following.find((item) => item.talent === profile.id) || profile.specialist_follow_id;
    setWorkingId(profile.id); setError('');
    try {
      if (existing) {
        await apiRequest(`${base}/talents/${profile.id}/unfollow/`, { method: 'DELETE' });
        dataRevision.current += 1;
        setFollowing((current) => current.filter((item) => item.talent !== profile.id));
        setProfiles(current => current.map(item => item.id === profile.id ? { ...item, specialist_follow_id: null } : item));
      } else {
        const result = await apiRequest<Follow>(`${base}/talents/${profile.id}/follow/`, { method: 'POST' });
        dataRevision.current += 1;
        setFollowing((current) => [result, ...current.filter((item) => item.talent !== profile.id)]);
        setProfiles(current => current.map(item => item.id === profile.id ? { ...item, specialist_follow_id: result.id } : item));
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update followed talents.'); }
    finally { setWorkingId(null); }
  }

  const cards = (items: TalentProfile[]) => items.map((profile) => {
    const name = [profile.user.first_name, profile.user.last_name].filter(Boolean).join(' ') || profile.user.username;
    const saved = bookmarks.some((item) => item.talent === profile.id) || !!profile.specialist_bookmark_id;
    const followed = following.some((item) => item.talent === profile.id) || !!profile.specialist_follow_id;
    return <View key={profile.id} style={styles.card}>
      <Pressable style={styles.personRow} onPress={() => router.push({ pathname: '/talent/[id]', params: { id: String(profile.id) } })}>
        {profile.profile_photo || profile.user.profile_picture ? <Image source={{ uri: profile.profile_photo || profile.user.profile_picture || '' }} style={styles.avatar} /> : <View style={[styles.avatar, styles.avatarFallback]}><Text style={styles.initial}>{name.charAt(0).toUpperCase()}</Text></View>}
        <View style={styles.copy}><Text style={styles.person}>{name}</Text><Text style={styles.username}>@{profile.user.username}</Text><Text numberOfLines={1} style={styles.meta}>{profile.headline || profile.talent_area || profile.talent_category || 'Talent'} · {profile.country || profile.user.country || 'Location not set'}</Text></View>
      </Pressable>
      <View style={styles.actions}>
        <Pressable disabled={workingId !== null} onPress={() => void toggleFollow(profile)} style={styles.action}><Text style={styles.actionText}>{workingId === profile.id ? 'Working...' : followed ? 'Following' : 'Follow talent'}</Text></Pressable>
        <Pressable disabled={workingId !== null} onPress={() => void toggleBookmark(profile)} style={styles.action}><Text style={styles.actionText}>{saved ? 'Remove saved' : 'Save talent'}</Text></Pressable>
      </View>
    </View>;
  });

  return <>
    <Stack.Screen options={{ headerShown: true, title, headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow={role === 'SCOUT' ? 'SCOUT WORKSPACE' : 'COACH WORKSPACE'} title={title} refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      <Text style={styles.intro}>Browse public talent profiles, follow talents, and keep a private bookmark list.</Text>
      <TextInput accessibilityLabel="Search talent" autoCapitalize="none" onChangeText={setQuery} placeholder="Search talent" placeholderTextColor={colors.muted} style={styles.search} value={query} />
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && profiles.length === 0 ? <EmptyState title="Specialist tools unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        <Text style={styles.section}>Talent directory</Text>
        {filtered.length ? cards(filtered) : <Text style={styles.meta}>No matching public talents found.</Text>}
        <Text style={styles.section}>Saved talents ({bookmarks.length} loaded)</Text>
        {bookmarks.map(item => <View key={item.id} style={styles.card}><Pressable onPress={() => router.push({ pathname: '/talent/[id]', params: { id: String(item.talent) } })}><Text style={styles.person}>{item.talent_name}</Text><Text style={styles.meta}>{item.notes}</Text></Pressable><Pressable disabled={workingId !== null} onPress={() => void toggleBookmark({ id: item.talent, specialist_bookmark_id: item.id })}><Text style={styles.actionText}>Remove saved</Text></Pressable></View>)}
        {!bookmarks.length && <Text style={styles.meta}>Your saved talents will appear here.</Text>}
        <Text style={styles.section}>Following ({following.length} loaded)</Text>
        {following.map(item => <View key={item.id} style={styles.card}><Pressable onPress={() => router.push({ pathname: '/talent/[id]', params: { id: String(item.talent) } })}><Text style={styles.person}>{item.talent_name}</Text></Pressable><Pressable disabled={workingId !== null} onPress={() => void toggleFollow({ id: item.talent, specialist_follow_id: item.id })}><Text style={styles.actionText}>Unfollow</Text></Pressable></View>)}
        {!following.length && <Text style={styles.meta}>Talents you follow will appear here.</Text>}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}

      <LoadMore items={profiles} onChange={setProfiles} label="Load more profiles" />
      <LoadMore items={bookmarks} onChange={setBookmarks} label="Load more bookmarks" />
      <LoadMore items={following} onChange={setFollowing} label="Load more following" />
    </Page>
  </>;
}

const styles = StyleSheet.create({ intro: { color: colors.muted, fontSize: 12, lineHeight: 18 }, search: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.ink, minHeight: 48, paddingHorizontal: 13 }, loader: { marginTop: 24 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 10, padding: 12 }, personRow: { alignItems: 'center', flexDirection: 'row', gap: 10 }, avatar: { backgroundColor: colors.softBlue, borderRadius: 22, height: 44, width: 44 }, avatarFallback: { alignItems: 'center', justifyContent: 'center' }, initial: { color: colors.primary, fontSize: 17, fontWeight: '800' }, copy: { flex: 1, gap: 3 }, person: { color: colors.ink, fontSize: 13, fontWeight: '800' }, username: { color: colors.primary, fontSize: 11 }, meta: { color: colors.muted, fontSize: 11 }, actions: { flexDirection: 'row', gap: 8 }, action: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 9, flex: 1, padding: 9 }, actionText: { color: colors.primary, fontSize: 11, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
