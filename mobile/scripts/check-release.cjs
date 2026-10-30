/* Local validation only. Does not build remotely, upload, submit, or deploy. */
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
process.env.NODE_ENV ||= 'production';
require('@expo/env').load(root);
let failures = 0;
function check(ok, description) {
  console.log(`${ok ? 'PASS' : 'BLOCKED'} ${description}`);
  if (!ok) failures++;
}
const savedProfile = process.env.EAS_BUILD_PROFILE;
let releaseConfigLoaded = false;
for (const key of [
  'EXPO_PUBLIC_API_URL', 'EXPO_PUBLIC_WEB_URL', 'EXPO_PUBLIC_EAS_PROJECT_ID',
  'EXPO_PUBLIC_PRIVACY_URL', 'EXPO_PUBLIC_TERMS_URL', 'EXPO_PUBLIC_SUPPORT_URL',
  'EXPO_PUBLIC_DELETE_ACCOUNT_URL', 'AWINLINK_GOOGLE_SERVICES_FILE',
]) check(Boolean(process.env[key]), `Production setting present: ${key}`);
try {
  process.env.EAS_BUILD_PROFILE = 'production';
  require('../app.config.js')();
  releaseConfigLoaded = true;
  check(true, 'Production environment and app identifiers configured');
} catch (error) {
  const reason = error.code === 'ENOENT'
    ? 'AWINLINK_GOOGLE_SERVICES_FILE points to a file that is unavailable.'
    : error.message;
  check(false, reason);
}
finally {
  if (savedProfile === undefined) delete process.env.EAS_BUILD_PROFILE;
  else process.env.EAS_BUILD_PROFILE = savedProfile;
}
const baseConfig = require('../app.json').expo;
const metadata = require('../store/metadata.json');
let config = baseConfig;
try { config = require('../app.config.js')(); } catch { /* The detailed blocking reason was emitted above. */ }
check(metadata.androidPackage === config.android.package, 'Android package matches the Play listing metadata');
check(config.android.permissions?.includes('android.permission.CAMERA') && config.android.permissions?.includes('android.permission.RECORD_AUDIO'), 'Android camera and microphone permissions remain declared for calls');
if (releaseConfigLoaded) {
  check(config.android.blockedPermissions?.includes('android.permission.READ_EXTERNAL_STORAGE') && config.android.blockedPermissions?.includes('android.permission.WRITE_EXTERNAL_STORAGE'), 'Broad legacy storage permissions remain blocked');
  check(config.android.blockedPermissions?.includes('android.permission.SYSTEM_ALERT_WINDOW'), 'Overlay permission remains blocked in production builds');
} else {
  console.log('SKIP Production-only permission checks require valid release configuration.');
}
const splash = baseConfig.plugins.find(plugin => Array.isArray(plugin) && plugin[0] === 'expo-splash-screen')?.[1]?.image;
for (const asset of [config.icon, config.android.adaptiveIcon.foregroundImage, splash]) {
  check(fs.existsSync(path.resolve(root, asset)), `Asset exists: ${asset}`);
}
const eas = require('../eas.json');
check(eas.build.production.distribution === 'store' && eas.build.production.android.buildType === 'app-bundle', 'Production AAB/iOS store build profiles configured');
check(!eas.submit, 'Build configuration does not submit or publish');
check(config.plugins.includes('expo-secure-store'), 'SecureStore backup plugin configured');
for (const source of ['src/jetpack-compose/index.ts', 'src/swift-ui/index.tsx']) {
  check(fs.existsSync(path.resolve(root, 'node_modules/@expo/ui', source)), `Expo UI dependency source: ${source}`);
}
console.log('Signing, native device behavior, store metadata, and service delivery require separate verification.');
process.exitCode = failures ? 1 : 0;
