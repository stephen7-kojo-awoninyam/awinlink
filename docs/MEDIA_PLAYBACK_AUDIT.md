# Voice and feed video audit — 2026-10-16

## Findings and fixes

| Confirmed cause | Correction |
| --- | --- |
| Default Cloudinary storage sent audio and video to the image API and generated image delivery URLs. | `config/media_storage.py` routes the existing voice/video folders to resource type `video`, including IDs prefixed with the Cloudinary storage `media/` prefix. Audio delivery uses MP3; video uses MP4/H.264/AAC. Image handling remains inherited. |
| Existing local AV paths had no production route and no byte range support. | `config/media_views.py` serves those paths with GET, HEAD, MIME headers, Content-Length, byte ranges, session/JWT authentication, conversation membership and existing feed visibility rules, even with DEBUG disabled. |
| Nine existing local recordings use Opus/WebM, which is unsuitable for older iOS players. | Local storage URLs request cached MP3 voice or MP4/H.264/AAC video derivatives. `config/media_transcoding.py` uses bundled FFmpeg, limits conversion to one encoding thread with a 60-second timeout, and atomically caches the result. Originals and DB field values remain unchanged. Invalid source files retain an original download URL and return a controlled conversion error. |
| Web format negotiation omitted an explicit Safari MP4 option. | Browser-supported recording MIME selection includes MP4/AAC, keeps WebM/Opus preferred where supported, and derives the filename extension from the actual recorded blob. Unknown types are no longer labelled WebM. |
| Message API responses omitted serializer request context. | Create, list and read responses now return absolute attachment URLs. |
| Mobile feed displayed a video placeholder; voice attachments opened an external application. | Native Expo video/audio players and HTML web players provide playback controls. Native audio includes pause, replay, progress and seeking; video includes native controls. Players release resources on unmount and native playback pauses when the app becomes inactive. |
| Mobile had no voice recording UI. | Recording, stop, preview, discard, upload, error and retry flows use the existing message API. Native recordings use AAC/M4A; web recording uses a supported browser format. Failed sends retain the pending recording. |

## End-to-end paths

- Django voice: conversation template → MediaRecorder → actual MIME/extension → multipart POST `/messages/<conversation_id>/send/` → `messaging.views.send_message` → `Message.audio` → configured storage → audio controls.
- Mobile voice: `VoiceRecorder` → Expo Audio → multipart POST `/api/messaging/conversations/<id>/messages/create/` → `SendMessageAPIView` / `MessageSerializer` → the same `Message.audio` field → `VoicePlayer`.
- Feed video: existing Django post form or API upload → `Post.video` under `feed/videos/` → default storage → Django `post_card.html` or mobile `FeedPostCard` / `VideoPlayer`. Existing captions, images, likes and comments are retained.
- Local playback: `/media/messages/audio/...`, `/media/messages/videos/...`, `/media/feed/videos/...` → permission check → original or cached derivative → byte-range response. Removing the `playback` query parameter accesses the original, subject to the same permission checks.
- Cloud playback: stored public ID → HTTPS Cloudinary video delivery transformation. Original assets are not replaced, renamed, migrated or deleted.

## Configuration and Railway compatibility

- Complete `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`, or a `CLOUDINARY_URL`, selects Cloudinary. No credentials selects local playback storage.
- Local Railway media requires `MEDIA_ROOT` on a persistent volume; otherwise container replacement can remove uploads. Existing production local files must remain at their existing names under that volume. This work does not move any media.
- Install `requirements.txt`, including `imageio-ffmpeg==0.6.0`. The legacy ignored `requirements.render.txt` also includes the new FFmpeg dependency; `requirements.txt` remains the complete dependency list.
- FFmpeg is bundled for common Windows and Linux wheel platforms. `IMAGEIO_FFMPEG_EXE` can override the executable. Cached derivatives live under `MEDIA_ROOT/.playback-cache`; their keys change when the source changes. First local playback incurs conversion time; remote Cloudinary delivery uses Cloudinary's conversion instead.
- Cloudinary strict transformation policies or account restrictions must permit the requested MP3 and H.264/AAC delivery transformations. Provider requests were mocked during testing; no production asset was uploaded or modified.
- Native media requests attach the current JWT only to the configured API origin's `/media/` URLs. External Cloudinary URLs never receive account tokens. HTML media cannot attach JWT headers, so the Expo web player fetches protected local media into a temporary blob URL and revokes it on unmount. This web fallback buffers that file; native clients and Django web players use byte ranges directly.
- Expo Audio and Video add native modules. A rebuilt Android/iOS app is needed; no build was published. The audio plugin requests microphone permission without enabling background recording or playback.

## Regression coverage and validation

- `config/test_media.py`: upload resource types and prefixes, original IDs, delivery codecs, local legacy fallback, Railway configuration with individual credentials and CLOUDINARY_URL, multipart voice upload, absolute API URLs, JWT/session-compatible access control, private/public feed visibility, HEAD, normal/suffix/invalid ranges, real MP3 and H.264/AAC conversion, cache reuse, unchanged originals, and controlled failures on invalid media.
- `mobile/tests/media.test.cjs`: recording negotiation, native AAC metadata, browser blob MIME/filename agreement, empty recording rejection, relative media URL resolution and prevention of token leakage to external origins.
- `mobile/tests/media-browser.test.cjs`: real Chrome voice MediaRecorder encoding and real audio/video decoding, play/pause, playback progression and controls at 1440px and 390px. Synthetic oscillator input and an FFmpeg-generated H.264/AAC video only; it does not claim physical microphone or native device coverage.
- 31 focused Django media, deployment, message upload/reply/read/notification and feed regressions passed. Three JavaScript regressions and the real browser test passed. TypeScript checking, mobile web export and whitespace checks passed.
- A broader initial messaging run exposed an existing unrelated failure: `ConversationListSearchTests.test_list_search_includes_participant_username` expects `mobileGlobalSearch`, while the existing conversation list template uses `conversationSearch`. Neither file was changed to address that failure.
- Read-only FFmpeg inspection found 9 existing voice recordings, all readable Opus audio, and no local feed/message video fixtures. No existing media was rewritten.

Run from the repository root:

```powershell
.venv/Scripts/python.exe scripts/test_media.py config.test_media config.test_deployment
cd mobile
npm.cmd run typecheck
npm.cmd run test:media
$env:MEDIA_TEST_CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
npm.cmd run test:media
```

The browser test skips when `MEDIA_TEST_CHROME` is unset. `scripts/test_media.py` uses an isolated in-memory database and temporary test media. Its default labels also include the broader messaging suite and the unrelated existing UI assertion described above.

Live Railway, live Cloudinary transformations, physical Android/iOS devices and Safari were not exercised. No deployment, commit, push, database migration, or modification of existing media was performed. Pre-existing working-tree changes were preserved.

## Provider references

- [Cloudinary audio resource types and delivery](https://cloudinary.com/documentation/audio_transformations)
- [Cloudinary video transcoding](https://cloudinary.com/documentation/video_transcoding)
- [Expo SDK 57 Audio](https://docs.expo.dev/versions/v57.0.0/sdk/audio/) and [Video](https://docs.expo.dev/versions/v57.0.0/sdk/video/)
- [Bundled FFmpeg wheels and executable override](https://github.com/imageio/imageio-ffmpeg)
