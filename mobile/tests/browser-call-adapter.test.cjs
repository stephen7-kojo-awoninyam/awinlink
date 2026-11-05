const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const ts = require('typescript');
const vm = require('node:vm');

test('browser media adapter attaches remote audio, mutes self preview, and releases elements', async () => {
  const effects = [], videos = [], states = [];
  const react = {
    useEffect: fn => effects.push(fn), useRef: () => ({ current: null }), useState: value => [value, next => states.push(next)],
    createElement: (_type, props) => {
      const video = { muted: props.muted, playsInline: props.playsInline, play: async () => {}, pause() { this.paused = true; } };
      props.ref.current = video; videos.push(video); return {};
    },
  };
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../src/calls/rtc.web.tsx'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(code, { exports, navigator: { mediaDevices: { getUserMedia: async () => ({ id: 'captured' }) } },
    require: name => name === 'react' ? react : name === 'react-native' ? {} : { jsx: () => ({}), jsxs: () => ({}) },
  });
  const stream = { id: 'remote' };
  exports.RTCView({ streamURL: exports.streamURL(stream) });
  const cleanup = effects.shift()();
  assert.equal(videos[0].srcObject, stream);
  assert.equal(videos[0].muted, false);
  assert.equal(videos[0].playsInline, true);
  cleanup(); assert.equal(videos[0].srcObject, null); assert.equal(videos[0].paused, true);
  exports.RTCView({ streamURL: exports.streamURL({ id: 'self' }), mirror: true });
  effects.shift()(); assert.equal(videos[1].muted, true);
  assert.equal((await exports.mediaDevices.getUserMedia({ audio: true })).id, 'captured');
});


test('Metro selects browser WebRTC on web and native WebRTC on Android', () => {
  const path = require('node:path');
  const { resolve } = require('metro-resolver');
  const context = {
    originModulePath: require.resolve('../src/calls/CallScreen.tsx'),
    sourceExts: ['js', 'jsx', 'json', 'ts', 'tsx'], assetExts: new Set(),
    mainFields: ['react-native', 'browser', 'main'], preferNativePlatform: true,
    getPackageForModule: () => null,
    fileSystemLookup(file) {
      try { return { exists: true, type: fs.statSync(file).isDirectory() ? 'd' : 'f', realPath: fs.realpathSync(file) }; }
      catch { return { exists: false }; }
    },
  };
  assert.equal(resolve(context, './rtc', 'web').filePath, path.resolve(__dirname, '../src/calls/rtc.web.tsx'));
  assert.equal(resolve(context, './rtc', 'android').filePath, path.resolve(__dirname, '../src/calls/rtc.tsx'));
});
