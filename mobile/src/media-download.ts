import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import { mediaSource } from './api/client';
import { savePrivateArtifact } from './marketplace/files';

function exportName(name: string, type?: string) {
  if (/\.[a-z0-9]{1,12}$/i.test(name)) return name;
  const extension = ({ 'video/mp4': 'mp4', 'video/webm': 'webm', 'video/quicktime': 'mov',
    'audio/mpeg': 'mp3', 'audio/mp4': 'm4a', 'audio/webm': 'webm', 'audio/ogg': 'ogg',
    'audio/wav': 'wav', 'image/jpeg': 'jpg', 'image/png': 'png', 'application/pdf': 'pdf' } as Record<string, string>)[type?.split(';')[0] || ''] || 'bin';
  return `${name}.${extension}`;
}

// Download bytes with authentication; opening the URL in a separate browser
// loses native JWT headers. Never render a downloaded HTML/SVG blob in the app.
export async function downloadMedia(uri: string, options: { localPreview?: boolean } = {}) {
  const source = await mediaSource(uri, { original: true, localPreview: options.localPreview });
  let name = decodeURIComponent(new URL(source.uri).pathname.split('/').pop() || 'download')
    .replace(/[\\/:\x00-\x1f\x7f]/g, '_').slice(0, 180);
  if (/\.(html?|xhtml|svgz?|xml|js|mjs|exe|bat|cmd|com|ps1|sh)$/i.test(name)) name += '.download';
  if (Platform.OS === 'web') {
    const response = await fetch(source.uri, { headers: source.headers });
    if (!response.ok) throw new Error('Unable to download this file.');
    const blob = new Blob([await response.blob()], { type: 'application/octet-stream' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = exportName(name, response.headers?.get('Content-Type') || undefined); anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    return;
  }
  if (!FileSystem.cacheDirectory) throw new Error('File storage is unavailable.');
  let destination = FileSystem.cacheDirectory + Date.now() + '-' + Math.random().toString(36).slice(2) + '-' + encodeURIComponent(name);
  try {
    const response = options.localPreview && source.uri.startsWith('file:')
      ? (await FileSystem.copyAsync({ from: source.uri, to: destination }), { status: 200, headers: {} })
      : await FileSystem.downloadAsync(source.uri, destination, { headers: source.headers });
    if (response.status !== 200) throw new Error('Unable to download this file.');
    const type = Object.entries(response.headers || {}).find(([key]) => key.toLowerCase() === 'content-type')?.[1];
    const named = exportName(name, typeof type === 'string' ? type : undefined);
    if (named !== name) {
      const renamed = destination + '.' + named.split('.').pop();
      await FileSystem.moveAsync({ from: destination, to: renamed });
      destination = renamed;
      name = named;
    }
    if (Platform.OS === 'ios') {
      await Share.share({ url: destination, title: name });
    } else {
      const info = await FileSystem.getInfoAsync(destination);
      if (info.exists && info.size > 50 * 1024 * 1024) throw new Error('This file is too large to export on this device.');
      const content = await FileSystem.readAsStringAsync(destination, { encoding: FileSystem.EncodingType.Base64 });
      await savePrivateArtifact({ filename: name, content });
    }
  } finally {
    await FileSystem.deleteAsync(destination, { idempotent: true });
  }
}
