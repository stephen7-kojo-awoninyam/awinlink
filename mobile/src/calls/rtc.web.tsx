import React, { useEffect, useRef, useState } from 'react';
import { Pressable, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import type * as Native from 'react-native-webrtc';

const streams = new Map<string, globalThis.MediaStream>();
const ids = new WeakMap<globalThis.MediaStream, string>();
let sequence = 0;
export function streamURL(value: Native.MediaStream) {
  const stream = value as unknown as globalThis.MediaStream;
  let id = ids.get(stream);
  if (!id) { id = String(++sequence); ids.set(stream, id); }
  streams.set(id, stream);
  return id;
}
// Native types describe the shared subset used by CallScreen. Browser objects
// remain native browser WebRTC objects at runtime.
export const MediaStream = globalThis.MediaStream as unknown as typeof Native.MediaStream;
export const RTCPeerConnection = globalThis.RTCPeerConnection as unknown as typeof Native.RTCPeerConnection;
export const mediaDevices = {
  async getUserMedia(constraints: Parameters<typeof navigator.mediaDevices.getUserMedia>[0]) {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('Calling requires HTTPS and a browser with microphone support.');
    return await navigator.mediaDevices.getUserMedia(constraints) as unknown as Native.MediaStream;
  },
};
export function RTCView({ streamURL: url, style, objectFit, mirror }: {
  streamURL: string; style?: StyleProp<ViewStyle>; objectFit?: 'cover' | 'contain'; mirror?: boolean;
}) {
  const stream = streams.get(url);
  const ref = useRef<HTMLVideoElement>(null);
  const [blocked, setBlocked] = useState(false);
  const play = () => { ref.current?.play().then(() => setBlocked(false)).catch(() => setBlocked(true)); };
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.srcObject = stream || null;
    streams.delete(url);
    play();
    return () => { element.pause(); element.srcObject = null; streams.delete(url); };
  }, [url]);
  return <View style={style}>
    {React.createElement('video', { ref, autoPlay: true, playsInline: true, muted: !!mirror,
      style: { width: '100%', height: '100%', objectFit: objectFit || 'contain', transform: mirror ? 'scaleX(-1)' : undefined } })}
    {blocked && !mirror && <Pressable accessibilityRole="button" onPress={play} style={{ position: 'absolute', bottom: 8, padding: 12, backgroundColor: '#273149' }}><Text style={{ color: '#fff' }}>Enable call audio</Text></Pressable>}
  </View>;
}
