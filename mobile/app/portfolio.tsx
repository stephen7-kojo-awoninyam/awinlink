import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Redirect, Stack, useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useScopedState } from '@/src/privacy-state';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { AuthorizedImage } from '@/src/components/AuthorizedImage';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type PortfolioItem = {
  id: number; title: string; description: string; item_type: string;
  image: string | null; file: string | null; link: string | null; created_at: string;
};

export default function PortfolioScreen() {
  const { user } = useAuth();
  const scope = `${user?.id ?? ''}:${user?.role ?? ''}`;
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const generation = useRef(0);
  const [loadedScope, setLoadedScope] = useState('');
  const [items, setItems] = useScopedState<PortfolioItem[]>(scope, []);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    const version = ++generation.current;
    if (!user || user.role !== 'ATHLETE') return;
    const current = () => currentScope.current === scope && generation.current === version;
    setError('');
    setLoading(true);
    try {
      const result = await apiRequest<PortfolioItem[]>('portfolio/my/');
      if (current()) { setItems(result); setLoadedScope(scope); }
    } catch (loadError) {
      if (current()) {
        setItems([]); setLoadedScope(scope);
        setError(loadError instanceof Error ? loadError.message : 'Unable to load portfolio.');
      }
    } finally { if (current()) { setLoading(false); setRefreshing(false); } }
  }, [scope, user?.id, user?.role]);
  useFocusEffect(useCallback(() => {
    void load();
    return () => { generation.current += 1; };
  }, [load]));
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ATHLETE') return <Redirect href="/(tabs)" />;
  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'My portfolio', headerTintColor: colors.primary,
        headerStyle: { backgroundColor: colors.background }, headerShadowVisible: false }} />
      <Page eyebrow="YOUR WORK" title="Portfolio"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary}
          onRefresh={() => { setRefreshing(true); void load(); }} />}>
        {loading || loadedScope !== scope ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
          error ? <EmptyState title="Portfolio unavailable" message={error} actionLabel="Try again"
            onAction={() => { setLoading(true); void load(); }} /> :
          items.length === 0 ? <EmptyState title="Your portfolio is ready"
            message="Add projects and achievements from the Create tab." /> :
          items.map((item) => (
            <View key={item.id} style={styles.card}>
              {!!item.image && <AuthorizedImage uri={item.image} style={styles.image} />}
              <Text style={styles.type}>{item.item_type}</Text>
              <Text style={styles.title}>{item.title}</Text>
              {!!item.description && <Text style={styles.description}>{item.description}</Text>}
              {!!item.link && <Text numberOfLines={1} style={styles.link}>{item.link}</Text>}
              <Text style={styles.date}>{new Date(item.created_at).toLocaleDateString()}</Text>
            </View>
          ))
        }

      <LoadMore items={items} onChange={setItems} label="Load more items" />
    </Page>
    </>
  );
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 16, borderWidth: 1, gap: 7, overflow: 'hidden', padding: 15 },
  image: { aspectRatio: 1.4, margin: -15, marginBottom: 4, width: 'auto' },
  type: { color: colors.primary, fontSize: 10, fontWeight: '800' },
  title: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  description: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  link: { color: colors.primary, fontSize: 12 },
  date: { color: colors.muted, fontSize: 10 },
});
