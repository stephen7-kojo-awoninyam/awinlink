import { useState } from 'react';
import { Linking, Platform, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { useAuth } from '@/src/auth/AuthProvider';
import { beginGoogle, type GoogleExchange } from '@/src/google';
import { policyUrl, TERMS_VERSION } from '@/src/legal';
import { ui } from '@/src/components/Page';

const FIELDS = [
  ['first_name', 'First name'], ['last_name', 'Last name'], ['username', 'Username'],
  ['country', 'Country code (GH, US, GB...)'], ['phone_number', 'Phone number'],
] as const;
const ORG_FIELDS = [['organization_name', 'Organization name'], ['organization_username', 'Organization username'],
  ['organization_email', 'Organization email'], ['website', 'Website (optional)']] as const;
const ROLES = [['ATHLETE', 'Talent'], ['ORGANIZATION', 'Organization'], ['SCOUT', 'Scout'], ['COACH', 'Coach']] as const;

export default function GoogleAuthScreen() {
  const { user, isLoading, signInGoogle } = useAuth();
  const params = useLocalSearchParams<{ link?: string }>();
  const linking = params.link === '1';
  const router = useRouter();
  const [secret, setSecret] = useState<GoogleExchange | null>(null);
  const [email, setEmail] = useState('');
  const [needsSignup, setNeedsSignup] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({ role: '' });
  const [accepted, setAccepted] = useState(false);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (isLoading) return null;
  if (linking && !user) return <Redirect href="/login" />;

  async function handleGoogle(signup = false) {
    if (busy) return;
    if (signup && (!accepted || !values.role)) {
      setError('Choose your account type and explicitly accept the Terms of Use.'); return;
    }
    setBusy(true); setError('');
    try {
      if (Platform.OS === 'web') {
        await Linking.openURL(new URL('/accounts/login/', policyUrl('terms')).toString());
        return;
      }
      const exchangeSecret = signup ? secret : await beginGoogle(linking, password);
      if (!exchangeSecret) throw new Error('Start Google sign-in again.');
      setSecret(exchangeSecret);
      setPassword('');
      const result = await signInGoogle(exchangeSecret, signup ? {
        ...Object.fromEntries(Object.entries(values).map(([key, value]) => [key, value.trim()])),
        country: (values.country || '').trim().toUpperCase(),
        terms_accepted: accepted, terms_version: TERMS_VERSION,
      } : undefined, linking);
      if ('access' in result) {
        setSecret(null);
        router.replace(signup && ['ATHLETE', 'ORGANIZATION'].includes(result.user.role) ? '/onboarding' : '/(tabs)');
      } else if (result.signup_required) {
        setEmail(result.email || ''); setNeedsSignup(true);
      } else {
        setError('Google sign-in is not complete. Start again.');
      }
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to sign in with Google.'); }
    finally { setBusy(false); }
  }

  async function openPolicy(path: 'terms' | 'privacy' | 'community-guidelines') {
    try { await Linking.openURL(policyUrl(path)); }
    catch { setError('Unable to open the policy. Please try again before accepting.'); }
  }

  return <><Stack.Screen options={{ headerShown: true, title: linking ? 'Link Google' : 'Continue with Google' }} />
    <ScrollView contentContainerStyle={{ padding: 24, gap: 16 }} keyboardShouldPersistTaps="handled">
      {linking && !needsSignup && <><Text>Confirm your current Awinlink password, then choose Google. This links to your signed-in account.</Text>
        <TextInput accessibilityLabel="Current Awinlink password" secureTextEntry value={password} onChangeText={setPassword} style={{ borderWidth: 1, borderColor: '#ccd3df', borderRadius: 8, padding: 12 }} /></>}
      {!needsSignup && <Pressable accessibilityRole="button" disabled={busy} onPress={() => void handleGoogle()} style={ui.primaryButton}>
        <Text style={ui.primaryButtonText}>{busy ? 'Connecting...' : linking ? 'Link Google' : 'Continue with Google'}</Text></Pressable>}
      {needsSignup && <>
        <Text>Google verified: {email}. Choose your Awinlink account type.</Text>
        {ROLES.map(([value, label]) => <Pressable key={value} accessibilityRole="radio" accessibilityState={{ checked: values.role === value }}
          disabled={busy} onPress={() => setValues(current => ({ ...current, role: value }))}><Text>{values.role === value ? '(x)' : '( )'} {label}</Text></Pressable>)}
        {[...FIELDS, ...(values.role === 'ORGANIZATION' ? ORG_FIELDS : [])].map(([key, label]) => <View key={key}>
          <Text>{label}</Text><TextInput accessibilityLabel={label} value={values[key] || ''} style={{ borderWidth: 1, borderColor: '#ccd3df', borderRadius: 8, padding: 12 }}
            autoCapitalize={key === 'country' ? 'characters' : key === 'first_name' || key === 'last_name' ? 'words' : 'none'}
            onChangeText={value => setValues(current => ({ ...current, [key]: value }))} /></View>)}
        <Pressable accessibilityRole="checkbox" accessibilityLabel="I accept the Terms of Use" accessibilityState={{ checked: accepted }}
          disabled={busy} onPress={() => setAccepted(value => !value)}><Text>{accepted ? '[x]' : '[ ]'} I accept the Terms of Use</Text></Pressable>
        {(['terms', 'privacy', 'community-guidelines'] as const).map(path => <Pressable key={path} accessibilityRole="link" onPress={() => void openPolicy(path)}>
          <Text>{path === 'terms' ? 'Terms of Use' : path === 'privacy' ? 'Privacy Policy' : 'Community Guidelines'}</Text></Pressable>)}
        <Pressable accessibilityRole="button" disabled={busy} style={ui.primaryButton} onPress={() => void handleGoogle(true)}><Text style={ui.primaryButtonText}>{busy ? 'Creating...' : 'Create account'}</Text></Pressable>
        <Pressable accessibilityRole="button" disabled={busy} onPress={() => { setSecret(null); setNeedsSignup(false); setAccepted(false); }}><Text>Start Google sign-in again</Text></Pressable>
      </>}
      {!!error && <Text accessibilityRole="alert">{error}</Text>}
    </ScrollView></>;
}
