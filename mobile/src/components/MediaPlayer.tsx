import { useEffect, useState } from 'react';
import { AppState, Button, Linking, Text, View } from 'react-native';
import { useEvent } from 'expo';
import { useVideoPlayer, VideoView } from 'expo-video';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { mediaSource } from '@/src/api/client';

function useMediaSource(uri: string) {
  const [source, setSource] = useState<{ uri: string; headers?: Record<string, string> } | null>(null);
  const [sourceError, setSourceError] = useState('');
  useEffect(() => {
    let active = true;
    setSource(null);
    setSourceError('');
    void mediaSource(uri).then(value => { if (active) setSource(value); })
      .catch(() => { if (active) setSourceError('Unable to load this media URL.'); });
    return () => { active = false; };
  }, [uri]);
  return { source, sourceError };
}

export function VideoPlayer({ uri }: { uri: string }) {
  const { source, sourceError } = useMediaSource(uri);
  const player = useVideoPlayer(source);
  const { status, error } = useEvent(player, 'statusChange', { status: player.status });
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => { if (state !== 'active') player.pause(); });
    return () => subscription.remove();
  }, [player]);
  return <View>
    <VideoView player={player} nativeControls contentFit="contain" style={{ width: '100%', minWidth: 220, height: 240 }} />
    {!!sourceError && <Text accessibilityRole="alert">{sourceError}</Text>}
    {status === 'error' && <><Text accessibilityRole="alert">Unable to play this video. {error?.message}</Text><Button title="Open original video" onPress={() => void Linking.openURL(uri)} /></>}
  </View>;
}

export function VoicePlayer({ uri }: { uri: string }) {
  const { source, sourceError } = useMediaSource(uri);
  const player = useAudioPlayer(source);
  const status = useAudioPlayerStatus(player);
  const [error, setError] = useState('');
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => { if (state !== 'active') player.pause(); });
    return () => subscription.remove();
  }, [player]);
  async function toggle() {
    try {
      setError('');
      if (status.playing) { player.pause(); return; }
      await setAudioModeAsync({ playsInSilentMode: true });
      if (status.didJustFinish || (status.duration > 0 && status.currentTime >= status.duration)) await player.seekTo(0);
      player.play();
    } catch { setError('Unable to play this voice message.'); }
  }
  return <View style={{ minWidth: 220, gap: 6 }}>
    <Button title={status.playing ? 'Pause voice message' : 'Play voice message'} disabled={!status.isLoaded} onPress={() => void toggle()} />
    <Text>{Math.floor(status.currentTime || 0)} / {Math.floor(status.duration || 0)} seconds</Text>
    <View style={{ flexDirection: 'row', gap: 8 }}>
      <Button title="Back 10s" disabled={!status.isLoaded} onPress={() => void player.seekTo(Math.max(0, status.currentTime - 10))} />
      <Button title="Forward 10s" disabled={!status.isLoaded} onPress={() => void player.seekTo(Math.min(status.duration, status.currentTime + 10))} />
    </View>
    {!!(error || status.error || sourceError) && <Text accessibilityRole="alert">{error || status.error || sourceError}</Text>}
    <Button title="Open audio file" onPress={() => void Linking.openURL(uri)} />
  </View>;
}
