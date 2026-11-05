const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const configure = require('../app.config.js');

test('APNs environment follows signing profiles and rejects invalid overrides', () => {
  const saved = { ...process.env };
  try {
    delete process.env.AWINLINK_APNS_ENVIRONMENT;
    delete process.env.EAS_BUILD_PROFILE;
    assert.equal(configure().extra.apnsEnvironment, 'development');
    for (const profile of ['ios-device', 'ios-simulator', 'preview-device']) {
      process.env.EAS_BUILD_PROFILE = profile;
      const config = configure();
      assert.equal(config.extra.apnsEnvironment, 'production');
      assert.equal(config.ios.entitlements['aps-environment'], 'production');
    }
    process.env.AWINLINK_APNS_ENVIRONMENT = 'development';
    assert.equal(configure().ios.entitlements['aps-environment'], 'development');
    process.env.AWINLINK_APNS_ENVIRONMENT = 'sandbox';
    assert.throws(configure, /APNS_ENVIRONMENT/);
    delete process.env.AWINLINK_APNS_ENVIRONMENT;
    process.env.AWINLINK_IOS_BUNDLE_IDENTIFIER = 'com.example.awinlink-ios';
    assert.equal(configure().ios.bundleIdentifier, 'com.example.awinlink-ios');
    process.env.AWINLINK_IOS_BUNDLE_IDENTIFIER = 'com.example.awinlink_ios';
    assert.throws(configure, /IOS_BUNDLE_IDENTIFIER/);
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in saved)) delete process.env[key];
    Object.assign(process.env, saved);
  }
});

test('iOS forwards CallKit audio activation and registers the signed APNs environment even in debug JS', async () => {
  const events = {}, calls = [], exports = {};
  const native = { addEventListener: (event, handler) => { events[event] = handler; }, getInitialEvents: async () => [], clearInitialEvents() {} };
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../src/calls/nativeCallUI.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(code, { exports, __DEV__: true, setTimeout,
    require: name => ({
      'react-native': { Platform: { OS: 'ios' }, NativeModules: { WebRTCModule: {
        audioSessionDidActivate: () => calls.push('activate'), audioSessionDidDeactivate: () => calls.push('deactivate'),
      } } },
      'react-native-callkeep': { __esModule: true, default: native },
      'react-native-voip-push-notification': { __esModule: true, default: { addEventListener: (event, handler) => { events[`voip:${event}`] = handler; } } },
      'expo-constants': { __esModule: true, default: { expoConfig: { extra: { apnsEnvironment: 'production' } } } },
      'expo-secure-store': { getItemAsync: async () => 'expo-token', setItemAsync: async () => {} },
      '@/src/api/client': { apiRequest: async (url, options) => calls.push({ url, ...options }) },
      './callIdentity': {}, './callLifecycle': {},
    })[name],
  });
  exports.initializeNativeCallEvents();
  events.didActivateAudioSession(); events.didDeactivateAudioSession();
  assert.deepEqual(calls, ['activate', 'deactivate']);
  events['voip:register']('voip-token');
  await exports.registerVoipToken();
  assert.equal(calls[2].body.environment, 'production');
  assert.equal(calls[2].body.token, 'voip-token');
});

test('iOS source icon is 1024 square; splash and native dependencies exist', async () => {
  const config = require('../app.json').expo;
  const icon = fs.readFileSync(config.icon);
  assert.equal(icon.readUInt32BE(16), 1024); assert.equal(icon.readUInt32BE(20), 1024);
  // Expo's iOS icon generator removes source PNG transparency during prebuild.
  assert.ok([2, 6].includes(icon[25]));
  const splash = config.plugins.find(plugin => Array.isArray(plugin) && plugin[0] === 'expo-splash-screen')[1].image;
  assert.ok(fs.readFileSync(splash).readUInt32BE(16) > 0);
  for (const name of ['react-native-webrtc', 'react-native-callkeep', 'react-native-voip-push-notification']) assert.ok(require.resolve(`${name}/package.json`));
});

test('native auth writes device-bound credentials accessible to locked CallKit actions', async () => {
  const exports = {}, writes = [];
  const storage = { AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY: 'device-after-unlock',
    getItemAsync: async () => 'token', deleteItemAsync: async () => {},
    setItemAsync: async (...args) => writes.push(args),
  };
  const code = ts.transpileModule(fs.readFileSync(require.resolve('../src/auth/tokenStorage.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS },
  }).outputText;
  vm.runInNewContext(code, { exports, require: () => storage });
  await exports.setItemAsync('awinlink.access-token', 'token');
  assert.equal(writes[0][2].keychainAccessible, 'device-after-unlock');
  assert.equal(await exports.getItemAsync('awinlink.access-token'), 'token');
});
