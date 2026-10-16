/* Enable the existing react-native-webrtc Android MediaProjection service. */
const { withMainApplication, AndroidConfig } = require('expo/config-plugins');
function enableService(contents, language) {
  const assignment = 'com.oney.WebRTCModule.WebRTCModuleOptions.getInstance().enableMediaProjectionService = true';
  if (contents.includes(assignment)) return contents;
  const match = /super\.onCreate\(\);?/;
  if (!match.test(contents)) throw new Error('Cannot configure classroom screen sharing: MainApplication.onCreate is missing.');
  return contents.replace(match, value => `${value}\n    ${assignment}${language === 'java' ? ';' : ''}`);
}
module.exports = config => {
  config = AndroidConfig.Permissions.withPermissions(config, [
    'android.permission.FOREGROUND_SERVICE', 'android.permission.FOREGROUND_SERVICE_MEDIA_PROJECTION',
  ]);
  return withMainApplication(config, mod => {
    mod.modResults.contents = enableService(mod.modResults.contents, mod.modResults.language);
    return mod;
  });
};
module.exports.enableService = enableService;
