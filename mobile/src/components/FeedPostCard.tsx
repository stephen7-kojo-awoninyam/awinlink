import { useEffect, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { apiRequest, mediaSource } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';

import type { FeedPost } from '@/src/types';
import { colors } from '@/src/theme';
import { VideoPlayer } from './MediaPlayer';
import { SafetyActions } from './SafetyActions';

export function FeedPostCard({
  post,
  onToggleLike,
}: {
  post: FeedPost;
  onToggleLike: (post: FeedPost) => void;
}) {
  const { user } = useAuth();
  const [liking, setLiking] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [comments, setComments] = useState<{ id: number; user: number; user_name: string; text: string }[] | null>(null);
  const [draft, setDraft] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [blocked, setBlocked] = useState(false);
  const [imageSource, setImageSource] = useState<{ uri: string; headers?: Record<string, string> } | null>(null);
  useEffect(() => {
    let active = true;
    setImageSource(null);
    if (post.image) void mediaSource(post.image).then(source => { if (active) setImageSource(source); });
    return () => { active = false; };
  }, [post.image]);
  async function loadComments() {
    setExpanded(true); setWorking(true); setError('');
    try { setComments(await apiRequest(`feed/posts/${post.id}/comments/`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load comments.'); }
    finally { setWorking(false); }
  }
  async function submitComment() {
    if (working || !draft.trim()) return;
    setWorking(true); setError('');
    try {
      const comment = await apiRequest<NonNullable<typeof comments>[number]>(`feed/posts/${post.id}/comments/`, { method: 'POST', body: { text: draft.trim() } });
      setComments(current => [comment, ...(current || [])]); setDraft('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to send comment.'); }
    finally { setWorking(false); }
  }
  async function deleteComment(id: number) {
    setWorking(true); setError('');
    try { await apiRequest(`feed/comments/${id}/delete/`, { method: 'DELETE' }); setComments(current => current?.filter(item => item.id !== id) || []); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to delete comment.'); }
    finally { setWorking(false); }
  }
  const displayDate = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
  }).format(new Date(post.created_at));

  if (blocked) return null;
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
      {!!post.image && imageSource && <Image source={imageSource} style={styles.postImage} />}
      {!!post.video && (
        <VideoPlayer uri={post.video} />
      )}

      <View style={styles.actions}>
        <Pressable
          accessibilityLabel={post.is_liked ? 'Unlike post' : 'Like post'}
          accessibilityRole="button"
          disabled={liking}
          onPress={async () => { setLiking(true); try { await onToggleLike(post); } finally { setLiking(false); } }}
          style={styles.action}
        >
          <Text style={[styles.like, post.is_liked && styles.liked]}>
            {post.is_liked ? '♥' : '♡'} {post.likes_count}
          </Text>
        </Pressable>
        <Pressable accessibilityRole="button" disabled={working} onPress={() => expanded ? setExpanded(false) : void loadComments()}>
          <Text style={styles.commentCount}>{comments?.length ?? post.comments_count} comments</Text>
        </Pressable>
      </View>
      <SafetyActions userId={post.author} postId={post.id} onBlocked={() => setBlocked(true)} />
      {expanded && <View style={{ padding: 15, gap: 12 }}>
        {comments?.map(comment => <View key={comment.id} style={{ gap: 4 }}>
          <Text style={styles.authorName}>{comment.user_name}</Text><Text>{comment.text}</Text>
          {comment.user === user?.id && <Pressable accessibilityRole="button" disabled={working} onPress={() => void deleteComment(comment.id)}><Text style={styles.liked}>Delete comment</Text></Pressable>}
        </View>)}
        {!!error && <><Text accessibilityRole="alert" style={styles.liked}>{error}</Text><Pressable disabled={working} onPress={() => void loadComments()}><Text>Retry loading comments</Text></Pressable></>}
        <TextInput accessibilityLabel="Comment" placeholder="Write a comment" multiline value={draft} onChangeText={setDraft} editable={!working} style={{ borderWidth: 1, borderColor: colors.border, padding: 10, borderRadius: 8 }} />
        <Pressable accessibilityRole="button" disabled={working || !draft.trim() || comments === null} onPress={() => void submitComment()}><Text style={styles.authorName}>{working ? 'Working...' : 'Send comment'}</Text></Pressable>
      </View>}
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
