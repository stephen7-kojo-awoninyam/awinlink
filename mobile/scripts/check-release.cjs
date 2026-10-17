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
try {
  process.env.EAS_BUILD_PROFILE = 'production';
  require('../app.config.js')();
  check(true, 'Production environment and app identifiers configured');
} catch (error) { check(false, error.message); }
finally {
  if (savedProfile === undefined) delete process.env.EAS_BUILD_PROFILE;
  else process.env.EAS_BUILD_PROFILE = savedProfile;
}
const config = require('../app.json').expo;
const splash = config.plugins.find(plugin => Array.isArray(plugin) && plugin[0] === 'expo-splash-screen')?.[1]?.image;
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
