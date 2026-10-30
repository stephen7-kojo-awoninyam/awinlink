import { useEffect, useState } from 'react';
import { Alert, AppState, Button, Pressable, Text, View } from 'react-native';
import { useEvent } from 'expo';
import { useVideoPlayer, VideoView } from 'expo-video';
import { setAudioModeAsync, useAudioPlayer, useAudioPlayerStatus } from 'expo-audio';
import { downloadMedia } from '@/src/media-download';
import { mediaSource } from '@/src/api/client';
import { parseWebVtt } from '@/src/webvtt';

function useMediaSource(uri: string, localPreview = false) {
  const [source, setSource] = useState<{ uri: string; headers?: Record<string, string> } | null>(null);
  const [sourceError, setSourceError] = useState('');
  useEffect(() => {
    let active = true;
    setSource(null);
    setSourceError('');
    void mediaSource(uri, { localPreview }).then(value => { if (active) setSource(value); })
      .catch(() => { if (active) setSourceError('Unable to load this media URL.'); });
    return () => { active = false; };
  }, [uri, localPreview]);
  return { source, sourceError };
}

export function VideoPlayer({ uri, captionsUri, captionLanguage }: { uri: string; captionsUri?: string | null; captionLanguage?: string }) {
  const { source, sourceError } = useMediaSource(uri);
  const [cues, setCues] = useState<{ start: number; end: number; text: string }[]>([]);
  const [captionsOn, setCaptionsOn] = useState(true);
  const [captionError, setCaptionError] = useState('');
  const player = useVideoPlayer(source);
  const { status, error } = useEvent(player, 'statusChange', { status: player.status });
  const time = useEvent(player, 'timeUpdate', { currentTime: player.currentTime, currentLiveTimestamp: null, currentOffsetFromLive: null, bufferedPosition: 0 });
  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setCues([]); setCaptionError(''); setCaptionsOn(true);
    if (!captionsUri) return () => { active = false; controller.abort(); };
    void (async () => {
      try {
        const resolved = await mediaSource(captionsUri);
        const response = await fetch(resolved.uri, { headers: resolved.headers, signal: controller.signal });
        if (!response.ok) throw new Error('Caption request failed.');
        const parsed = parseWebVtt(await response.text());
        if (active) setCues(parsed);
      } catch { if (active) setCaptionError('Captions could not be loaded.'); }
    })();
    return () => { active = false; controller.abort(); };
  }, [captionsUri]);
  useEffect(() => {
    player.timeUpdateEventInterval = 0.25;
    const subscription = AppState.addEventListener('change', state => { if (state !== 'active') player.pause(); });
    return () => subscription.remove();
  }, [player]);
  return <View>
    <VideoView player={player} nativeControls contentFit="contain" style={{ width: '100%', minWidth: 220, height: 240 }} />
    {!!captionsUri && <>
      <Pressable accessibilityRole="button" accessibilityLabel={`${captionsOn ? 'Turn off' : 'Turn on'} captions${captionLanguage ? ` (${captionLanguage})` : ''}`} accessibilityState={{ checked: captionsOn }} onPress={() => setCaptionsOn(value => !value)} style={{ minHeight: 44, justifyContent: 'center' }}><Text>{captionsOn ? 'Captions on' : 'Captions off'}</Text></Pressable>
      {captionsOn && <Text accessibilityLiveRegion="polite" style={{ textAlign: 'center', backgroundColor: '#172b4d', color: 'white', padding: 8 }}>{cues.find(cue => (time?.currentTime ?? player.currentTime) >= cue.start && (time?.currentTime ?? player.currentTime) < cue.end)?.text || ''}</Text>}
      {!!captionError && <Text accessibilityRole="alert">{captionError}</Text>}
    </>}
    {!!sourceError && <Text accessibilityRole="alert">{sourceError}</Text>}
    {status === 'error' && <><Text accessibilityRole="alert">Unable to play this video. {error?.message}</Text><Button title="Download original video" onPress={() => void downloadMedia(uri).catch(() => Alert.alert('Download unavailable', 'Unable to download this media.'))} /></>}
  </View>;
}

export function VoicePlayer({ uri, localPreview = false }: { uri: string; localPreview?: boolean }) {
  const { source, sourceError } = useMediaSource(uri, localPreview);
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
    <Button title="Download audio file" onPress={() => void downloadMedia(uri, { localPreview }).catch(() => Alert.alert('Download unavailable', 'Unable to download this media.'))} />
  </View>;
}
