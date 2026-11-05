export { mediaDevices, RTCPeerConnection, RTCView, MediaStream } from 'react-native-webrtc';
import type { MediaStream } from 'react-native-webrtc';
export const streamURL = (stream: MediaStream) => stream.toURL();
