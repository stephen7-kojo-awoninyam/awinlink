import { useCallback, useState } from 'react';
import { ActivityIndicator, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';

import { useAuth } from '@/src/auth/AuthProvider';
import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { FeedPostCard } from '@/src/components/FeedPostCard';
import { Page, ui } from '@/src/components/Page';
import type { FeedPost } from '@/src/types';
import { colors } from '@/src/theme';

export default function FeedScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [posts, setPosts] = useState<FeedPost[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadFeed = useCallback(async () => {
    setError('');
    try {
      setPosts(await apiRequest<FeedPost[]>('feed/posts/'));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load the feed.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadFeed();
    }, [loadFeed]),
  );

  const toggleLike = useCallback(async (post: FeedPost) => {
    const action = post.is_liked ? 'unlike' : 'like';
    try {
      await apiRequest(`feed/posts/${post.id}/${action}/`, { method: post.is_liked ? 'DELETE' : 'POST' });
      setPosts((current) =>
        current.map((item) =>
          item.id === post.id
            ? {
                ...item,
                is_liked: !post.is_liked,
                likes_count: item.likes_count + (post.is_liked ? -1 : 1),
              }
            : item,
        ),
      );
    } catch (likeError) {
      setError(likeError instanceof Error ? likeError.message : 'Unable to update this like.');
    }
  }, []);

  const firstName = user?.first_name || user?.username || 'there';

  return (
    <Page
      eyebrow="YOUR AWINLINK"
      title="Home"
      refreshControl={
        <RefreshControl
          onRefresh={() => {
            setRefreshing(true);
            void loadFeed();
          }}
          refreshing={refreshing}
          tintColor={colors.primary}
        />
      }
    >
      <View style={styles.welcome}>
        <Text style={styles.welcomeTitle}>Good to see you, {firstName}</Text>
        <Text style={ui.muted}>
          {user?.role === 'ATHLETE'
            ? 'Your talent ecosystem, in one feed.'
            : 'Updates from your Awinlink network.'}
        </Text>
      </View>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={styles.loader} />
      ) : error ? (
        <EmptyState
          title="Feed unavailable"
          message={error}
          actionLabel="Try again"
          onAction={() => void loadFeed()}
        />
      ) : posts.length === 0 ? (
        <EmptyState
          title="Your feed is ready"
          message="Follow people and connect with your ecosystem to bring updates into your feed."
          actionLabel="Discover people"
          onAction={() => router.navigate('/(tabs)/discover')}
        />
      ) : (
        posts.map((post) => (
          <FeedPostCard key={post.id} onToggleLike={toggleLike} post={post} />
        ))
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  welcome: {
    backgroundColor: '#eaf1ff',
    borderColor: '#d8e4ff',
    borderRadius: 17,
    borderWidth: 1,
    gap: 5,
    padding: 16,
  },
  welcomeTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  loader: { marginTop: 28 },
});
