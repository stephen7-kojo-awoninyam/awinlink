import { Platform } from 'react-native';
if (Platform.OS !== 'web') {
  require('./src/calls/nativeCallUI').initializeNativeCallEvents();
}
require('expo-router/entry');
