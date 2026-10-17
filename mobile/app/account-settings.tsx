import { useCallback, useState } from 'react';
import { Alert, Linking, Pressable, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect, router } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page, ui } from '@/src/components/Page';
import { openNativeCallSettings } from '@/src/calls/nativeCallUI';

type Block = { blocked_user_id: number; blocked_user__username: string };
export default function AccountSettings() {
  const { signOut } = useAuth();
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
  async function removeAccount() {
    if (busy) return;
    setBusy(true); setError('');
    try { await apiRequest('auth/account/', { method: 'DELETE', body: { password } }); await signOut(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to delete account.'); }
    finally { setPassword(''); setBusy(false); }
  }
  const links = [
    ['Privacy policy', process.env.EXPO_PUBLIC_PRIVACY_URL],
    ['Terms of use', process.env.EXPO_PUBLIC_TERMS_URL],
    ['Support', process.env.EXPO_PUBLIC_SUPPORT_URL],
    ['Delete account in browser', process.env.EXPO_PUBLIC_DELETE_ACCOUNT_URL],
  ];
  return <><Stack.Screen options={{ headerShown: true, title: 'Account and safety' }} /><Page title="Account and safety">
    <Pressable accessibilityRole="button" onPress={() => { void Linking.openSettings().catch(() => setError('Unable to open device settings.')); }}><Text>Notification and device permissions</Text></Pressable>
    <Pressable accessibilityRole="button" onPress={() => openNativeCallSettings()}><Text>Native calling account settings (Android)</Text></Pressable>
    {links.filter(([, url]) => url).map(([label, url]) => <Pressable key={label} accessibilityRole="link" onPress={() => { void Linking.openURL(url!).catch(() => setError('Unable to open link.')); }}><Text>{label}</Text></Pressable>)}
    <Pressable onPress={() => router.push('/password-reset')}><Text>Reset password</Text></Pressable>
    <Text style={{ fontWeight: '700' }}>Blocked accounts</Text>
    {!blocks.length && <Text>No blocked accounts.</Text>}
    {blocks.map(block => <View key={block.blocked_user_id} style={ui.card}><Text>@{block.blocked_user__username}</Text><Pressable disabled={busy} onPress={() => void unblock(block.blocked_user_id)}><Text>Unblock account</Text></Pressable></View>)}
    <View style={[ui.card, { gap: 12 }]}><Text style={{ fontWeight: '700' }}>Delete account permanently</Text>
      <Text>This deletes your account and associated profile/content. Organization owners must transfer ownership first. This cannot be undone.</Text>
      <TextInput accessibilityLabel="Current password" placeholder="Current password" secureTextEntry value={password} onChangeText={setPassword} editable={!busy} />
      <Pressable disabled={busy || !password} onPress={() => Alert.alert('Permanently delete your account?', 'Your account and associated content will be deleted.', [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete account', style: 'destructive', onPress: () => void removeAccount() }])}><Text style={{ color: '#b42318' }}>{busy ? 'Working...' : 'Delete account'}</Text></Pressable>
    </View>
    {!!error && <Text accessibilityRole="alert" style={{ color: '#b42318' }}>{error}</Text>}
  </Page></>;
}
