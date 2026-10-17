import { useCallback, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Image, Linking, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Organization = {
  id: number; name: string; category_name: string; domain_name: string;
  country: string; city: string; website: string; description: string;
  logo: string | null; followers_count: number;
};
type Follow = { organization_id: number };

export default function OrganizationsScreen() {
  const [items, setItems] = useState<Organization[]>([]);
  const [followed, setFollowed] = useState<Set<number>>(new Set());
  const [selected, setSelected] = useState<Organization | null>(null);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const dataRevision = useRef(0);
  const loadGeneration = useRef(0);

  const load = useCallback(async () => {
    const revision = dataRevision.current;
    const generation = ++loadGeneration.current;
    setError('');
    try {
      const [organizations, follows] = await Promise.all([
        apiRequest<Organization[]>('organizations/'),
        apiRequest<Follow[]>('organizations/following/'),
      ]);
      if (revision === dataRevision.current && generation === loadGeneration.current) {
        setItems(organizations);
        setFollowed(new Set(follows.map((follow) => follow.organization_id)));
      }
    } catch (loadError) {
      if (revision === dataRevision.current && generation === loadGeneration.current) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load organizations.');
      }
    } finally {
      if (generation === loadGeneration.current) { setLoading(false); setRefreshing(false); }
    }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const matches = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return items.filter((item) => [item.name, item.category_name, item.domain_name, item.country, item.city, item.description]
      .filter(Boolean).join(' ').toLocaleLowerCase().includes(term));
  }, [items, query]);

  async function toggleFollow() {
    if (!selected || working) return;
    const target = selected;
    const organizationId = target.id;
    setWorking(true);
    setError('');
    const isFollowed = followed.has(selected.id);
    try {
      const result = await apiRequest<{ followers_count: number }>(`organizations/${organizationId}/${isFollowed ? 'unfollow' : 'follow'}/`, {
        method: isFollowed ? 'DELETE' : 'POST',
      });
      dataRevision.current += 1;
      setFollowed((current) => {
        const next = new Set(current);
        if (isFollowed) next.delete(organizationId); else next.add(organizationId);
        return next;
      });
      setItems((current) => current.map((item) => item.id === organizationId
        ? { ...item, followers_count: result.followers_count } : item));
      setSelected((current) => current?.id === organizationId
        ? { ...current, followers_count: result.followers_count } : current);
    } catch (followError) {
      setError(followError instanceof Error ? followError.message : 'Unable to update follow.');
    } finally { setWorking(false); }
  }

  return (
    <Page eyebrow="YOUR ECOSYSTEM" title="Organizations"
      refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary}
        onRefresh={() => { setRefreshing(true); void load(); }} />}>
      <TextInput accessibilityLabel="Search organizations" value={query} onChangeText={setQuery}
        placeholder="Search organizations or locations" placeholderTextColor={colors.muted} style={styles.search} />
      {!!error && items.length > 0 && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
        error && items.length === 0 ? <EmptyState title="Organizations unavailable" message={error}
          actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> :
        selected ? (
          <View style={styles.card}>
            <Pressable accessibilityRole="button" onPress={() => setSelected(null)}><Text style={styles.back}>All organizations</Text></Pressable>
            {!!selected.logo && <Image source={{ uri: selected.logo }} style={styles.logo} />}
            <Text style={styles.title}>{selected.name}</Text>
            <Text style={styles.meta}>{[selected.category_name, selected.domain_name].filter(Boolean).join(' | ')}</Text>
            <Text style={styles.meta}>{[selected.city, selected.country].filter(Boolean).join(', ')}</Text>
            <Text style={styles.description}>{selected.description || 'No description provided.'}</Text>
            {!!selected.website && <Pressable accessibilityRole="link" onPress={() => {
              try {
                const url = new URL(selected.website);
                if (!['https:', 'http:'].includes(url.protocol)) throw new Error('This website address is invalid.');
                void Linking.openURL(url.href).catch(() => setError('Unable to open this website.'));
              } catch { setError('This website address is invalid.'); }
            }}><Text style={styles.back}>Visit website</Text></Pressable>}
            <Text style={styles.meta}>{selected.followers_count} followers</Text>
            <Pressable accessibilityRole="button" disabled={working} onPress={() => void toggleFollow()}
              style={[styles.button, working && styles.disabled]}>
              <Text style={styles.buttonText}>{working ? 'Updating...' : followed.has(selected.id) ? 'Following' : 'Follow organization'}</Text>
            </Pressable>
          </View>
        ) : matches.length === 0 ? <EmptyState title="No organizations found"
          message={items.length ? 'Try another search.' : 'Organizations will appear here.'} /> :
        matches.map((item) => (
          <Pressable accessibilityRole="button" key={item.id} onPress={() => setSelected(item)} style={styles.row}>
            {!!item.logo && <Image source={{ uri: item.logo }} style={styles.avatar} />}
            <View style={styles.copy}>
              <Text style={styles.title}>{item.name}</Text>
              <Text style={styles.meta}>{[item.category_name, item.city, item.country].filter(Boolean).join(' | ')}</Text>
              <Text style={styles.meta}>{item.followers_count} followers</Text>
            </View>
            {followed.has(item.id) && <Text style={styles.followed}>FOLLOWING</Text>}
          </Pressable>
        ))}
    </Page>
  );
}

const styles = StyleSheet.create({
  search: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.ink, minHeight: 48, paddingHorizontal: 13 },
  loader: { marginTop: 28 },
  row: { alignItems: 'center', backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, flexDirection: 'row', gap: 12, padding: 13 },
  avatar: { backgroundColor: colors.softBlue, borderRadius: 24, height: 48, width: 48 },
  logo: { alignSelf: 'center', borderRadius: 14, height: 80, width: 80 },
  copy: { flex: 1, gap: 4 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 10, padding: 16 },
  back: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  title: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  meta: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  description: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  followed: { color: colors.primary, fontSize: 9, fontWeight: '800' },
  button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, justifyContent: 'center', minHeight: 46 },
  buttonText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  error: { color: colors.danger, fontSize: 12 },
});
