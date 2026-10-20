const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const configure = require('../app.config.js');

test('Android APK refuses an unusable API or missing push configuration', () => {
  const original = { ...process.env };
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'awinlink-apk-'));
  try {
    const profile = require('../eas.json').build['android-apk'];
    Object.assign(process.env, profile.env, {
      EAS_BUILD_PROFILE: 'android-apk', EAS_BUILD_PLATFORM: 'android',
      AWINLINK_ANDROID_PACKAGE: 'com.awinlink.app',
    });
    delete process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
    delete process.env.AWINLINK_GOOGLE_SERVICES_FILE;
    assert.throws(configure, /owned EAS project UUID/);
    process.env.EXPO_PUBLIC_EAS_PROJECT_ID = '00000000-0000-4000-8000-000000000000';
    assert.throws(configure, /GOOGLE_SERVICES_FILE/);
    const google = path.join(directory, 'google-services.json');
    fs.writeFileSync(google, JSON.stringify({ client: [{ client_info: { android_client_info: { package_name: 'com.awinlink.app' } } }] }));
    process.env.AWINLINK_GOOGLE_SERVICES_FILE = google;
    const config = configure();
    assert.equal(config.android.package, 'com.awinlink.app');
    assert.equal(config.extra.eas.projectId, process.env.EXPO_PUBLIC_EAS_PROJECT_ID);
    assert.ok(config.android.blockedPermissions.includes('android.permission.SYSTEM_ALERT_WINDOW'));
    for (const value of ['', 'http://api.example', 'https://localhost', 'https://127.0.0.1', 'https://192.168.1.2', 'https://api.example/api/', 'https://user:secret@api.example']) {
      process.env.EXPO_PUBLIC_API_URL = value;
      assert.throws(configure, /EXPO_PUBLIC_API_URL/);
    }
    process.env.EXPO_PUBLIC_API_URL = profile.env.EXPO_PUBLIC_API_URL;
    delete process.env.EXPO_PUBLIC_DELETE_ACCOUNT_URL;
    assert.throws(configure, /DELETE_ACCOUNT_URL/);
    process.env.EXPO_PUBLIC_DELETE_ACCOUNT_URL = profile.env.EXPO_PUBLIC_DELETE_ACCOUNT_URL;
    fs.writeFileSync(google, JSON.stringify({ client: [{ client_info: { android_client_info: { package_name: 'com.wrong.app' } } }] }));
    assert.throws(configure, /does not match/);
  } finally {
    for (const key of Object.keys(process.env)) if (!(key in original)) delete process.env[key];
    Object.assign(process.env, original);
    // Only remove the unique test fixture created in the OS temp directory.
    assert.equal(path.dirname(directory), os.tmpdir());
    assert.ok(path.basename(directory).startsWith('awinlink-apk-'));
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('APK profile produces an internal release APK without submission or version changes', () => {
  const eas = require('../eas.json');
  const profile = eas.build['android-apk'];
  assert.equal(profile.extends, 'preview');
  assert.equal(eas.build.preview.distribution, 'internal');
  assert.equal(profile.environment, 'preview');
  assert.equal(profile.developmentClient, false);
  assert.equal(profile.android.buildType, 'apk');
  assert.equal(profile.android.resourceClass, 'medium');
  assert.equal(profile.android.credentialsSource, 'remote');
  assert.equal(profile.autoIncrement, undefined);
  assert.equal(eas.submit, undefined);
  assert.equal(eas.build.production.android.buildType, 'app-bundle');
  assert.match(require('../package.json').scripts['build:android:apk'], /--freeze-credentials/);
});
