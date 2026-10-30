import { useEffect, useState } from 'react';
import { mediaSource } from '@/src/api/client';

// HTML media elements cannot attach a JWT header. Fetch protected local media
// with the existing API token, and release the blob URL when it leaves the UI.
function BrowserMedia({ uri, captionsUri, captionLanguage, audio = false, localPreview = false }: { uri: string; captionsUri?: string | null; captionLanguage?: string; audio?: boolean; localPreview?: boolean }) {
  const [source, setSource] = useState('');
  const [captionSource, setCaptionSource] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    let objectUrl = '';
    setSource(''); setError('');
    void (async () => {
      try {
        const resolved = await mediaSource(uri, { localPreview });
        if (resolved.headers) {
          const response = await fetch(resolved.uri, { headers: resolved.headers, signal: controller.signal });
          if (!response.ok) throw new Error(`Media request failed (${response.status}).`);
          const blob = await response.blob();
          if (controller.signal.aborted) return;
          objectUrl = URL.createObjectURL(blob);
          setSource(objectUrl);
        } else if (!controller.signal.aborted) setSource(resolved.uri);
      } catch (e) { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : 'Unable to load media.'); }
    })();
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [uri, localPreview]);
  useEffect(() => {
    const controller = new AbortController(); let objectUrl = '';
    setCaptionSource('');
    if (!captionsUri) return () => controller.abort();
    void (async () => {
      try {
        const resolved = await mediaSource(captionsUri);
        const response = await fetch(resolved.uri, { headers: resolved.headers, signal: controller.signal });
        if (!response.ok) throw new Error('Caption request failed.');
        objectUrl = URL.createObjectURL(await response.blob());
        if (!controller.signal.aborted) setCaptionSource(objectUrl);
      } catch { /* The video remains usable when an optional caption track fails. */ }
    })();
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [captionsUri]);
  return <div style={{ width: '100%', minWidth: 220 }}>
    {source && (audio
      ? <audio controls preload="metadata" src={source} onError={() => setError('Unable to play this voice message.')} style={{ width: '100%' }} />
      : <video controls playsInline preload="metadata" src={source} onError={() => setError('Unable to play this video.')} style={{ width: '100%', maxHeight: 400 }}>{captionSource && <track kind="captions" src={captionSource} srcLang={captionLanguage || 'en'} label={captionLanguage || 'Captions'} default />}</video>)}
    {error && <p role="alert">{error}</p>}
  </div>;
}

export function VideoPlayer({ uri, captionsUri, captionLanguage }: { uri: string; captionsUri?: string | null; captionLanguage?: string }) { return <BrowserMedia uri={uri} captionsUri={captionsUri} captionLanguage={captionLanguage} />; }
export function VoicePlayer({ uri, localPreview = false }: { uri: string; localPreview?: boolean }) { return <BrowserMedia uri={uri} audio localPreview={localPreview} />; }
