const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function compile(name, globals, requireMock) {
  const source = fs.readFileSync(path.join(__dirname, '../src', name), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, { exports, URL, Blob, process: { env: { EXPO_PUBLIC_API_URL: 'https://app.example' } },
    require: requireMock || (() => ({ getItemAsync: async () => 'test-access-token' })), ...globals });
  return exports;
}

test('media URLs reject executable schemes and embedded credentials', async () => {
  const client = compile('api/client.ts', {});
  for (const uri of ['javascript:alert(1)', 'data:text/html,payload', 'file:///secret', 'https://user:pass@app.example/media/file']) {
    await assert.rejects(client.mediaSource(uri), /Unsupported file URL/);
  }
  assert.equal((await client.mediaSource('/media/messages/files/notes.pdf')).headers.Authorization, 'Bearer test-access-token');
  assert.equal((await client.mediaSource('https://external.example/file.pdf')).headers, undefined);
  assert.equal((await client.mediaSource('file:///cache/recording.m4a', { localPreview: true })).headers, undefined);
  assert.equal((await client.mediaSource('blob:local-recording', { localPreview: true })).uri, 'blob:local-recording');
  assert.equal((await client.mediaSource('/media/messages/audio/voice.wav?playback=mp3', { original: true })).uri,
    'https://app.example/media/messages/audio/voice.wav');
});

test('public proxy image URLs and nested private file URLs become absolute without rewriting text', () => {
  const client = compile('api/client.ts', {});
  const source = { caption: '/media/not-an-asset', image: '/media/talents/profile/photo.png',
    user: { profile_picture: '/media/profiles/avatar.jpg' }, lessons: [{ notes: '/media/learning/notes/notes.pdf', captions: '/media/learning/captions/lesson.vtt' }] };
  const result = client.resolveMediaFields(source);
  assert.equal(result.image, 'https://app.example/media/talents/profile/photo.png');
  assert.equal(result.user.profile_picture, 'https://app.example/media/profiles/avatar.jpg');
  assert.equal(result.lessons[0].notes, 'https://app.example/media/learning/notes/notes.pdf');
  assert.equal(result.lessons[0].captions, 'https://app.example/media/learning/captions/lesson.vtt');
  assert.equal(result.caption, source.caption);
  assert.equal(source.image, '/media/talents/profile/photo.png');
});

test('web and native upload preflight reject active filenames but retain recordings and documents', () => {
  const client = compile('api/client.ts', {});
  for (const name of ['attack.html', 'attack.SVG', 'attack.xhtml', 'attack.xml', 'attack.js', 'attack.exe']) {
    assert.throws(() => client.validateMultipartUploads({ entries: () => [['video', { name }]][Symbol.iterator]() }), /not supported/);
    assert.throws(() => client.validateMultipartUploads({ getParts: () => [{ name }] }), /not supported/);
  }
  for (const name of ['voice.m4a', 'voice.webm', 'camera.mov', 'clip.mp4', 'notes.pdf', 'notes.txt']) {
    client.validateMultipartUploads({ getParts: () => [{ name }] });
  }
});

test('web downloads use authenticated fetch and an inert download blob, never browser navigation', async () => {
  let created, clicked = false, revoked = false;
  const urls = class extends URL {};
  urls.createObjectURL = blob => { created = blob; return 'blob:audit-download'; };
  urls.revokeObjectURL = () => { revoked = true; };
  const anchor = { click() { clicked = true; } };
  const download = compile('media-download.ts', { URL: urls,
    document: { createElement: () => anchor }, setTimeout: fn => fn(),
    fetch: async (uri, options) => {
      assert.equal(options.headers.Authorization, 'Bearer fixture');
      return { ok: true, blob: async () => new Blob(['<script>attack</script>'], { type: 'text/html' }) };
    },
  }, name => name === 'react-native' ? { Platform: { OS: 'web' } } : name === './api/client' ? {
    mediaSource: async uri => ({ uri: 'https://app.example' + uri, headers: { Authorization: 'Bearer fixture' } }),
  } : {});
  await download.downloadMedia('/media/portfolio/files/legacy.html');
  assert.equal(created.type, 'application/octet-stream');
  assert.equal(anchor.download, 'legacy.html.download');
  assert.equal(anchor.href, 'blob:audit-download');
  assert.ok(clicked && revoked);
});

