import { useEffect, useRef, useState } from 'react';
import { Pressable, Text, TextInput } from 'react-native';
import { Stack, useLocalSearchParams, useRouter } from 'expo-router';
import { apiRequest, clearTokens } from '@/src/api/client';
import { Page, ui } from '@/src/components/Page';
import { colors } from '@/src/theme';

function single(value: string | string[] | undefined) {
  return typeof value === 'string' ? value : '';
}

export default function PasswordReset() {
  const params = useLocalSearchParams<{ uid?: string | string[]; token?: string | string[] }>();
  const router = useRouter();
  const linkUid = single(params.uid), linkToken = single(params.token);
  const [confirm, setConfirm] = useState(!!linkUid && !!linkToken);
  const [manual, setManual] = useState(!(linkUid && linkToken));
  const [sent, setSent] = useState(false), [complete, setComplete] = useState(false);
  const [email, setEmail] = useState('');
  const [uid, setUid] = useState(linkUid), [token, setToken] = useState(linkToken);
  const [password, setPassword] = useState(''), [repeat, setRepeat] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('');
  const inFlight = useRef(false);

  // A new email link may arrive while this screen is already mounted.
  useEffect(() => {
    if (linkUid && linkToken) {
      setUid(linkUid); setToken(linkToken); setConfirm(true); setManual(false);
      setSent(false); setComplete(false); setMessage(''); setPassword(''); setRepeat('');
      router.setParams({ uid: undefined, token: undefined });
    }
  }, [linkUid, linkToken]);

  async function submit() {
    if (inFlight.current) return;
    if (confirm && password !== repeat) { setMessage('Passwords do not match.'); return; }
    inFlight.current = true; setBusy(true); setMessage('');
    try {
      const result = await apiRequest<{ detail: string }>(confirm ? 'auth/password-reset/confirm/' : 'auth/password-reset/', {
        method: 'POST', authenticated: false,
        body: confirm ? { uid: uid.trim(), token: token.trim(), new_password1: password, new_password2: repeat } : { email: email.trim() },
      });
      setMessage(result.detail);
      if (confirm) {
        setPassword(''); setRepeat(''); setUid(''); setToken(''); setComplete(true);
        await clearTokens();
      } else { setSent(true); }
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to reset password. Please try again.'); }
    finally { inFlight.current = false; setBusy(false); }
  }

  const field = (label: string, value: string, update: (value: string) => void, secure = false) => (
    <TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={update}
      secureTextEntry={secure} autoCapitalize="none" autoCorrect={false} editable={!busy}
      maxLength={label === 'Account code' ? 64 : label === 'Reset token' ? 128 : secure ? 4096 : 254}
      keyboardType={label === 'Email address' ? 'email-address' : 'default'}
      autoComplete={label === 'Email address' ? 'email' : label.includes('password') ? 'new-password' : 'off'}
      textContentType={label.includes('password') ? 'newPassword' : label === 'Email address' ? 'emailAddress' : 'none'}
      style={{ borderWidth: 1, borderColor: colors.border, padding: 14, borderRadius: 10, color: colors.ink }} />
  );
  return <><Stack.Screen options={{ headerShown: true, title: 'Reset password' }} /><Page title="Reset password">
    {complete ? <>
      <Text>Your password has been updated. Sign in with your new password.</Text>
      <Pressable accessibilityRole="button" onPress={() => router.replace('/login')} style={ui.primaryButton}><Text style={ui.primaryButtonText}>Back to sign in</Text></Pressable>
    </> : <>
      <Text>{confirm ? 'Choose a strong password you do not use elsewhere. Use the expiry time in your reset email.' : sent ? 'If an active account matches, reset instructions have been sent. Check your inbox and spam folder.' : 'Enter the email address you registered with Awinlink.'}</Text>
      {confirm ? <>{manual && <>{field('Account code', uid, setUid)}{field('Reset token', token, setToken, true)}</>}{field('New password', password, setPassword, true)}{field('Confirm new password', repeat, setRepeat, true)}<Text>Use at least 8 characters. Avoid common, numeric-only, or personally identifying passwords.</Text></> : !sent && field('Email address', email, setEmail)}
      {(!sent || confirm) && <Pressable accessibilityRole="button" disabled={busy || (confirm ? !uid.trim() || !token.trim() || !password || !repeat : !email.trim())} onPress={() => void submit()} style={ui.primaryButton}><Text style={ui.primaryButtonText}>{busy ? 'Working...' : confirm ? 'Save new password' : 'Send reset instructions'}</Text></Pressable>}
      {!!message && <Text accessibilityRole="alert">{message}</Text>}
      <Pressable accessibilityRole="button" disabled={busy} onPress={() => { setConfirm(!confirm); setManual(true); setSent(false); setUid(''); setToken(''); setPassword(''); setRepeat(''); setMessage(''); }}><Text style={{ color: colors.primary }}>{confirm ? 'Request a new reset email' : 'Enter reset code'}</Text></Pressable>
      <Pressable accessibilityRole="button" disabled={busy} onPress={() => router.replace('/login')}><Text style={{ color: colors.primary }}>Back to sign in</Text></Pressable>
    </>}
  </Page></>;
}
