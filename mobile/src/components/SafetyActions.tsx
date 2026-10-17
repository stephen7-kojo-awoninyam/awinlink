import { useState } from 'react';
import { Alert, Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';

export function SafetyActions({ userId, postId, onBlocked }: { userId?: number; postId?: number; onBlocked?: () => void }) {
  const { user } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function block() {
    setBusy(true); setError('');
    try { await apiRequest('safety/blocks/', { method: 'POST', body: { user_id: userId } }); onBlocked?.(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to block account.'); }
    finally { setBusy(false); }
  }
  if (userId === user?.id) return null;
  return <View style={{ gap: 8, padding: 10 }}>
    <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: '/report', params: { type: postId ? 'post' : 'user', id: String(postId || userId) } })}><Text>Report {postId ? 'post' : 'account'}</Text></Pressable>
    {!!userId && <Pressable accessibilityRole="button" disabled={busy} onPress={() => Alert.alert('Block this account?', 'Their profile and posts will be hidden. Messages, calls, follows, and connection requests between you will be prevented. You can unblock in Account and safety.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Block', style: 'destructive', onPress: () => void block() }])}><Text>{busy ? 'Blocking...' : 'Block account'}</Text></Pressable>}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}
