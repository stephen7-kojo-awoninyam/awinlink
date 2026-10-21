import { Platform, Share } from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';

export async function savePrivateArtifact(file: { filename: string; content: string }) {
  const name = file.filename.replace(/[\\/:\x00-\x1f\x7f]/g, '_').slice(0, 200) || 'delivery';
  if (Platform.OS === 'web') {
    const bytes = Uint8Array.from(atob(file.content), character => character.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], { type: 'application/octet-stream' }));
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = name; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } else if (Platform.OS === 'android') {
    const access = await FileSystem.StorageAccessFramework.requestDirectoryPermissionsAsync();
    if (!access.granted) return;
    const uri = await FileSystem.StorageAccessFramework.createFileAsync(access.directoryUri, name, 'application/octet-stream');
    await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.Base64 });
  } else {
    if (!FileSystem.cacheDirectory) throw Error('File storage is unavailable.');
    const uri = FileSystem.cacheDirectory + Date.now() + '-' + encodeURIComponent(name);
    try {
      await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.Base64 });
      await Share.share({ url: uri, title: name });
    } finally {
      await FileSystem.deleteAsync(uri, { idempotent: true });
    }
  }
}
