const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const configure = require('../app.config.js');

test('release identities use the requested Android and iOS app ID', () => {
  const { expo } = require('../app.json');
  assert.equal(expo.android.package, 'com.awinlink.app');
  assert.equal(expo.ios.bundleIdentifier, 'com.awinlink.app');
  const metadata = require('../store/metadata.json');
  assert.equal(metadata.androidPackage, expo.android.package);
  assert.equal(metadata.iosBundleIdentifier, expo.ios.bundleIdentifier);
});

test('production validates real origins, identities, public policy links and FCM package', () => {
  const original = { ...process.env };
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'awinlink-release-config-'));
  try {
    Object.assign(process.env, {
      EAS_BUILD_PROFILE: 'production', EAS_BUILD_PLATFORM: 'android',
      EXPO_PUBLIC_API_URL: 'https://api.example', EXPO_PUBLIC_WEB_URL: 'https://app.example',
      EXPO_PUBLIC_EAS_PROJECT_ID: '00000000-0000-4000-8000-000000000000',
      AWINLINK_ANDROID_PACKAGE: 'com.example.awinlink', AWINLINK_IOS_BUNDLE_IDENTIFIER: 'com.example.awinlink',
      EXPO_PUBLIC_PRIVACY_URL: 'https://app.example/privacy', EXPO_PUBLIC_TERMS_URL: 'https://app.example/terms', EXPO_PUBLIC_SUPPORT_URL: 'https://app.example/support',
    });
    const google = path.join(temporary, 'google-services.json');
    process.env.AWINLINK_GOOGLE_SERVICES_FILE = google;
    fs.writeFileSync(google, JSON.stringify({ client: [{ client_info: { android_client_info: { package_name: 'com.example.awinlink' } } }] }));
    const config = configure();
    assert.equal(config.android.package, 'com.example.awinlink');
    assert.equal(config.ios.entitlements['aps-environment'], 'production');
    assert.ok(config.android.blockedPermissions.includes('android.permission.SYSTEM_ALERT_WINDOW'));
    process.env.EXPO_PUBLIC_API_URL = 'http://api.example';
    assert.throws(configure, /HTTPS/);
    process.env.EXPO_PUBLIC_API_URL = 'https://api.example';
    process.env.AWINLINK_ANDROID_PACKAGE = 'com.wrong.app';
    assert.throws(configure, /does not match/);
    process.env.AWINLINK_ANDROID_PACKAGE = 'com.example.awinlink';
    delete process.env.AWINLINK_GOOGLE_SERVICES_FILE;
    assert.throws(configure, /GOOGLE_SERVICES_FILE/);
    process.env.EAS_BUILD_PLATFORM = 'ios';
    assert.equal(configure().ios.bundleIdentifier, 'com.example.awinlink');
    delete process.env.EXPO_PUBLIC_PRIVACY_URL;
    assert.throws(configure, /PRIVACY_URL/);
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in original)) delete process.env[key];
    Object.assign(process.env, original);
    assert.equal(path.dirname(temporary), os.tmpdir());
    assert.ok(path.basename(temporary).startsWith('awinlink-release-config-'));
    fs.rmSync(temporary, { recursive: true, force: true });
  }
});
