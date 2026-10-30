import { useEffect, useState } from 'react';
import { Image, Platform, type ImageProps, type ImageSourcePropType } from 'react-native';
import { mediaSource } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';

type Props = Omit<ImageProps, 'source'> & { uri: string };

// Native Image supports request headers; web images need an authenticated fetch
// and a temporary blob URL. Neither path reuses a previous account's source.
export function AuthorizedImage({ uri, ...props }: Props) {
  const { user } = useAuth();
  const scope = `${user?.id ?? ''}:${user?.role ?? ''}:${uri}`;
  const [loaded, setLoaded] = useState<{ scope: string; source: ImageSourcePropType } | null>(null);
  useEffect(() => {
    let active = true, blobUrl = '';
    const controller = new AbortController();
    setLoaded(null);
    void (async () => {
      try {
        const source = await mediaSource(uri);
        if (!active) return;
        if (Platform.OS === 'web' && source.headers) {
          const response = await fetch(source.uri, { headers: source.headers, signal: controller.signal });
          if (!response.ok) throw new Error('Image unavailable.');
          const blob = await response.blob();
          if (!active) return;
          blobUrl = URL.createObjectURL(blob);
          setLoaded({ scope, source: { uri: blobUrl } });
        } else {
          setLoaded({ scope, source: { ...source, cache: 'reload' } });
        }
      } catch { if (active) setLoaded(null); }
    })();
    return () => {
      active = false;
      controller.abort();
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [uri, scope]);
  if (!loaded || loaded.scope !== scope) return null;
  return <Image {...props} source={loaded.source} />;
}
