import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import { Stack, useLocalSearchParams, router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  mediaDevices,
  RTCPeerConnection,
  RTCView,
  MediaStream,
  type RTCPeerConnection as PeerConnection,
} from 'react-native-webrtc';

import { apiRequest, getAccessToken, getWebSocketUrl } from '@/src/api/client';
import { socketAccessToken, maintainSocketAuthentication } from '@/src/api/socketAuthentication';
import { useAuth } from '@/src/auth/AuthProvider';
import { validatedIceServers, type CallIceServer } from '@/src/calls/iceServers';
import { colors } from '@/src/theme';
import { bindNativeCall, nativeCallConnected, syncNativeMute, endNativeCall } from '@/src/calls/nativeCallUI';
import { callHasEnded, finishCallRequest, onCallEnded } from '@/src/calls/callLifecycle';

type CallParticipant = { user: { id: number }; status: string };
type CallInfo = { id: number; participants: CallParticipant[] };
type Signal = {
  type?: string;
  sender_id?: number;
  to_user_id?: number;
  description?: { type: 'offer' | 'answer'; sdp: string };
  candidate?: RTCIceCandidateInit;
  target_id?: number;
  offer?: { type: 'offer'; sdp: string };
  answer?: { type: 'answer'; sdp: string };
  user_id?: number;
};

function socketWithToken(url: string, token: string) {
  const Socket = WebSocket as unknown as new (
    url: string,
    protocols: string[],
    options: { headers: Record<string, string> },
  ) => WebSocket;
  const socket = new Socket(url, [], { headers: { Authorization: `Bearer ${token}` } });
  maintainSocketAuthentication(socket);
  return socket;
}

