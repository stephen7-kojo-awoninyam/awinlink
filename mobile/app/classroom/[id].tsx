import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { mediaDevices, MediaStream, RTCPeerConnection, RTCView } from 'react-native-webrtc';
import { apiRequest, getAccessToken, getWebSocketUrl } from '@/src/api/client';
import { validatedIceServers } from '@/src/calls/iceServers';
import { ClassroomClient, type ClassroomState } from '@/src/classrooms/client';
import { Whiteboard } from '@/src/classrooms/Whiteboard';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

const supportedSharing = Platform.OS === 'android' && typeof mediaDevices.getDisplayMedia === 'function';
export default function ClassroomScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const clientRef = useRef<ClassroomClient | null>(null);
  const [state, setState] = useState<ClassroomState | null>(null), [error, setError] = useState(''), [draft, setDraft] = useState(''), [sending, setSending] = useState(false);
  const report = (e: unknown) => setError(e instanceof Error ? e.message : 'Classroom operation failed.');
  useEffect(() => {
    let client: ClassroomClient;
    try {
      client = new ClassroomClient({ sessionId: Number(id),
        api: (path, method = 'GET', body) => apiRequest(path, { method, body }),
        socket: async path => {
          const token = await getAccessToken();
          if (!token) throw new Error('Sign in again to join the classroom.');
          const Socket = WebSocket as unknown as new (url: string, protocols: string[], options: { headers: Record<string, string> }) => WebSocket;
          return new Socket(getWebSocketUrl(path), [], { headers: { Authorization: `Bearer ${token}` } });
        },
        media: constraints => constraints.audio || constraints.video ? mediaDevices.getUserMedia(constraints) : Promise.resolve(new MediaStream()),
        canCapture: () => AppState.currentState !== 'background',
        display: supportedSharing ? () => mediaDevices.getDisplayMedia({}) : undefined,
        peer: iceServers => new RTCPeerConnection({ iceServers }), validateIce: validatedIceServers,
        onState: next => { setState(next); if (AppState.currentState === 'background' && next.connected && !next.sharing) void clientRef.current?.leave(); },
      });
      clientRef.current = client; setState(client.state); void client.load().catch(report);
    } catch (e) { report(e); return; }
    let polling = false;
    const poll = setInterval(() => { if (polling || AppState.currentState !== 'active') return; polling = true; void client.load().catch(report).finally(() => { polling = false; }); }, 5000);
    const listener = AppState.addEventListener('change', value => { if (value === 'background' && !client.state.sharing) void client.leave(); });
    return () => { clearInterval(poll); listener.remove(); clientRef.current = null; void client.dispose(); };
  }, [id]);
  const run = (operation: () => Promise<unknown>) => { setError(''); void operation().catch(report); };
  const confirmAction = (action: string, label: string, participant?: number) => Alert.alert(label, 'This updates the classroom for its participants.', [
    { text: 'Keep session', style: 'cancel' }, { text: label, style: 'destructive', onPress: () => run(() => clientRef.current!.action(action, participant)) },
  ]);
  const button = (label: string, onPress: () => void, disabled = false, danger = false) => <Pressable key={label} accessibilityRole="button" disabled={disabled} onPress={onPress} style={[styles.button, danger && styles.danger, disabled && styles.disabled]}><Text style={styles.buttonText}>{label}</Text></Pressable>;
  const caps = state?.session?.capabilities || {};
  const joined = !!state?.connected;
  return <>
    <Stack.Screen options={{ headerShown: true, title: state?.session?.title || 'Live classroom' }} />
    <Page title={state?.session?.title || 'Live classroom'} eyebrow="LEARNING TOGETHER">
      <Text accessibilityRole="summary" style={styles.hint}>{state?.session?.status} · {state?.status || 'Loading…'} · {state?.session?.my_participant?.admission_state || 'Not admitted'}</Text>
      {!!(error || state?.error) && <Text accessibilityRole="alert" style={styles.error}>{error || state?.error}</Text>}
      {!state?.session && <>{!error && <ActivityIndicator color={colors.primary} />}{button('Try again', () => run(() => clientRef.current!.load()))}</>}
      <View style={styles.controls}>
        {!state?.session?.my_participant && ['LIVE', 'SCHEDULED'].includes(state?.session?.status || '') && button('Request admission', () => run(() => clientRef.current!.action('request-admission')), !!state?.busy)}
        {caps.start && button('Start session', () => run(() => clientRef.current!.action('start')), !!state?.busy)}
        {caps.cancel && button('Cancel session', () => confirmAction('cancel', 'Cancel session'), !!state?.busy, true)}
        {button(state?.camera ? 'Camera on' : 'Camera off', () => run(() => clientRef.current!.toggle('camera')), !state || !!state.busy || !!state.sharing)}
        {button(state?.microphone ? 'Microphone on' : 'Microphone off', () => run(() => clientRef.current!.toggle('microphone')), !state || !!state.busy)}
        {button('Join classroom', () => run(() => clientRef.current!.join()), !state || !!state.busy || joined || state.status === 'Reconnecting…' || state.session?.status !== 'LIVE' || state.session?.my_participant?.admission_state !== 'ADMITTED')}
        {button('Leave', () => run(() => clientRef.current!.leave()), !joined && !state?.busy && state?.status !== 'Reconnecting…')}
        {supportedSharing && joined && button(state?.sharing ? 'Stop sharing' : 'Share screen', () => run(() => clientRef.current!.share()))}
        {caps.end && button('End for everyone', () => confirmAction('end', 'End for everyone'), !!state?.busy, true)}
      </View>
      <Text style={styles.hint}>Camera and microphone are optional. Media closes in the background unless you explicitly share your screen.</Text>
      <Text style={styles.heading}>Participants</Text>
      <View style={styles.grid}>
        <View style={styles.tile}>{state?.localStream ? <RTCView streamURL={state.localStream.toURL()} objectFit="contain" mirror={!state.sharing} style={styles.video} /> : <Text style={styles.placeholder}>Camera off</Text>}<Text style={styles.label}>{state?.sharing ? 'Your screen' : 'You'}</Text></View>
        {state?.peers.map(peer => <View key={`${peer.participant_id}-${peer.generation}`} style={styles.tile}>{state.remoteStreams[peer.participant_id] ? <RTCView streamURL={state.remoteStreams[peer.participant_id].toURL()} objectFit="contain" style={styles.video} /> : <Text style={styles.placeholder}>Connecting…</Text>}<Text style={styles.label}>{state.participants.find(p => p.id === peer.participant_id)?.display_name || `Participant ${peer.user_id}`} · {peer.role.toLowerCase()}</Text></View>)}
      </View>
      {caps.participants && <View style={styles.panel}><Text style={styles.heading}>Host controls</Text>{state?.participants.map(participant => {
        const learner = participant.role === 'LEARNER', self = participant.id === state.session?.my_participant?.id;
        const manageable = !self && participant.role !== 'HOST' && (state.session?.my_participant?.role !== 'COHOST' || learner);
        const allowed = state.board?.editors.includes(participant.id);
        return <View key={participant.id} style={styles.roster}><Text style={styles.hint}>{participant.display_name} · {participant.role} · {participant.admission_state}</Text><View style={styles.controls}>
          {manageable && caps.admit && participant.admission_state !== 'ADMITTED' && button('Admit', () => run(() => clientRef.current!.action('admit', participant.id)), state.busy)}
          {manageable && caps.remove && participant.admission_state === 'ADMITTED' && button('Remove', () => confirmAction('remove', `Remove ${participant.display_name}`, participant.id), state.busy, true)}
          {learner && participant.admission_state === 'ADMITTED' && state.board?.can_manage && button(allowed ? 'Revoke drawing' : 'Allow drawing', () => run(() => clientRef.current!.boardCommand('permission', { participant_id: participant.id, allowed: !allowed })), !state.activityConnected)}
        </View></View>;
      })}
        {(state?.rosterHasNext || state?.rosterHasPrevious) && <View style={styles.controls}>
          <Text style={styles.hint}>Participant page {state.rosterPage}</Text>
          {button('Previous participants', () => run(() => clientRef.current!.changeRosterPage(-1)), !state.rosterHasPrevious)}
          {button('More participants', () => run(() => clientRef.current!.changeRosterPage(1)), !state.rosterHasNext)}
        </View>}
      </View>}
      <Whiteboard board={state?.board || null} connected={!!state?.activityConnected} onError={report}
        command={(action, payload) => {
          if (action !== 'clear') return clientRef.current!.boardCommand(action, payload);
          return new Promise<void>((resolve, reject) => Alert.alert('Clear whiteboard?', 'All participants will see the cleared board.', [
            { text: 'Keep board', style: 'cancel', onPress: () => resolve() }, { text: 'Clear', style: 'destructive', onPress: () => { clientRef.current!.boardCommand(action, payload).then(resolve, reject); } },
          ]));
        }} />
      <View style={styles.panel}><Text style={styles.heading}>Classroom chat</Text>{!state?.chat.length && <Text style={styles.hint}>Messages appear here after you join.</Text>}
        {state?.chat.map(message => <Text key={message.id} style={styles.chat}><Text style={styles.sender}>{message.sender_name}: </Text>{message.text}</Text>)}
        <TextInput accessibilityLabel="Classroom chat message" placeholder="Message the classroom" value={draft} onChangeText={setDraft} maxLength={2000} multiline editable={joined && !!state?.activityConnected} style={styles.input} />
        {button('Send', () => { setSending(true); run(async () => { try { await clientRef.current!.chat(draft); setDraft(''); } finally { setSending(false); } }); }, sending || !joined || !state?.activityConnected || !draft.trim())}
      </View>
    </Page>
  </>;
}
const styles = StyleSheet.create({ controls: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 }, button: { backgroundColor: colors.primary, borderRadius: 9, paddingVertical: 10, paddingHorizontal: 12 }, danger: { backgroundColor: colors.danger }, disabled: { opacity: .45 }, buttonText: { color: '#fff', fontSize: 12, fontWeight: '700' }, hint: { color: colors.muted, fontSize: 12, lineHeight: 18 }, error: { color: colors.danger }, heading: { color: colors.ink, fontSize: 17, fontWeight: '800' }, grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, tile: { width: '48%', backgroundColor: '#142038', borderRadius: 12, overflow: 'hidden' }, video: { height: 150, width: '100%' }, label: { color: '#fff', fontSize: 11, padding: 8 }, placeholder: { color: '#fff', padding: 25, minHeight: 150, textAlign: 'center' }, panel: { backgroundColor: '#fff', borderRadius: 14, padding: 12, gap: 10 }, roster: { borderBottomColor: colors.border, borderBottomWidth: 1, paddingVertical: 8, gap: 7 }, chat: { color: colors.ink, fontSize: 13 }, sender: { fontWeight: '700' }, input: { borderColor: colors.border, borderWidth: 1, padding: 10, borderRadius: 9 } });
