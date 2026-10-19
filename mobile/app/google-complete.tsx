import { Link } from 'expo-router';
import { Text, View } from 'react-native';

// Fallback for an OS opening the deep link outside the active authentication session.
export default function GoogleComplete() {
  return <View style={{ padding: 24 }}><Text>Return to the Awinlink sign-in screen to finish. If your sign-in session closed, start again.</Text>
    <Link href="/google-auth">Return to Google sign-in</Link></View>;
}
