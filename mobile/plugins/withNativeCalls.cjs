const fs = require('node:fs');
const path = require('node:path');
const { withAppDelegate, withInfoPlist, withAndroidManifest, withDangerousMod, withXcodeProject, withAppBuildGradle, IOSConfig } = require('expo/config-plugins');

function patchAppDelegate(source, language) {
  if (source.includes('AwinlinkCallPush.start()')) return source;
  if (language !== 'swift') throw new Error('Awinlink native calls require the Expo Swift AppDelegate.');
  const signature = /(didFinishLaunchingWithOptions[^]*?-> Bool\s*\{)/;
  if (!signature.test(source)) throw new Error('Cannot locate AppDelegate launch method for native calls.');
  return source.replace(signature, '$1\n    AwinlinkCallPush.start()');
}

module.exports = config => {
  config = withInfoPlist(config, mod => {
    mod.modResults.UIBackgroundModes = [...new Set([...(mod.modResults.UIBackgroundModes || []), 'voip', 'audio', 'remote-notification'])];
    return mod;
  });
  config = withAppDelegate(config, mod => { mod.modResults.contents = patchAppDelegate(mod.modResults.contents, mod.modResults.language); return mod; });
  config = withDangerousMod(config, ['ios', async mod => {
    const name = mod.modRequest.projectName || IOSConfig.XcodeUtils.getProjectName(mod.modRequest.projectRoot);
    const directory = path.join(mod.modRequest.platformProjectRoot, name);
    for (const file of ['AwinlinkCallPush.h', 'AwinlinkCallPush.m']) fs.copyFileSync(path.join(__dirname, 'native-calls', file), path.join(directory, file));
    const header = path.join(directory, `${name}-Bridging-Header.h`);
    let content = fs.existsSync(header) ? fs.readFileSync(header, 'utf8') : '';
    if (!content.includes('"AwinlinkCallPush.h"')) fs.writeFileSync(header, `${content}\n#import "AwinlinkCallPush.h"\n`);
    return mod;
  }]);
  config = withXcodeProject(config, mod => {
    const name = mod.modRequest.projectName || IOSConfig.XcodeUtils.getProjectName(mod.modRequest.projectRoot);
    const file = `${name}/AwinlinkCallPush.m`;
    if (!mod.modResults.hasFile(file)) IOSConfig.XcodeUtils.addBuildSourceFileToGroup({ filepath: file, groupName: name, project: mod.modResults });
    return mod;
  });
  config = withAndroidManifest(config, mod => {
    const manifest = mod.modResults.manifest;
    manifest.$['xmlns:tools'] = 'http://schemas.android.com/tools';
    const application = manifest.application[0];
    const services = application.service || (application.service = []);
    const add = service => { if (!services.some(item => item.$['android:name'] === service.$['android:name'])) services.push(service); };
    add({ $: { 'android:name': 'expo.modules.notifications.service.ExpoFirebaseMessagingService', 'tools:node': 'remove' } });
    add({ $: { 'android:name': 'com.awinlink.calls.AwinlinkMessagingService', 'android:exported': 'false' }, 'intent-filter': [{ action: [{ $: { 'android:name': 'com.google.firebase.MESSAGING_EVENT' } }] }] });
    add({ $: { 'android:name': 'io.wazo.callkeep.VoiceConnectionService', 'android:exported': 'true', 'android:permission': 'android.permission.BIND_TELECOM_CONNECTION_SERVICE', 'android:foregroundServiceType': 'phoneCall' }, 'intent-filter': [{ action: [{ $: { 'android:name': 'android.telecom.ConnectionService' } }] }] });
    add({ $: { 'android:name': 'io.wazo.callkeep.RNCallKeepBackgroundMessagingService', 'android:exported': 'false' } });
    manifest['uses-permission'] ||= [];
    for (const permission of ['android.permission.FOREGROUND_SERVICE', 'android.permission.FOREGROUND_SERVICE_PHONE_CALL', 'android.permission.MANAGE_OWN_CALLS']) {
      if (!manifest['uses-permission'].some(item => item.$['android:name'] === permission)) manifest['uses-permission'].push({ $: { 'android:name': permission } });
    }
    return mod;
  });
  config = withDangerousMod(config, ['android', async mod => {
    const directory = path.join(mod.modRequest.platformProjectRoot, 'app/src/main/java/com/awinlink/calls');
    fs.mkdirSync(directory, { recursive: true });
    fs.copyFileSync(path.join(__dirname, 'native-calls/AwinlinkMessagingService.kt'), path.join(directory, 'AwinlinkMessagingService.kt'));
    return mod;
  }]);
  return withAppBuildGradle(config, mod => {
    if (!mod.modResults.contents.includes('// Awinlink native call push')) mod.modResults.contents += '\n// Awinlink native call push\ndependencies {\n  implementation project(":expo-notifications")\n  implementation "com.google.firebase:firebase-messaging:25.0.1"\n}\n';
    return mod;
  });
};
module.exports.patchAppDelegate = patchAppDelegate;
