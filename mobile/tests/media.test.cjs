const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const formats = require('../../static/js/recording-format.js');

test('Safari AAC/MP4, Chrome Opus/WebM and Firefox Ogg recording negotiation', () => {
  for (const type of ['audio/mp4', 'audio/webm;codecs=opus', 'audio/ogg;codecs=opus']) {
    assert.equal(formats.select({ isTypeSupported: value => value === type }), type);
  }
  assert.equal(formats.select({}), '');
  assert.equal(formats.select({ isTypeSupported: () => false }), '');
  assert.equal(formats.extension('audio/mp4;codecs=mp4a.40.2'), 'mp4');
  assert.equal(formats.extension('audio/webm;codecs=opus'), 'webm');
  assert.equal(formats.extension('audio/ogg;codecs=opus'), 'ogg');
  assert.equal(formats.extension('audio/mpeg'), 'mp3');
  assert.equal(formats.extension(''), 'bin');
});

test('local media resolves against API origin and JWT never reaches external media', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/api/client.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  vm.runInNewContext(compiled, {
    exports, URL, process: { env: { EXPO_PUBLIC_API_URL: 'https://app.up.railway.app' } },
    require: () => ({ getItemAsync: async () => 'test-token' }),
  });
  const local = await exports.mediaSource('/media/messages/audio/voice.webm');
  assert.equal(local.uri, 'https://app.up.railway.app/media/messages/audio/voice.webm');
  assert.equal(local.headers.Authorization, 'Bearer test-token');
  for (const uri of ['https://res.cloudinary.com/test/video/upload/voice.mp3', 'https://other.example/media/voice.webm', 'https://app.up.railway.app.evil.example/media/voice.webm']) {
    assert.equal((await exports.mediaSource(uri)).headers, undefined);
  }
});

test('voice uploads retain the real browser container and native AAC file metadata', async () => {
  const source = fs.readFileSync(path.join(__dirname, '../src/voice-upload.ts'), 'utf8');
  const compiled = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText;
  const exports = {};
  let blob = new Blob(['recorded'], { type: 'audio/mp4' });
  class Body { constructor() { this.fields = []; } append(...values) { this.fields.push(values); } }
  vm.runInNewContext(compiled, { exports, FormData: Body, fetch: async () => ({ ok: true, blob: async () => blob }) });
  for (const [type, extension] of [['audio/mp4', 'mp4'], ['audio/webm;codecs=opus', 'webm'], ['audio/ogg;codecs=opus', 'ogg']]) {
    blob = new Blob(['recorded'], { type });
    const result = await exports.createVoiceUpload('blob:recording', 'web');
    assert.equal(result.fields[1][1], blob);
    assert.equal(result.fields[1][2], `voice_message.${extension}`);
    assert.equal(exports.recordingMimeType({ isTypeSupported: value => value === type }), type);
  }
  const result = await exports.createVoiceUpload('file:///cache/recording.m4a', 'ios');
  assert.equal(result.fields[1][1].type, 'audio/mp4');
  assert.equal(result.fields[1][1].uri, 'file:///cache/recording.m4a');
  blob = new Blob([]);
  await assert.rejects(exports.createVoiceUpload('blob:empty', 'web'), /Nothing was recorded/);
});
