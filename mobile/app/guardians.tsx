import { useCallback, useState } from 'react';
import { Linking, Pressable, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect } from 'expo-router';
import { apiRequest, loadCurrentUser } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page, ui } from '@/src/components/Page';
import { policyUrl } from '@/src/legal';
import { GuardianPermissions, type GuardianGrants } from '@/src/components/GuardianPermissions';

type Authorization = GuardianGrants & { child_username: string; status: string; consent_text: string; consent_version: string };

export default function GuardiansScreen() {
  const { signOut } = useAuth();
  const [items, setItems] = useState<Authorization[]>([]);
  const [needsAge, setNeedsAge] = useState(false);
  const [birthDate, setBirthDate] = useState('');
  const [guardianEmail, setGuardianEmail] = useState('');
  const [accepted, setAccepted] = useState<Record<number, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const load = useCallback(async () => {
    try {
      const [current, requests] = await Promise.all([loadCurrentUser(), apiRequest<Authorization[]>('auth/guardians/')]);
      setNeedsAge(current.account_capabilities?.age_group === 'UNKNOWN'); setItems(requests);
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to load guardian authorizations.'); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); }, [load]));
  async function act(item: Authorization, action: 'approve' | 'revoke') {
    if (busy) return;
    setBusy(true); setError('');
    try {
      await apiRequest(`auth/guardians/${item.id}/`, { method: 'POST', body: {
        action, accepted: accepted[item.id] === true, version: item.consent_version,
      } });
      setAccepted({}); await load();
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to update authorization.'); }
    finally { setBusy(false); }
  }
  async function saveAge() {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const result = await apiRequest<{ guardian_approval_required?: boolean }>('auth/age-details/', {
        method: 'POST', body: { date_of_birth: birthDate.trim(), guardian_email: guardianEmail.trim() },
      });
      if (result.guardian_approval_required) { await signOut(); return; }
      await load();
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save age details.'); }
    finally { setBusy(false); }
  }
  return <><Stack.Screen options={{ headerShown: true, title: 'Guardian authorizations' }} /><Page title="Guardian authorizations">
    <Text>Support must verify your identity, adulthood and relationship to the child before a request appears here. Google login or an email match alone does not establish guardianship.</Text>
    <Pressable onPress={() => void Linking.openURL(new URL('/support/', policyUrl('terms')).toString()).catch(() => setError('Unable to open support.'))}><Text>Contact support</Text></Pressable>
    {needsAge && <View style={ui.card}>
      <Text>Record your private date of birth before acting as a guardian. A recorded date can only be corrected through support. Children under 13 will be restricted pending verified guardian approval.</Text>
      <TextInput accessibilityLabel="Date of birth" placeholder="YYYY-MM-DD" value={birthDate} onChangeText={setBirthDate} editable={!busy} />
      <TextInput accessibilityLabel="Guardian email (required under 13)" placeholder="Guardian email (required under 13)" value={guardianEmail} onChangeText={setGuardianEmail} autoCapitalize="none" keyboardType="email-address" editable={!busy} />
      <Pressable disabled={busy} onPress={() => void saveAge()}><Text>Save age details</Text></Pressable>
    </View>}
    {items.map(item => <View key={item.id} style={ui.card}>
      <Text>{item.child_username}: {item.status}</Text>
      {item.status === 'APPROVED' && <GuardianPermissions item={item} onChanged={load} />}
      {item.status === 'PENDING' && <><Text>{item.consent_text}</Text>
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: accepted[item.id] === true }} disabled={busy}
          onPress={() => setAccepted(current => ({ ...current, [item.id]: !current[item.id] }))}>
          <Text>{accepted[item.id] ? '[x]' : '[ ]'} I explicitly approve ({item.consent_version}).</Text></Pressable>
        <Pressable disabled={busy || !accepted[item.id]} onPress={() => void act(item, 'approve')}><Text>Approve child account</Text></Pressable></>}
      {item.status !== 'REVOKED' && <Pressable disabled={busy} onPress={() => void act(item, 'revoke')}><Text>Withdraw authorization and restrict child account</Text></Pressable>}
    </View>)}
    {!items.length && <Text>No verified requests are linked to your account yet.</Text>}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </Page></>;
}
