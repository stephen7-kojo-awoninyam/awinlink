import { useState } from 'react';
import { Pressable, Text, TextInput } from 'react-native';
import { Stack, useLocalSearchParams } from 'expo-router';
import { useURL } from 'expo-linking';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page, ui } from '@/src/components/Page';

export default function TeamInvitation() {
  const params = useLocalSearchParams<{ organization?: string; invitation?: string }>();
  const currentUrl = useURL();
  const { user, signIn } = useAuth();
  const [organization, setOrganization] = useState(params.organization || '');
  const [invitation, setInvitation] = useState(params.invitation || '');
  const [token, setToken] = useState('');
  const [link, setLink] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [done, setDone] = useState(false);
  async function respond(action: 'accept' | 'decline') {
    if (busy) return;
    setBusy(true); setMessage('');
    try {
      const url = link.trim() || currentUrl || '';
      let org = organization, invite = invitation, code = token;
      if (url) {
        const parsed = new URL(url);
        org = parsed.searchParams.get('organization') || org;
        invite = parsed.searchParams.get('invitation') || parsed.pathname.match(/team-invitations\/(\d+)/)?.[1] || invite;
        code = new URLSearchParams(parsed.hash.slice(1)).get('token') || code;
      }
      if (![org, invite].every(value => /^\d+$/.test(value) && Number(value) > 0) || !code.trim()) throw new Error('Enter the organization ID, invitation ID, and invitation code, or paste the full app invitation link.');
      await apiRequest(`organizations/${org}/team/invitations/${invite}/${action}/`, { method: 'POST', body: { token: code.trim() } });
      setToken(''); setLink(''); setDone(true); setMessage(action === 'accept' ? 'You joined the organization.' : 'Invitation declined.');
    } catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to respond to invitation.'); }
    finally { setBusy(false); }
  }
  async function login() {
    setBusy(true); setMessage('');
    try { await signIn(username.trim(), password); setPassword(''); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to sign in.'); }
    finally { setBusy(false); }
  }
  const field = (label: string, value: string, update: (value: string) => void, secure = false) => <TextInput accessibilityLabel={label} placeholder={label} autoCapitalize="none" secureTextEntry={secure} value={value} onChangeText={update} editable={!busy} style={{ padding: 12, borderWidth: 1, borderColor: '#dde3ed', borderRadius: 8 }} />;
  return <><Stack.Screen options={{ headerShown: true, title: 'Team invitation' }} /><Page title="Team invitation">
    {!user ? <><Text>Sign in with the account this invitation was sent to.</Text>{field('Username', username, setUsername)}{field('Password', password, setPassword, true)}<Pressable disabled={busy || !username || !password} onPress={() => void login()} style={ui.primaryButton}><Text style={ui.primaryButtonText}>Sign in</Text></Pressable></> : !done && <>
      <Text>Responding as @{user.username}. Paste your full invitation link, or enter the invitation details.</Text>
      {field('Invitation link', link, setLink)}{field('Organization ID', organization, setOrganization)}{field('Invitation ID', invitation, setInvitation)}{field('Invitation code', token, setToken, true)}
      <Pressable disabled={busy} onPress={() => void respond('accept')} style={ui.primaryButton}><Text style={ui.primaryButtonText}>Accept invitation</Text></Pressable>
      <Pressable disabled={busy} onPress={() => void respond('decline')}><Text>Decline invitation</Text></Pressable>
    </>}
    {!!message && <Text accessibilityRole="alert">{message}</Text>}
  </Page></>;
}
