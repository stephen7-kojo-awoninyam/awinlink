const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const { patchAppDelegate } = require('../plugins/withNativeCalls.cjs');

test('native UUIDs round trip across cold-start answer/end events', () => {
  const source = fs.readFileSync(require.resolve('../src/calls/callIdentity.ts'), 'utf8');
  const exports = {};
  vm.runInNewContext(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, { exports });
  for (const id of [1, 42, 0xffffffffffff]) assert.equal(exports.callID(exports.callUUID(id).toUpperCase()), id);
  for (const id of [0, -1, NaN, 1.5, 0x1000000000000]) assert.throws(() => exports.callUUID(id));
  for (const uuid of ['bad', 'a7100000-0000-4000-8000-000000000000', 'a7100000-0000-4000-8000-00000000000z']) assert.equal(exports.callID(uuid), null);
});

test('Swift startup installs PushKit before React and remains idempotent', () => {
  const source = 'func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {\n return super.application(application, didFinishLaunchingWithOptions: launchOptions)\n}';
  const patched = patchAppDelegate(source, 'swift');
  assert.ok(patched.indexOf('AwinlinkCallPush.start()') < patched.indexOf('return super'));
  assert.equal(patchAppDelegate(patched, 'swift'), patched);
  assert.throws(() => patchAppDelegate('unknown', 'swift'), /Cannot locate/);
  assert.throws(() => patchAppDelegate(source, 'objc'), /Swift/);
});

test('native answer rechecks backend state, deduplicates, and routes mute/end to active media', async () => {
  const events = {};
  const calls = [];
  const identity = {};
  const compile = source => ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true } }).outputText;
  vm.runInNewContext(compile(fs.readFileSync(require.resolve('../src/calls/callIdentity.ts'), 'utf8')), { exports: identity });
  const native = new Proxy({
    addEventListener: (name, fn) => { events[name] = fn; },
    getInitialEvents: async () => [], setup: async () => {}, hasPhoneAccount: async () => true,
  }, { get: (target, key) => target[key] || ((...args) => { calls.push([key, ...args]); }) });
  let requests = 0;
  const exports = {};
  vm.runInNewContext(compile(fs.readFileSync(require.resolve('../src/calls/nativeCallUI.ts'), 'utf8')), {
    exports, __DEV__: true, setTimeout,
    require: name => ({
      'react-native': { Platform: { OS: 'android' }, AppRegistry: { registerHeadlessTask() {} } },
      'react-native-callkeep': { __esModule: true, default: native, CONSTANTS: { END_CALL_REASONS: { REMOTE_ENDED: 2 } } },
      'react-native-voip-push-notification': {}, 'expo-secure-store': {},
      '@/src/api/client': { apiRequest: async () => { requests++; return [{ id: 42, conversation: 1, call_type: 'VOICE', caller_name: 'Caller' }]; } },
      './callIdentity': identity,
      './callLifecycle': { callHasEnded: () => false, finishCallRequest: (_id, work) => work() },
    })[name],
  });
  const answers = [];
  await exports.enableNativeCallUI(call => answers.push(call.id));
  events.answerCall({ callUUID: identity.callUUID(42) });
  events.answerCall({ callUUID: identity.callUUID(42) });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests, 1);
  assert.deepEqual(answers, [42]);
  let muted = false, ended = false;
  exports.bindNativeCall(42, true, 'Caller', false, { mute: value => { muted = value; }, hold() {}, end: () => { ended = true; } });
  events.didPerformSetMutedCallAction({ callUUID: identity.callUUID(42), muted: true });
  events.endCall({ callUUID: identity.callUUID(42) });
  assert.equal(muted, true);
  assert.equal(ended, true);
  events.answerCall({ callUUID: identity.callUUID(42) });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests, 1);
  assert.deepEqual(answers, [42]);
});
