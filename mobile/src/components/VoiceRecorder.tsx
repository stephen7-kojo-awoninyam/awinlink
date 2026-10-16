import { useEffect, useRef, useState } from 'react';
import { Button, Platform, Text, View } from 'react-native';
import { AudioModule, RecordingPresets, setAudioModeAsync, useAudioRecorder, useAudioRecorderState } from 'expo-audio';
import { apiRequest } from '@/src/api/client';
import type { Message } from '@/src/types';
import { VoicePlayer } from './MediaPlayer';
import { createVoiceUpload, recordingMimeType } from '@/src/voice-upload';

export function VoiceRecorder({ conversationId, disabled, onSent }: {
  conversationId: number; disabled: boolean; onSent: (message: Message) => void;
}) {
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const state = useAudioRecorderState(recorder);
  const [uri, setUri] = useState('');
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const recording = useRef(false);
  useEffect(() => () => {
    if (recording.current) void setAudioModeAsync({ allowsRecording: false }).catch(() => {});
  }, []);
  async function record() {
    setWorking(true); setError('');
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!permission.granted) throw new Error('Allow microphone access to record a voice message.');
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      const mimeType = Platform.OS === 'web' && typeof MediaRecorder !== 'undefined'
        ? recordingMimeType(MediaRecorder) : undefined;
      await recorder.prepareToRecordAsync({ ...RecordingPresets.HIGH_QUALITY,
        web: { ...RecordingPresets.HIGH_QUALITY.web, mimeType } });
      recorder.record();
      recording.current = true;
    } catch (e) {
      await setAudioModeAsync({ allowsRecording: false }).catch(() => {});
      setError(e instanceof Error ? e.message : 'Unable to record.');
    }
    finally { setWorking(false); }
  }
  async function stop() {
    setWorking(true); setError('');
    try {
      await recorder.stop();
      recording.current = false;
      if (!recorder.uri) throw new Error('No voice recording was created.');
      setUri(recorder.uri);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to stop recording.'); }
    finally {
      await setAudioModeAsync({ allowsRecording: false }).catch(() => {});
      setWorking(false);
    }
  }
  async function send() {
    if (!uri || working) return;
    setWorking(true); setError('');
    try {
      const body = await createVoiceUpload(uri, Platform.OS);
      const message = await apiRequest<Message>(`messaging/conversations/${conversationId}/messages/create/`, { method: 'POST', body });
      onSent(message);
      setUri('');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to send. Your recording is ready to retry.'); }
    finally { setWorking(false); }
  }
  return <View style={{ padding: 10, gap: 6 }}>
    {uri ? <>
      <VoicePlayer uri={uri} />
      <Button title="Send voice message" disabled={disabled || working} onPress={() => void send()} />
      <Button title="Discard recording" disabled={working} onPress={() => setUri('')} />
    </> : <Button title={state.isRecording ? `Stop recording (${Math.floor(state.durationMillis / 1000)}s)` : 'Record voice message'}
      disabled={disabled || working} onPress={() => void (state.isRecording ? stop() : record())} />}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}
