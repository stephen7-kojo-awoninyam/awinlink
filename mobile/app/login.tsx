import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Redirect, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/src/auth/AuthProvider';
import { colors } from '@/src/theme';

export default function LoginScreen() {
  const { user, signIn, isLoading, sessionError } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (isLoading) return null;
  if (user) return <Redirect href="/(tabs)" />;

  async function handleSignIn() {
    setSubmitting(true);
    setError('');
    try {
      await signIn(username.trim().replace(/^@/, ''), password);
    } catch (signInError) {
      setError(
        signInError instanceof Error
          ? signInError.message
          : 'Unable to sign in. Please try again.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View style={styles.brandMark}>
          <Text style={styles.brandInitial}>A</Text>
        </View>
        <Text style={styles.brand}>AWINLINK</Text>
        <Text style={styles.heading}>Your next connection starts here.</Text>
        <Text style={styles.description}>
          Sign in to your talent ecosystem and pick up where you left off.
        </Text>
        {!!sessionError && (
          <Text accessibilityRole="alert" style={styles.error}>
            {sessionError}
          </Text>
        )}

        <View style={styles.form}>
          <Text style={styles.label}>Username</Text>
          <TextInput
            autoCapitalize="none"
            autoComplete="username"
            autoCorrect={false}
            onChangeText={setUsername}
            onSubmitEditing={handleSignIn}
            placeholder="@yourusername"
            placeholderTextColor={colors.muted}
            returnKeyType="next"
            style={styles.input}
            value={username}
          />
          <Text style={styles.label}>Password</Text>
          <TextInput
            autoComplete="password"
            onChangeText={setPassword}
            onSubmitEditing={handleSignIn}
            placeholder="Your password"
            placeholderTextColor={colors.muted}
            returnKeyType="go"
            secureTextEntry
            style={styles.input}
            value={password}
          />

          {!!error && (
            <Text accessibilityRole="alert" style={styles.error}>
              {error}
            </Text>
          )}

          <Pressable accessibilityRole="button" onPress={() => router.push('/google-auth')}><Text>Continue with Google</Text></Pressable>
          <Pressable
            accessibilityRole="button"
            disabled={submitting || !username || !password}
            onPress={handleSignIn}
            style={({ pressed }) => [
              styles.button,
              (pressed || submitting) && styles.buttonPressed,
              (!username || !password) && styles.buttonDisabled,
            ]}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.buttonText}>Sign in</Text>
            )}
          </Pressable>
          <Pressable
            accessibilityRole="button"
            onPress={() => router.push('/register')}
            style={styles.registerLink}
          >
            <Text style={styles.footnote}>New to Awinlink? Create an account</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/password-reset')}><Text style={styles.footnote}>Forgot password?</Text></Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: { flex: 1, backgroundColor: colors.background },
  container: {
    flex: 1,
    justifyContent: 'center',
    paddingHorizontal: 28,
    paddingVertical: 32,
  },
  brandMark: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: colors.primary,
    borderRadius: 18,
    height: 58,
    justifyContent: 'center',
    marginBottom: 12,
    width: 58,
  },
  brandInitial: { color: '#fff', fontSize: 30, fontWeight: '800' },
  brand: { color: colors.primary, fontSize: 14, fontWeight: '800', letterSpacing: 3, textAlign: 'center' },
  heading: { color: colors.ink, fontSize: 28, fontWeight: '800', lineHeight: 35, marginTop: 28, textAlign: 'center' },
  description: { color: colors.muted, fontSize: 15, lineHeight: 23, marginTop: 9, textAlign: 'center' },
  form: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 22,
    borderWidth: 1,
    marginTop: 28,
    padding: 20,
    shadowColor: '#172033',
    shadowOffset: { width: 0, height: 9 },
    shadowOpacity: 0.07,
    shadowRadius: 22,
  },
  label: { color: colors.ink, fontSize: 13, fontWeight: '700', marginBottom: 8, marginTop: 10 },
  input: {
    backgroundColor: '#fbfcfe',
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 15,
    minHeight: 50,
    paddingHorizontal: 14,
  },
  error: { color: colors.danger, fontSize: 13, lineHeight: 19, marginTop: 12 },
  button: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 12,
    justifyContent: 'center',
    marginTop: 22,
    minHeight: 52,
  },
  buttonPressed: { opacity: 0.85 },
  buttonDisabled: { opacity: 0.5 },
  buttonText: { color: '#fff', fontSize: 15, fontWeight: '800' },
  footnote: { color: colors.primary, fontSize: 12, fontWeight: '700', lineHeight: 18, marginTop: 16, textAlign: 'center' },
  registerLink: { alignSelf: 'center' },
});
