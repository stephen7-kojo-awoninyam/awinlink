import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import type { FeedPost } from '@/src/types';
import { colors } from '@/src/theme';
import { VideoPlayer } from './MediaPlayer';

export function FeedPostCard({
  post,
  onToggleLike,
}: {
  post: FeedPost;
  onToggleLike: (post: FeedPost) => void;
}) {
  const displayDate = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
  }).format(new Date(post.created_at));

  return (
    <View style={styles.card}>
      <View style={styles.authorRow}>
        {post.author_profile_picture ? (
          <Image source={{ uri: post.author_profile_picture }} style={styles.avatar} />
        ) : (
          <View style={styles.avatarFallback}>
            <Text style={styles.avatarInitial}>
              {post.author_name?.charAt(0)?.toUpperCase() || 'A'}
            </Text>
          </View>
        )}
        <View style={styles.authorDetails}>
          <Text numberOfLines={1} style={styles.authorName}>
            {post.author_name || `@${post.author_username}`}
          </Text>
          <Text style={styles.metadata}>
            @{post.author_username} · {displayDate}
          </Text>
        </View>
      </View>

      {!!post.caption && <Text style={styles.caption}>{post.caption}</Text>}
      {!!post.image && <Image source={{ uri: post.image }} style={styles.postImage} />}
      {!!post.video && (
        <VideoPlayer uri={post.video} />
      )}

      <View style={styles.actions}>
        <Pressable
          accessibilityLabel={post.is_liked ? 'Unlike post' : 'Like post'}
          accessibilityRole="button"
          onPress={() => onToggleLike(post)}
          style={styles.action}
        >
          <Text style={[styles.like, post.is_liked && styles.liked]}>
            {post.is_liked ? '♥' : '♡'} {post.likes_count}
          </Text>
        </Pressable>
        <Text style={styles.commentCount}>◯ {post.comments_count} comments</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    overflow: 'hidden',
  },
  authorRow: { alignItems: 'center', flexDirection: 'row', gap: 11, padding: 15 },
  avatar: { backgroundColor: colors.softBlue, borderRadius: 24, height: 46, width: 46 },
  avatarFallback: {
    alignItems: 'center',
    backgroundColor: colors.softBlue,
    borderRadius: 24,
    height: 46,
    justifyContent: 'center',
    width: 46,
  },
  avatarInitial: { color: colors.primary, fontSize: 18, fontWeight: '800' },
  authorDetails: { flex: 1, gap: 3 },
  authorName: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  metadata: { color: colors.muted, fontSize: 11 },
  caption: { color: colors.ink, fontSize: 14, lineHeight: 21, paddingHorizontal: 15, paddingBottom: 15 },
  postImage: { aspectRatio: 1, backgroundColor: '#edf1f6', width: '100%' },
  videoNotice: { backgroundColor: '#edf1f6', color: colors.muted, padding: 30, textAlign: 'center' },
  actions: {
    alignItems: 'center',
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 22,
    paddingHorizontal: 15,
    paddingVertical: 13,
  },
  action: { minHeight: 26, justifyContent: 'center' },
  like: { color: colors.muted, fontSize: 13, fontWeight: '700' },
  liked: { color: colors.danger },
  commentCount: { color: colors.muted, fontSize: 12, fontWeight: '600' },
});