export default function CallScreen() {
  const params = useLocalSearchParams<{
    id: string; mode?: string; callType?: string; conversationId?: string; title?: string;
    participants?: string; autoAccept?: string;
  }>();
  const { user } = useAuth();
  const callId = Number(params.id);
  const incoming = params.mode === 'incoming';
  const autoAccept = params.autoAccept === 'true';
  const video = params.callType === 'VIDEO';
  const title = params.title || 'Awinlink call';
  const [status, setStatus] = useState(incoming ? 'Incoming call' : 'Calling…');
  const [error, setError] = useState('');
  const [accepted, setAccepted] = useState(!incoming);
  const [muted, setMuted] = useState(false);
  const [cameraEnabled, setCameraEnabled] = useState(video);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);
  const [remoteStreams, setRemoteStreams] = useState<Record<number, MediaStream>>({});
  const socketRef = useRef<WebSocket | null>(null);
  const localRef = useRef<MediaStream | null>(null);
  const peersRef = useRef(new Map<number, PeerConnection>());
  const offerMakingRef = useRef(new Set<number>());
  const pendingCandidates = useRef(new Map<number, RTCIceCandidateInit[]>());
  const icePolicyRef = useRef<'all' | 'relay'>('all');
  const iceServersRef = useRef<CallIceServer[]>([]);
  const diagnostics = useRef<Record<string, unknown>[]>([]);
  const diagnose = useCallback((event: string, detail: Record<string, unknown> = {}) => {
    const entry = { at: Date.now(), callId, event, ...detail };
    diagnostics.current.push(entry);
    if (diagnostics.current.length > 100) diagnostics.current.shift();
    console.info('[Awinlink call]', entry);
  }, [callId]);
  const leavingRef = useRef(false);
  const autoAcceptHandled = useRef(false);
  const acceptedRef = useRef(!incoming);
  const connectedRef = useRef(false);
  const mediaGeneration = useRef(0);
  const nativeMuted = useRef(false);
  const nativeHeld = useRef(false);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const accepting = useRef(false);

  const closeLocal = useCallback(() => {
    mediaGeneration.current += 1;
    timers.current.forEach(timer => { clearTimeout(timer); clearInterval(timer); });
    timers.current.clear();
    pendingCandidates.current.clear();
    offerMakingRef.current.clear();
    endNativeCall(callId);
    if (socketRef.current) {
      socketRef.current.onmessage = null; socketRef.current.onopen = null;
      socketRef.current.onerror = null; socketRef.current.onclose = null;
    }
    try { socketRef.current?.close(); } catch { /* Continue releasing media. */ }
    socketRef.current = null;
    peersRef.current.forEach((peer) => {
      peer.ontrack = null; peer.onicecandidate = null; peer.onconnectionstatechange = null; peer.oniceconnectionstatechange = null;
      try { peer.close(); } catch { /* Release the remaining peers and tracks. */ }
    });
    peersRef.current.clear();
    localRef.current?.getTracks().forEach((track) => { try { track.stop(); } catch { /* Release remaining tracks. */ } });
    localRef.current = null;
    setLocalStream(null);
    setRemoteStreams({});
  }, [callId]);

  const leaveCall = useCallback(async (reject = false) => {
    if (leavingRef.current) return;
    leavingRef.current = true;
    closeLocal();
    const request = finishCallRequest(callId, () => {
      if (reject && incoming && !acceptedRef.current && !accepting.current) {
        return apiRequest(`messaging/calls/${callId}/reject/`, { method: 'POST' });
      } else {
        return apiRequest(`messaging/calls/${callId}/end/`, {
          method: 'POST', body: { end_for_everyone: true },
        });
      }
    });
    router.back();
    await request.catch(() => {});
  }, [callId, closeLocal, incoming]);

  useEffect(() => {
    const ended = (id: number) => {
      if (id !== callId || leavingRef.current) return;
      leavingRef.current = true; closeLocal(); router.back();
    };
    const remove = onCallEnded(ended);
    if (callHasEnded(callId)) ended(callId);
    return remove;
  }, [callId, closeLocal]);

  useEffect(() => {
    if (!Number.isSafeInteger(callId) || callId < 1 || leavingRef.current || callHasEnded(callId)) return;
    const applyAudio = () => localRef.current?.getAudioTracks().forEach(track => { track.enabled = !nativeMuted.current && !nativeHeld.current; });
    const unbind = bindNativeCall(callId, incoming, title, video, {
      end: () => { void leaveCall(incoming && !acceptedRef.current); },
      mute: value => { nativeMuted.current = value; setMuted(value); applyAudio(); },
      hold: value => { nativeHeld.current = value; applyAudio(); },
    });
    return () => {
      unbind(); closeLocal();
      if (!leavingRef.current) {
        leavingRef.current = true;
        void finishCallRequest(callId, () => apiRequest(`messaging/calls/${callId}/${incoming && !acceptedRef.current && !accepting.current ? 'reject' : 'end'}/`, { method: 'POST', body: { end_for_everyone: true } })).catch(() => {});
      }
    };
  }, [callId, closeLocal, incoming, leaveCall, title, video]);

  const sendSignal = useCallback((payload: Record<string, unknown>) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const makePeer = useCallback((remoteUserId: number) => {
    if (leavingRef.current) throw new Error('Call ended.');
    const existing = peersRef.current.get(remoteUserId);
    if (existing) return existing;
    const local = localRef.current;
    if (!local) throw new Error('The microphone or camera is not ready yet.');
    const peer = new RTCPeerConnection({ iceServers: iceServersRef.current, iceTransportPolicy: icePolicyRef.current });
    peersRef.current.set(remoteUserId, peer);
    local.getTracks().forEach((track) => peer.addTrack(track, local));
    peer.onicecandidate = (event: { candidate: { toJSON: () => RTCIceCandidateInit } | null }) => {
      if (event.candidate) sendSignal({
        type: 'ice_candidate', to_user_id: remoteUserId,
        candidate: event.candidate.toJSON(),
      });
    };
    const receivedStream = new MediaStream();
    peer.ontrack = (event: { streams?: MediaStream[]; track?: MediaStreamTrack }) => {
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) return;
      const stream = event.streams?.[0] || receivedStream;
      if (event.track && !stream.getTracks().some(track => track.id === event.track!.id)) stream.addTrack(event.track as never);
      diagnose('remote_track', { peerId: remoteUserId, kind: event.track?.kind });
      if (stream) setRemoteStreams((current) => ({ ...current, [remoteUserId]: stream }));
    };
    const sampleStats = async () => {
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) return;
      try {
        const report = await peer.getStats();
        report.forEach((row: { type: string; isRemote?: boolean; kind?: string; mediaType?: string; bytesReceived?: number; packetsLost?: number; framesDecoded?: number; selectedCandidatePairId?: string }) => {
          if (row.type === 'inbound-rtp' && !row.isRemote) diagnose('inbound_media', {
            peerId: remoteUserId, kind: row.kind || row.mediaType, bytesReceived: row.bytesReceived || 0,
            packetsLost: row.packetsLost || 0, framesDecoded: row.framesDecoded || 0,
          });
          if (row.type === 'transport' && row.selectedCandidatePairId) {
            const pair = report.get(row.selectedCandidatePairId);
            diagnose('selected_ice_pair', {
              peerId: remoteUserId,
              localType: pair && report.get(pair.localCandidateId)?.candidateType,
              remoteType: pair && report.get(pair.remoteCandidateId)?.candidateType,
            });
          }
        });
      } catch { /* Older engines may not expose all stats. */ }
    };
    const statsTimer = setInterval(() => {
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) {
        clearInterval(statsTimer); timers.current.delete(statsTimer); return;
      }
      void sampleStats();
    }, 5000);
    timers.current.add(statsTimer);
    peer.oniceconnectionstatechange = () => {
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) return;
      diagnose('ice_state', { peerId: remoteUserId, state: peer.iceConnectionState });
      if (['connected', 'completed', 'failed'].includes(peer.iceConnectionState)) void sampleStats();
    };
    peer.onconnectionstatechange = () => {
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) return;
      if (peer.connectionState === 'connected') {
        connectedRef.current = true;
        nativeCallConnected(callId);
        setStatus('Connected');
      } else if (peer.connectionState === 'failed') {
        setError('The call could not connect. Check the network or TURN server and try again.');
        setStatus('Connection failed');
      } else if (peer.connectionState === 'disconnected') {
        setStatus('Reconnecting…');
      }
    };
    return peer;
  }, [callId, diagnose, sendSignal]);

  const createOffer = useCallback(async (remoteUserId: number) => {
    const existing = peersRef.current.get(remoteUserId);
    if (offerMakingRef.current.has(remoteUserId) || (existing && existing.signalingState !== 'stable')) return;
    offerMakingRef.current.add(remoteUserId);
    try {
      const peer = makePeer(remoteUserId);
      const offer = await peer.createOffer();
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) return;
      await peer.setLocalDescription(offer);
      if (leavingRef.current || peersRef.current.get(remoteUserId) !== peer) return;
      sendSignal({ type: 'offer', to_user_id: remoteUserId, description: offer });
    } finally {
      offerMakingRef.current.delete(remoteUserId);
    }
  }, [makePeer, sendSignal]);

  const connectSignaling = useCallback(async (call: CallInfo) => {
    const token = await socketAccessToken();
    if (leavingRef.current) return;
    if (!token) throw new Error('Your session expired. Sign in again to call.');
    const socket = socketWithToken(getWebSocketUrl(`ws/calls/${callId}/`), token);
    socketRef.current = socket;
    socket.onopen = () => {
      if (leavingRef.current || socketRef.current !== socket) { socket.close(); return; }
      setStatus('Waiting for others…');
      const activePeers = call.participants.filter(
        (participant) => participant.status === 'JOINED' && participant.user.id !== user?.id,
      );
      activePeers.forEach((participant) => sendSignal({
        type: 'ready', to_user_id: participant.user.id,
      }));
    };
    socket.onerror = () => setError('Signaling connection failed. Check your network and try again.');
    socket.onclose = (event) => {
      if (!leavingRef.current && event.code !== 1000) {
        setError('The signaling connection closed. Reconnect or hang up.');
      }
    };
    let signalQueue = Promise.resolve();
    socket.onmessage = (event) => {
      if (leavingRef.current || socketRef.current !== socket) return;
      signalQueue = signalQueue.then(async () => {
        if (leavingRef.current || socketRef.current !== socket) return;
        const message = JSON.parse(String(event.data)) as Signal & { call_id?: number };
        message.type = message.type === 'ice-candidate' ? 'ice_candidate' : message.type;
        message.description = message.description || message.offer || message.answer;
        message.to_user_id = message.to_user_id ?? message.target_id;
        const peerId = Number(message.sender_id ?? message.user_id);
        diagnose('signal_received', { type: message.type, peerId });
        if (message.type === 'call_ended') {
          if (message.call_id && message.call_id !== callId) return;
          leavingRef.current = true;
          setStatus('Call ended');
          closeLocal();
          router.back();
          return;
        }
        if (message.type === 'participant_rejected') {
          setStatus('Call declined');
          setError('A participant declined the call.');
          return;
        }
        if (message.type === 'participant_left') {
          peersRef.current.get(peerId)?.close();
          peersRef.current.delete(peerId);
          setRemoteStreams((current) => {
            const next = { ...current };
            delete next[peerId];
            return next;
          });
          return;
        }
        if (message.type === 'connection') {
          call.participants.filter(p => p.status === 'JOINED' && p.user.id !== user?.id).forEach(p => sendSignal({ type: 'ready', to_user_id: p.user.id }));
          return;
        }
        if (message.type === 'participant_joined' && peerId && peerId !== user?.id) {
          setStatus('Connecting…');
          sendSignal({ type: 'ready', to_user_id: peerId });
          if (Number(user?.id) < peerId) await createOffer(peerId);
          return;
        }
        if (message.to_user_id && message.to_user_id !== user?.id) return;
        if (!peerId || peerId === user?.id) return;
        if (message.type === 'ready') {
          if (Number(user?.id) < peerId) await createOffer(peerId);
          return;
        }
        if (message.type === 'offer' && message.description) {
          const peer = makePeer(peerId);
          await peer.setRemoteDescription(message.description);
          if (leavingRef.current || peersRef.current.get(peerId) !== peer) return;
          const candidates = pendingCandidates.current.get(peerId) ?? [];
          pendingCandidates.current.delete(peerId);
          for (const candidate of candidates) await peer.addIceCandidate(candidate);
          const answer = await peer.createAnswer();
          if (leavingRef.current || peersRef.current.get(peerId) !== peer) return;
          await peer.setLocalDescription(answer);
          if (leavingRef.current || peersRef.current.get(peerId) !== peer) return;
          sendSignal({ type: 'answer', to_user_id: peerId, description: answer });
        } else if (message.type === 'answer' && message.description) {
          const peer = peersRef.current.get(peerId);
          if (peer) {
            await peer.setRemoteDescription(message.description);
            if (leavingRef.current || peersRef.current.get(peerId) !== peer) return;
            const candidates = pendingCandidates.current.get(peerId) ?? [];
            pendingCandidates.current.delete(peerId);
            for (const candidate of candidates) await peer.addIceCandidate(candidate);
          }
        } else if (message.type === 'ice_candidate' && message.candidate) {
          const peer = peersRef.current.get(peerId);
          if (peer?.remoteDescription) await peer.addIceCandidate(message.candidate);
          else pendingCandidates.current.set(peerId, [
            ...(pendingCandidates.current.get(peerId) ?? []), message.candidate,
          ]);
        }
      }).catch((signalError: unknown) => {
        diagnose('signaling_error', { name: signalError instanceof Error ? signalError.name : 'Error' });
        setError(signalError instanceof Error ? signalError.message : 'WebRTC signaling failed.');
      });
    };
  }, [callId, closeLocal, createOffer, diagnose, makePeer, sendSignal, user?.id]);

  const startMedia = useCallback(async (call: CallInfo) => {
    if (leavingRef.current || callHasEnded(callId)) return;
    const generation = mediaGeneration.current;
    try {
      setError('');
      const ice = await apiRequest<{ ice_servers?: unknown; ice_transport_policy?: string }>('messaging/calls/ice-servers/');
      if (leavingRef.current || generation !== mediaGeneration.current) return;
      icePolicyRef.current = ice.ice_transport_policy === 'relay' ? 'relay' : 'all';
      iceServersRef.current = validatedIceServers(ice.ice_servers);
      diagnose('ice_configuration', { policy: icePolicyRef.current, relayConfigured: iceServersRef.current.some(server => [server.urls].flat().some(url => /^turns?:/.test(url))) });
      const stream = await mediaDevices.getUserMedia({ audio: true, video: video ? {
        facingMode: 'user', width: 1280, height: 720, frameRate: 24,
      } : false });
      if (leavingRef.current || generation !== mediaGeneration.current) { stream.getTracks().forEach(track => track.stop()); return; }
      diagnose('local_tracks', { count: stream.getTracks().length });
      localRef.current = stream;
      setLocalStream(stream);
      setAccepted(true);
      acceptedRef.current = true;
      setStatus('Connecting…');
      await connectSignaling(call);
    } catch (mediaError) {
      if (leavingRef.current || generation !== mediaGeneration.current) return;
      const message = mediaError instanceof Error ? mediaError.message : 'Unable to access the microphone or camera.';
      setError(message.includes('Permission') || message.includes('permission')
        ? 'Microphone or camera access was denied. Enable the permission in device settings and retry.'
        : message);
      setStatus('Unable to start call');
      Alert.alert('Unable to start call', 'Check microphone permissions and network connectivity, then try again.');
      void leaveCall();
    }
  }, [callId, connectSignaling, diagnose, incoming, leaveCall, video]);

  useEffect(() => {
    if (leavingRef.current || callHasEnded(callId)) return;
    if (!Number.isInteger(callId) || callId < 1 || !user) {
      setError('This call link is invalid or your session has expired.');
      return;
    }
    if (incoming && !accepted) {
      let active = true;
      let expired = false;
      const checkIncoming = async () => {
        try {
          const calls = await apiRequest<{ id: number }[]>('messaging/calls/incoming/');
          if (active && !expired && !accepting.current && !acceptedRef.current && !calls.some((call) => call.id === callId)) {
            expired = true;
            leavingRef.current = true; closeLocal(); router.back();
          }
        } catch { /* Keep the answer controls available during a temporary network outage. */ }
      };
      void checkIncoming();
      const poll = setInterval(() => void checkIncoming(), 4000);
      timers.current.add(poll);
      return () => { active = false; clearInterval(poll); };
    }
    if (incoming) return;
    let active = true;
    const outgoingCall: CallInfo = { id: callId, participants: (() => {
      try { return JSON.parse(params.participants || '[]') as CallParticipant[]; }
      catch { return []; }
    })() };
    void startMedia(outgoingCall)
      .catch((callError: unknown) => setError(callError instanceof Error ? callError.message : 'Unable to start the call.'));
    const timeout = setTimeout(() => {
      if (!connectedRef.current && active) {
        setError('No one answered. The call has ended.');
        void leaveCall();
      }
    }, 35_000);
    timers.current.add(timeout);
    return () => { active = false; clearTimeout(timeout); closeLocal(); };
  }, [accepted, callId, closeLocal, incoming, leaveCall, params.participants, startMedia, user]);

  async function acceptCall() {
    if (leavingRef.current || accepting.current || acceptedRef.current) return;
    accepting.current = true;
    try {
      const call = await apiRequest<CallInfo>(`messaging/calls/${callId}/accept/`, { method: 'POST' });
      if (leavingRef.current || callHasEnded(callId)) return;
      acceptedRef.current = true;
      setAccepted(true);
      await startMedia(call);
    } catch (acceptError) {
      if (leavingRef.current) return;
      setError(acceptError instanceof Error ? acceptError.message : 'Unable to accept the call.');
    } finally { accepting.current = false; }
  }

  useEffect(() => {
    if (incoming && autoAccept && !accepted && user && !autoAcceptHandled.current) {
      autoAcceptHandled.current = true;
      void acceptCall();
    }
  }, [accepted, autoAccept, incoming, user]);

  function toggleMute() {
    const next = !muted;
    nativeMuted.current = next;
    localRef.current?.getAudioTracks().forEach((track) => { track.enabled = !next && !nativeHeld.current; });
    syncNativeMute(callId, next);
    setMuted(next);
  }

  function toggleCamera() {
    const next = !cameraEnabled;
    localRef.current?.getVideoTracks().forEach((track) => { track.enabled = next; });
    setCameraEnabled(next);
  }

  function switchCamera() {
    const track = localRef.current?.getVideoTracks()[0] as (MediaStreamTrack & { _switchCamera?: () => void }) | undefined;
    if (track?._switchCamera) track._switchCamera();
    else Alert.alert('Camera unavailable', 'Camera switching is not supported on this device.');
  }

  return (
    <SafeAreaView style={styles.safe}>
      <Stack.Screen options={{ headerShown: false }} />
      <View style={styles.container}>
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.status}>{status}</Text>
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
        <View style={styles.videoArea}>
          {Object.entries(remoteStreams).map(([participantId, stream], index, entries) => (
            <RTCView key={participantId} streamURL={stream.toURL()} style={entries.length === 1 ? styles.remoteVideoFull : [styles.remoteVideoGrid, { left: `${(index % 2) * 50}%`, top: `${Math.floor(index / 2) * 50}%` }]} objectFit="cover" />
          ))}
          {video && localStream && <RTCView streamURL={localStream.toURL()} style={styles.localVideo} objectFit="cover" mirror />}
          {(!video || Object.keys(remoteStreams).length === 0) && (
            <View style={styles.audioPlaceholder}>
              <View style={styles.avatar}><Text style={styles.avatarText}>{title.slice(0, 1).toUpperCase()}</Text></View>
              {localStream ? null : <ActivityIndicator color="#fff" style={{ marginTop: 20 }} />}
            </View>
          )}
        </View>
        {incoming && !accepted ? (
          <View style={styles.actions}>
            <Control label="Decline" onPress={() => void leaveCall(true)} danger />
            <Control label="Answer" onPress={() => void acceptCall()} primary />
          </View>
        ) : (
          <View style={styles.actions}>
            <Control label={muted ? 'Unmute' : 'Mute'} onPress={toggleMute} />
            {video && <Control label={cameraEnabled ? 'Camera off' : 'Camera on'} onPress={toggleCamera} />}
            {video && <Control label="Flip" onPress={switchCamera} />}
            <Control label="Hang up" onPress={() => void leaveCall()} danger />
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

function Control({ label, onPress, danger, primary }: {
  label: string; onPress: () => void; danger?: boolean; primary?: boolean;
}) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={[
    styles.control, danger && styles.danger, primary && styles.primary,
  ]}><Text style={styles.controlText}>{label}</Text></Pressable>;
}

const styles = StyleSheet.create({
  safe: { backgroundColor: '#0b1020', flex: 1 },
  container: { alignItems: 'center', flex: 1, justifyContent: 'space-between', padding: 22 },
  title: { color: '#fff', fontSize: 24, fontWeight: '800', marginTop: 24 },
  status: { color: '#c8d0e0', fontSize: 15, marginTop: -16 },
  error: { color: '#ffb4ab', fontSize: 13, textAlign: 'center' },
  videoArea: { alignItems: 'center', backgroundColor: '#151b2d', borderRadius: 24, flex: 1, justifyContent: 'center', marginVertical: 22, overflow: 'hidden', width: '100%' },
  remoteVideoFull: { height: '100%', position: 'absolute', width: '100%' },
  remoteVideoGrid: { height: '50%', position: 'absolute', width: '50%' },
  localVideo: { borderColor: '#fff', borderRadius: 14, borderWidth: 1, height: 150, position: 'absolute', right: 14, top: 14, width: 104, zIndex: 2 },
  audioPlaceholder: { alignItems: 'center', justifyContent: 'center' },
  avatar: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 60, height: 112, justifyContent: 'center', width: 112 },
  avatarText: { color: '#fff', fontSize: 44, fontWeight: '700' },
  actions: { alignItems: 'center', flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'center', marginBottom: 20 },
  control: { alignItems: 'center', backgroundColor: '#273149', borderRadius: 24, justifyContent: 'center', minHeight: 48, minWidth: 88, paddingHorizontal: 16 },
  primary: { backgroundColor: colors.success },
  danger: { backgroundColor: '#b42318' },
  controlText: { color: '#fff', fontSize: 13, fontWeight: '700' },
});
