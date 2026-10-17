import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { Stack, useFocusEffect } from 'expo-router';

import { useAuth } from '@/src/auth/AuthProvider';
import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

type ConnectionRequest = { id: number; sender_id: number; sender_username: string; sender_name: string; receiver_id: number; receiver_username: string; receiver_name: string; status: string; created_at: string };

export default function ConnectionsScreen() {
  const { user } = useAuth();
  const [incoming, setIncoming] = useState<ConnectionRequest[]>([]);
  const [outgoing, setOutgoing] = useState<ConnectionRequest[]>([]);
  const [accepted, setAccepted] = useState<ConnectionRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [workingId, setWorkingId] = useState<number | null>(null);
  const mutationInFlight = useRef(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    setError('');
    try {
      const [received, sent, current] = await Promise.all([apiRequest<ConnectionRequest[]>('connections/received/'), apiRequest<ConnectionRequest[]>('connections/sent/'), apiRequest<ConnectionRequest[]>('connections/')]);
      setIncoming(received.filter((item) => item.status === 'PENDING')); setOutgoing(sent.filter((item) => item.status === 'PENDING')); setAccepted(current);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load connection requests.'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  async function respond(item: ConnectionRequest, status: 'ACCEPTED' | 'REJECTED') {
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setWorkingId(item.id); setError('');
    try { const updated = await apiRequest<ConnectionRequest>(`connections/${item.id}/respond/`, { method: 'PATCH', body: { status } }); if (status === 'ACCEPTED') setAccepted((current) => [...current.filter((request) => request.id !== item.id), updated]); setIncoming((current) => current.filter((request) => request.id !== item.id)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update this request.'); }
    finally { mutationInFlight.current = false; setWorkingId(null); }
  }
  async function cancel(item: ConnectionRequest) {
    if (mutationInFlight.current) return;
    mutationInFlight.current = true;
    setWorkingId(item.id); setError('');
    try { await apiRequest(`connections/${item.id}/cancel/`, { method: 'POST' }); setOutgoing((current) => current.filter((request) => request.id !== item.id)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to cancel this request.'); }
    finally { mutationInFlight.current = false; setWorkingId(null); }
  }
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Connections', headerTintColor: colors.primary, headerShadowVisible: false }} />
    <Page eyebrow="YOUR NETWORK" title="Connections" refreshControl={<RefreshControl refreshing={refreshing} tintColor={colors.primary} onRefresh={() => { setRefreshing(true); void load(); }} />}>
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : error && incoming.length === 0 && outgoing.length === 0 && accepted.length === 0 ? <EmptyState title="Connections unavailable" message={error} actionLabel="Try again" onAction={() => { setLoading(true); void load(); }} /> : <>
        <Text style={styles.section}>Requests for you</Text>
        {incoming.length === 0 ? <Text style={styles.empty}>No pending connection requests.</Text> : incoming.map((item) => <View key={item.id} style={styles.card}><Text style={styles.person}>{item.sender_name || item.sender_username}</Text><Text style={styles.username}>@{item.sender_username}</Text><View style={styles.actions}><Pressable disabled={workingId !== null} onPress={() => void respond(item, 'ACCEPTED')} style={styles.accept}><Text style={styles.acceptText}>{workingId === item.id ? 'Working...' : 'Accept'}</Text></Pressable><Pressable disabled={workingId !== null} onPress={() => void respond(item, 'REJECTED')} style={styles.secondary}><Text style={styles.secondaryText}>Decline</Text></Pressable></View></View>)}
        <Text style={styles.section}>Sent requests</Text>
        {outgoing.length === 0 ? <Text style={styles.empty}>You have no pending sent requests.</Text> : outgoing.map((item) => <View key={item.id} style={styles.card}><Text style={styles.person}>{item.receiver_name || item.receiver_username}</Text><Text style={styles.username}>@{item.receiver_username}</Text><Pressable disabled={workingId !== null} onPress={() => void cancel(item)} style={styles.secondary}><Text style={styles.secondaryText}>{workingId === item.id ? 'Working...' : 'Cancel request'}</Text></Pressable></View>)}
        <Text style={styles.section}>Connected</Text>
        {accepted.length === 0 ? <Text style={styles.empty}>Accepted connections will appear here.</Text> : accepted.map((item) => {
          const otherName = user?.id === item.sender_id ? item.receiver_name : item.sender_name;
          const otherUsername = user?.id === item.sender_id ? item.receiver_username : item.sender_username;
          return <View key={item.id} style={styles.card}><Text style={styles.person}>{otherName || otherUsername}</Text><Text style={styles.username}>@{otherUsername}</Text></View>;
        })}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </>}
    </Page>
  </>;
}

const styles = StyleSheet.create({ loader: { marginTop: 28 }, section: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 8 }, empty: { color: colors.muted, fontSize: 13 }, card: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 8, padding: 14 }, person: { color: colors.ink, fontSize: 14, fontWeight: '800' }, username: { color: colors.muted, fontSize: 12 }, actions: { flexDirection: 'row', gap: 8, marginTop: 4 }, accept: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 10, flex: 1, padding: 11 }, acceptText: { color: '#fff', fontSize: 12, fontWeight: '800' }, secondary: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 10, flex: 1, padding: 11 }, secondaryText: { color: colors.primary, fontSize: 12, fontWeight: '800' }, error: { color: colors.danger, fontSize: 12 } });
