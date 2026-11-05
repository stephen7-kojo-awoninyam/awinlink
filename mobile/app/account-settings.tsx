import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Linking, Pressable, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect, router } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { policyUrl } from '@/src/legal';
import { Page, ui } from '@/src/components/Page';
import { openNativeCallSettings } from '@/src/calls/nativeCallUI';
import { beginGoogleDeletion } from '@/src/google';

type Block = { blocked_user_id: number; blocked_user__username: string };
export default function AccountSettings() {
  const { signOut, user } = useAuth();
  const currentUser = useRef({ id: user?.id });
  if (currentUser.current.id !== user?.id) currentUser.current = { id: user?.id };
  const renderedAccount = currentUser.current;
  const deleting = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try { setBlocks(await apiRequest<Block[]>('safety/blocks/')); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load blocked accounts.'); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  async function unblock(id: number) {
    setBusy(true); setError('');
    try { await apiRequest('safety/blocks/', { method: 'DELETE', body: { user_id: id } }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to unblock account.'); }
    finally { setBusy(false); }
  }
  async function removeAccount(google = false) {
    if (busy || deleting.current) return;
    const owner = currentUser.current;
    if (!owner.id || owner !== renderedAccount || !mounted.current) return;
    deleting.current = true;
    setBusy(true); setError('');
    try {
      const proof = google ? await beginGoogleDeletion() : undefined;
      if (!mounted.current || currentUser.current !== owner) return;
      await apiRequest('auth/account/', { method: 'DELETE', body: google ? { google_reauth: proof, confirm: true } : { password } });
      if (mounted.current && currentUser.current === owner) await signOut();
    }
    catch (e) { if (mounted.current && currentUser.current === owner) setError(e instanceof Error ? e.message : 'Unable to delete account.'); }
    finally { deleting.current = false; if (mounted.current) { setPassword(''); setBusy(false); } }
  }
  const links = [
    ['Privacy policy', process.env.EXPO_PUBLIC_PRIVACY_URL || (process.env.EXPO_PUBLIC_API_URL ? policyUrl('privacy') : undefined)],
    ['Terms of use', process.env.EXPO_PUBLIC_TERMS_URL || (process.env.EXPO_PUBLIC_API_URL ? policyUrl('terms') : undefined)],
    ['Community Guidelines', process.env.EXPO_PUBLIC_API_URL ? policyUrl('community-guidelines') : undefined],
    ['Support', process.env.EXPO_PUBLIC_SUPPORT_URL],
    ['Delete account in browser', process.env.EXPO_PUBLIC_DELETE_ACCOUNT_URL],
  ];
  return <><Stack.Screen options={{ headerShown: true, title: 'Account and safety' }} /><Page title="Account and safety">
    <Pressable accessibilityRole="button" onPress={() => router.push('/guardians')}><Text>Guardian authorizations and private age details</Text></Pressable>
    <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: '/google-auth', params: { link: '1' } })}><Text>Link Google to this account</Text></Pressable>
    <Pressable accessibilityRole="button" onPress={() => { void Linking.openSettings().catch(() => setError('Unable to open device settings.')); }}><Text>Notification and device permissions</Text></Pressable>
    <Pressable accessibilityRole="button" onPress={() => openNativeCallSettings()}><Text>Native calling account settings (Android)</Text></Pressable>
    {links.filter(([, url]) => url).map(([label, url]) => <Pressable key={label} accessibilityRole="link" onPress={() => { void Linking.openURL(url!).catch(() => setError('Unable to open link.')); }}><Text>{label}</Text></Pressable>)}
    <Pressable onPress={() => router.push('/password-reset')}><Text>Reset password</Text></Pressable>
    <Text style={{ fontWeight: '700' }}>Blocked accounts</Text>
    {!blocks.length && <Text>No blocked accounts.</Text>}
    {blocks.map(block => <View key={block.blocked_user_id} style={ui.card}><Text>@{block.blocked_user__username}</Text><Pressable disabled={busy} onPress={() => void unblock(block.blocked_user_id)}><Text>Unblock account</Text></Pressable></View>)}
    <View style={[ui.card, { gap: 12 }]}><Text style={{ fontWeight: '700' }}>Delete account permanently</Text>
      <Text>This removes your account and related database content. Some shared records, uploaded files, recipient copies and backups need separate handling; see Privacy policy and Support. Organization owners must transfer ownership first. This cannot be undone.</Text>
      <TextInput accessibilityLabel="Current password" placeholder="Current password" secureTextEntry value={password} onChangeText={setPassword} editable={!busy} />
      <Pressable disabled={busy || !password} onPress={() => Alert.alert('Permanently delete your account?', 'Your account will be deleted. Some shared records, files and backups may remain; see Privacy policy for details.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete account', style: 'destructive', onPress: () => void removeAccount() }])}><Text style={{ color: '#b42318' }}>{busy ? 'Working...' : 'Delete account'}</Text></Pressable>
      <Text>If Google is already linked, you can confirm deletion with Google instead of a password. A recent Google sign-in is required.</Text>
      <Pressable accessibilityRole="button" disabled={busy} onPress={() => Alert.alert('Delete account using Google?', 'Choose your linked Google account to confirm your identity, then your Awinlink account will be permanently deleted. Some shared records, files and backups need separate handling. Organization owners must transfer ownership first.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Confirm and delete with Google', style: 'destructive', onPress: () => void removeAccount(true) }])}><Text>Delete account with Google</Text></Pressable>
    </View>
    {!!error && <Text accessibilityRole="alert" style={{ color: '#b42318' }}>{error}</Text>}
  </Page></>;
}
