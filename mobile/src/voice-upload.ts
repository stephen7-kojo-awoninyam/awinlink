export function recordingMimeType(recorder?: { isTypeSupported?: (type: string) => boolean }) {
  return ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
    .find(type => recorder?.isTypeSupported?.(type));
}

export async function createVoiceUpload(uri: string, platform: string) {
  const body = new FormData();
  body.append('message_type', 'AUDIO');
  if (platform === 'web') {
    const response = await fetch(uri);
    if (!response.ok) throw new Error('Unable to read the voice recording.');
    const blob = await response.blob();
    if (!blob.size) throw new Error('Nothing was recorded. Please try again.');
    const extension = ({ 'audio/mp4': 'mp4', 'audio/ogg': 'ogg', 'audio/webm': 'webm', 'audio/mpeg': 'mp3', 'audio/wav': 'wav' } as Record<string, string>)[blob.type.split(';')[0]] || 'bin';
    body.append('audio', blob, `voice_message.${extension}`);
  } else {
    body.append('audio', { uri, name: 'voice_message.m4a', type: 'audio/mp4' } as unknown as Blob);
  }
  return body;
}
