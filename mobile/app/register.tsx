import { useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Redirect, Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/src/auth/AuthProvider';
import { policyUrl, TERMS_VERSION } from '@/src/legal';
import { colors } from '@/src/theme';
import type { RegistrationData } from '@/src/types';

type Role = RegistrationData['role'];

const ROLES: { value: Role; label: string }[] = [
  { value: 'ATHLETE', label: 'Talent' },
  { value: 'ORGANIZATION', label: 'Organization' },
  { value: 'SCOUT', label: 'Scout' },
  { value: 'COACH', label: 'Coach' },
];

export default function RegisterScreen() {
  const { user, signUp, isLoading } = useAuth();
  const router = useRouter();
  const [values, setValues] = useState({
    first_name: '',
    last_name: '',
    username: '',
    email: '',
    phone_number: '',
    country: '',
    role: 'ATHLETE' as Role,
    organization_name: '',
    organization_username: '',
    organization_email: '',
    website: '',
    password1: '',
    password2: '',
  });
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (isLoading) return null;
  if (user) return <Redirect href="/(tabs)" />;

  function setField(field: keyof typeof values, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  async function openPolicy(path: 'terms' | 'privacy' | 'community-guidelines') {
    try { await Linking.openURL(policyUrl(path)); }
    catch { setError('Unable to open policy. Please try again before accepting the Terms.'); }
  }

  async function submit() {
    if (!termsAccepted) {
      setError('You must explicitly accept the Terms of Use to register.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      const data: RegistrationData = {
        terms_accepted: termsAccepted,
        terms_version: TERMS_VERSION,
        first_name: values.first_name.trim(),
        last_name: values.last_name.trim(),
        username: values.username.trim().replace(/^@/, ''),
        email: values.email.trim(),
        phone_number: values.phone_number.trim(),
        country: values.country.trim().toUpperCase(),
        role: values.role,
        password1: values.password1,
        password2: values.password2,
      };
      if (values.role === 'ORGANIZATION') {
        data.organization_name = values.organization_name.trim();
        data.organization_username = values.organization_username.trim().replace(/^@/, '');
        data.organization_email = values.organization_email.trim();
        data.website = values.website.trim();
      }
      await signUp(data);
      router.replace(
        values.role === 'ATHLETE' || values.role === 'ORGANIZATION'
          ? '/onboarding'
          : '/(tabs)',
      );
    } catch (registerError) {
      setError(
        registerError instanceof Error
          ? registerError.message
          : 'Unable to create your account. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.flex}
        >
          <ScrollView
            contentContainerStyle={styles.content}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <Text style={styles.brand}>AWINLINK</Text>
            <Text style={styles.heading}>Create your account</Text>
            <Text style={styles.description}>
              Join your ecosystem and build your Awinlink profile.
            </Text>

            <Pressable accessibilityRole="button" onPress={() => router.push('/google-auth')}><Text>Continue with Google</Text></Pressable>
            <View style={styles.form}>
              <Text style={styles.label}>I am joining as</Text>
              <View style={styles.roles}>
                {ROLES.map((role) => (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityState={{ selected: values.role === role.value }}
                    key={role.value}
                    onPress={() => setField('role', role.value)}
                    style={[styles.roleChoice, values.role === role.value && styles.roleSelected]}
                  >
                    <Text style={[styles.roleText, values.role === role.value && styles.roleTextSelected]}>
                      {role.label}
                    </Text>
                  </Pressable>
                ))}
              </View>

              <View style={styles.nameRow}>
                <Field label="First name" value={values.first_name} onChangeText={(value) => setField('first_name', value)} placeholder="First name" />
                <Field label="Last name" value={values.last_name} onChangeText={(value) => setField('last_name', value)} placeholder="Last name" />
              </View>
              <Field label="Username" autoCapitalize="none" value={values.username} onChangeText={(value) => setField('username', value)} placeholder="Choose a username" />
              <Field label="Email address" autoCapitalize="none" keyboardType="email-address" value={values.email} onChangeText={(value) => setField('email', value)} placeholder="you@example.com" />
              <View style={styles.nameRow}>
                <Field label="Country code" autoCapitalize="characters" value={values.country} onChangeText={(value) => setField('country', value)} placeholder="GH, US, GB..." />
                <Field label="Phone number" keyboardType="phone-pad" value={values.phone_number} onChangeText={(value) => setField('phone_number', value)} placeholder="+233..." />
              </View>

              {values.role === 'ORGANIZATION' && (
                <>
                  <Field label="Organization name" value={values.organization_name} onChangeText={(value) => setField('organization_name', value)} placeholder="Organization name" />
                  <Field label="Organization username" autoCapitalize="none" value={values.organization_username} onChangeText={(value) => setField('organization_username', value)} placeholder="Organization handle" />
                  <Field label="Organization email" autoCapitalize="none" keyboardType="email-address" value={values.organization_email} onChangeText={(value) => setField('organization_email', value)} placeholder="contact@example.com" />
                  <Field label="Website (optional)" autoCapitalize="none" keyboardType="url" value={values.website} onChangeText={(value) => setField('website', value)} placeholder="https://example.com" />
                </>
              )}

              <Field label="Password" secureTextEntry value={values.password1} onChangeText={(value) => setField('password1', value)} placeholder="Create a password" />
              <Field label="Confirm password" secureTextEntry value={values.password2} onChangeText={(value) => setField('password2', value)} placeholder="Enter it again" />
              <Text style={styles.countryNote}>
                Use the two-letter ISO country code (for example GH or US); phone numbers are validated for that country.
              </Text>

              <Pressable accessibilityRole="checkbox" accessibilityLabel="I accept the Terms of Use"
                accessibilityState={{ checked: termsAccepted }} disabled={submitting}
                onPress={() => setTermsAccepted((current) => !current)}>
                <Text>{termsAccepted ? '[x]' : '[ ]'} I accept the Terms of Use</Text>
              </Pressable>
              {(['terms', 'privacy', 'community-guidelines'] as const).map((path) => (
                <Pressable key={path} accessibilityRole="link" onPress={() => void openPolicy(path)}>
                  <Text style={styles.countryNote}>{path === 'terms' ? 'Read Terms of Use' : path === 'privacy' ? 'Read Privacy Policy' : 'Read Community Guidelines'}</Text>
                </Pressable>
              ))}
              {!!error && (
                <Text accessibilityRole="alert" style={styles.error}>
                  {error}
                </Text>
              )}
              <Pressable
                accessibilityRole="button"
                disabled={submitting}
                onPress={() => void submit()}
                style={({ pressed }) => [
                  styles.submitButton,
                  (pressed || submitting) && styles.pressed,
                ]}
              >
                {submitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.submitText}>Create account</Text>
                )}
              </Pressable>
              <Pressable accessibilityRole="button" onPress={() => router.back()}>
                <Text style={styles.loginLink}>Already have an account? Sign in</Text>
              </Pressable>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </>
  );
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  autoCapitalize,
  keyboardType,
  secureTextEntry = false,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  autoCapitalize?: 'none' | 'sentences' | 'words' | 'characters';
  keyboardType?: 'default' | 'email-address' | 'phone-pad' | 'url';
  secureTextEntry?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        autoCapitalize={autoCapitalize || 'sentences'}
        autoCorrect={false}
        keyboardType={keyboardType || 'default'}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        secureTextEntry={secureTextEntry}
        style={styles.input}
        value={value}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  flex: { flex: 1 },
  content: { padding: 24, paddingBottom: 40 },
  brand: { color: colors.primary, fontSize: 13, fontWeight: '800', letterSpacing: 3, textAlign: 'center' },
  heading: { color: colors.ink, fontSize: 27, fontWeight: '800', marginTop: 24, textAlign: 'center' },
  description: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 8, textAlign: 'center' },
  form: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: 13, marginTop: 22, padding: 17 },
  label: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  roles: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  roleChoice: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 18, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 8 },
  roleSelected: { backgroundColor: colors.softBlue, borderColor: colors.primary },
  roleText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  roleTextSelected: { color: colors.primary },
  nameRow: { flexDirection: 'row', gap: 10 },
  field: { flex: 1, gap: 6 },
  input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, fontSize: 14, minHeight: 46, paddingHorizontal: 11 },
  countryNote: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 18 },
  submitButton: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, justifyContent: 'center', minHeight: 50 },
  submitText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  pressed: { opacity: 0.8 },
  loginLink: { color: colors.primary, fontSize: 12, fontWeight: '700', paddingVertical: 8, textAlign: 'center' },
});
