import { useState } from 'react';
import { Pressable, Text, TextInput, View } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { Page, ui } from '@/src/components/Page';
import { colors } from '@/src/theme';

export default function PasswordReset() {
  const params = useLocalSearchParams<{ uid?: string; token?: string }>();
  const [confirm, setConfirm] = useState(!!params.uid && !!params.token);
  const [email, setEmail] = useState('');
  const [uid, setUid] = useState(params.uid || '');
  const [token, setToken] = useState(params.token || '');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  async function submit() {
    if (busy) return;
    setBusy(true); setMessage('');
    try {
      const result = await apiRequest<{ detail: string }>(confirm ? 'auth/password-reset/confirm/' : 'auth/password-reset/', {
        method: 'POST', authenticated: false,
        body: confirm ? { uid: uid.trim(), token: token.trim(), new_password1: password, new_password2: repeat } : { email: email.trim() },
      });
      setMessage(result.detail); setPassword(''); setRepeat('');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to reset password.'); }
    finally { setBusy(false); }
  }
  const field = (label: string, value: string, update: (value: string) => void, secure = false) => <TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={update} secureTextEntry={secure} autoCapitalize="none" editable={!busy} style={{ borderWidth: 1, borderColor: colors.border, padding: 14, borderRadius: 10 }} />;
  return <><Stack.Screen options={{ headerShown: true, title: 'Reset password' }} /><Page title="Reset password">
    <Text>{confirm ? 'Use the account code and reset token from your email.' : 'Enter your account email to receive reset instructions.'}</Text>
    {confirm ? <>{field('Account code', uid, setUid)}{field('Reset token', token, setToken, true)}{field('New password', password, setPassword, true)}{field('Confirm new password', repeat, setRepeat, true)}</> : field('Email address', email, setEmail)}
    <Pressable disabled={busy || (confirm ? !uid || !token || !password || password !== repeat : !email.trim())} onPress={() => void submit()} style={ui.primaryButton}><Text style={ui.primaryButtonText}>{busy ? 'Working...' : confirm ? 'Save new password' : 'Send reset instructions'}</Text></Pressable>
    {!!message && <Text accessibilityRole="alert">{message}</Text>}
    <Pressable disabled={busy} onPress={() => { setConfirm(!confirm); setMessage(''); }}><Text style={{ color: colors.primary }}>{confirm ? 'Request a new reset email' : 'Enter reset code'}</Text></Pressable>
  </Page></>;
}