test('native file export retains JWT headers and cleans temporary bytes after success or failure', async () => {
  for (const fail of [false, true]) {
    let deleted = false, shared = false;
    const fileSystem = { cacheDirectory: 'file:///cache/',
      downloadAsync: async (uri, destination, options) => {
        assert.equal(uri, 'https://app.example/media/learning/notes/notes.pdf');
        assert.equal(options.headers.Authorization, 'Bearer fixture');
        assert.ok(destination.startsWith('file:///cache/'));
        return { status: fail ? 403 : 200 };
      }, deleteAsync: async () => { deleted = true; },
    };
    const module = compile('media-download.ts', {}, name => {
      if (name === 'react-native') return { Platform: { OS: 'ios' }, Share: { share: async () => { shared = true; } } };
      if (name === 'expo-file-system/legacy') return fileSystem;
      if (name === './api/client') return { mediaSource: async uri => ({ uri, headers: { Authorization: 'Bearer fixture' } }) };
      return {};
    });
    if (fail) await assert.rejects(module.downloadMedia('https://app.example/media/learning/notes/notes.pdf'), /Unable to download/);
    else await module.downloadMedia('https://app.example/media/learning/notes/notes.pdf');
    assert.equal(shared, !fail);
    assert.ok(deleted);
  }
});

test('attachment preview uses text nodes and does not interpret filenames as HTML', () => {
  const template = fs.readFileSync(path.join(__dirname, '../../messaging/templates/messaging/conversation.html'), 'utf8');
  assert.ok(!template.includes('attachmentPreview.innerHTML'));
  assert.match(template, /attachmentPreview\.textContent\s*=\s*files\.join\("\\n"\)/);
});

test('extensionless cloud media is exported with a safe media extension on native', async () => {
  let moved = false, deleted = false;
  const module = compile('media-download.ts', {}, name => {
    if (name === 'react-native') return { Platform: { OS: 'ios' }, Share: { share: async file => {
      assert.ok(file.url.endsWith('.mp4')); assert.equal(file.title, 'cloud-id.mp4');
    } } };
    if (name === './api/client') return { mediaSource: async uri => ({ uri }) };
    if (name === 'expo-file-system/legacy') return { cacheDirectory: 'file:///cache/',
      downloadAsync: async () => ({ status: 200, headers: { 'Content-Type': 'video/mp4' } }),
      moveAsync: async value => { assert.ok(value.to.endsWith('.mp4')); moved = true; },
      deleteAsync: async uri => { assert.ok(uri.endsWith('.mp4')); deleted = true; },
    };
    return {};
  });
  await module.downloadMedia('https://app.example/media/feed/videos/cloud-id');
  assert.ok(moved && deleted);
});

test('a trusted local recording export copies temporary bytes without deleting the recording', async () => {
  const original = 'file:///recordings/voice.m4a';
  let copied = false, shared = false;
  const module = compile('media-download.ts', {}, name => {
    if (name === 'react-native') return { Platform: { OS: 'ios' }, Share: { share: async file => {
      assert.ok(file.url.startsWith('file:///cache/')); shared = true;
    } } };
    if (name === './api/client') return { mediaSource: async (uri, options) => {
      assert.equal(options.localPreview, true); return { uri };
    } };
    if (name === 'expo-file-system/legacy') return { cacheDirectory: 'file:///cache/',
      copyAsync: async value => { assert.equal(value.from, original); assert.notEqual(value.to, original); copied = true; },
      downloadAsync: async () => { throw new Error('A local recording must not use the network.'); },
      deleteAsync: async uri => { assert.notEqual(uri, original); },
    };
    return {};
  });
  await module.downloadMedia(original, { localPreview: true });
  assert.ok(copied && shared);
});
