const { expo } = require('./app.json');
const fs = require('node:fs');

function httpsUrl(value, name, originOnly = false) {
  let url;
  try { url = new URL(value); } catch { throw new Error(`Set ${name} to a valid HTTPS URL.`); }
  if (url.protocol !== 'https:' || url.username || url.password || (originOnly && (url.pathname !== '/' || url.search || url.hash))) {
    throw new Error(`${name} must be an HTTPS ${originOnly ? 'origin' : 'URL'} without credentials.`);
  }
  return url;
}

module.exports = () => {
  const production = process.env.EAS_BUILD_PROFILE === 'production';
  const projectId = process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  const androidPackage = process.env.AWINLINK_ANDROID_PACKAGE || expo.android.package;
  const iosBundle = process.env.AWINLINK_IOS_BUNDLE_IDENTIFIER || expo.ios.bundleIdentifier;
  const googleServicesFile = process.env.AWINLINK_GOOGLE_SERVICES_FILE;
  if (production) {
    httpsUrl(process.env.EXPO_PUBLIC_API_URL, 'EXPO_PUBLIC_API_URL', true);
    httpsUrl(process.env.EXPO_PUBLIC_WEB_URL, 'EXPO_PUBLIC_WEB_URL', true);
    for (const key of ['EXPO_PUBLIC_PRIVACY_URL', 'EXPO_PUBLIC_TERMS_URL', 'EXPO_PUBLIC_SUPPORT_URL']) httpsUrl(process.env[key], key);
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(projectId || '')) throw new Error('Set EXPO_PUBLIC_EAS_PROJECT_ID to your EAS project UUID.');
    if (![androidPackage, iosBundle].every(value => /^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$/.test(value || ''))) throw new Error('Set valid owned AWINLINK_ANDROID_PACKAGE and AWINLINK_IOS_BUNDLE_IDENTIFIER values.');
    if (process.env.EAS_BUILD_PLATFORM !== 'ios' && !googleServicesFile) throw new Error('Set AWINLINK_GOOGLE_SERVICES_FILE for Android FCM configuration.');
  }
  if (googleServicesFile) {
    const google = JSON.parse(fs.readFileSync(googleServicesFile, 'utf8'));
    if (!google.client?.some(client => client.client_info?.android_client_info?.package_name === androidPackage)) throw new Error('Google services configuration does not match AWINLINK_ANDROID_PACKAGE.');
  }
  return {
    ...expo,
    extra: { ...expo.extra, launch: { free: true, purchasesEnabled: false }, ...(projectId ? { eas: { projectId } } : {}) },
    android: {
      ...expo.android,
      blockedPermissions: ['android.permission.READ_EXTERNAL_STORAGE', 'android.permission.WRITE_EXTERNAL_STORAGE', ...(production ? ['android.permission.SYSTEM_ALERT_WINDOW'] : [])],
      ...(googleServicesFile ? { googleServicesFile } : {}),
      ...(androidPackage ? { package: androidPackage } : {}),
    },
    ios: {
      ...expo.ios,
      entitlements: { 'aps-environment': ['production', 'preview', 'preview-device'].includes(process.env.EAS_BUILD_PROFILE) ? 'production' : 'development' },
      ...(process.env.AWINLINK_APPLE_TEAM_ID ? { appleTeamId: process.env.AWINLINK_APPLE_TEAM_ID } : {}),
      ...(iosBundle ? { bundleIdentifier: iosBundle } : {}),
    },
  };
};
