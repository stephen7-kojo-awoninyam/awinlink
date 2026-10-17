import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, Share, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page, ui } from '@/src/components/Page';
import { colors } from '@/src/theme';

type Member = { id: number; user: number; username: string; role: string; status: string };
type Invitation = { id: number; recipient_username: string; role: string; status: string };
const roles = ['MANAGER', 'RECRUITER', 'VIEWER'];

export default function OrganizationTeam() {
  const { user } = useAuth();
  const [organization, setOrganization] = useState<number | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [username, setUsername] = useState('');
  const [role, setRole] = useState('VIEWER');
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [pendingShare, setPendingShare] = useState('');
  const load = useCallback(async () => {
    setError('');
    try {
      const own = await apiRequest<{ id: number }>('organizations/me/');
      setOrganization(own.id);
      const [roster, invites] = await Promise.all([
        apiRequest<Member[]>(`organizations/${own.id}/team/members/`),
        apiRequest<Invitation[]>(`organizations/${own.id}/team/invitations/`),
      ]);
      setMembers(roster); setInvitations(invites);
    } catch (e) { setMembers([]); setInvitations([]); setError(e instanceof Error ? e.message : 'Unable to load your team.'); }
    finally { setLoading(false); }
  }, []);
  useFocusEffect(useCallback(() => { void load(); return () => setPendingShare(''); }, [load]));
  async function mutate(path: string, body?: unknown, method = 'POST') {
    if (working || !organization) return;
    setWorking(true); setError('');
    try { await apiRequest(`organizations/${organization}/team/${path}`, { method, body }); await load(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to update the team.'); }
    finally { setWorking(false); }
  }
  async function invite() {
    if (working || !organization || !username.trim()) return;
    setWorking(true); setError('');
    try {
      const result = await apiRequest<{ response_url: string; token: string; invitation: { id: number } }>(`organizations/${organization}/team/invitations/`, {
        method: 'POST', body: { recipient_username: username.trim(), role },
      });
      const origin = process.env.EXPO_PUBLIC_WEB_URL || process.env.EXPO_PUBLIC_API_URL;
      if (!origin) throw new Error('Configure the web origin to share invitation links.');
      const url = new URL(result.response_url, origin);
      url.hash = new URLSearchParams({ token: result.token }).toString();
      const nativeUrl = `awinlink://team-invitation?organization=${organization}&invitation=${result.invitation.id}#${url.hash.slice(1)}`;
      const invitationMessage = `Join my Awinlink organization in the app: ${nativeUrl}\nOr in your browser: ${url.href}`;
      setPendingShare(invitationMessage); setUsername(''); await load();
      await Share.share({ message: invitationMessage });
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to invite this account.'); }
    finally { setWorking(false); }
  }
  const button = (label: string, action: () => void) => <Pressable accessibilityRole="button" disabled={working} onPress={action} style={[ui.primaryButton, working && { opacity: .5 }]}><Text style={ui.primaryButtonText}>{label}</Text></Pressable>;
  return <>
    <Stack.Screen options={{ headerShown: true, title: 'Organization team' }} />
    <Page title="Organization team" eyebrow="OWNER WORKSPACE">
      {loading ? <ActivityIndicator /> : <>
        {!!error && <Text accessibilityRole="alert" style={{ color: colors.danger }}>{error}</Text>}
        {button('Refresh team', () => void load())}
        {members.map(member => <View key={member.id} style={[ui.card, { gap: 10 }]}>
          <Text style={{ fontWeight: '700' }}>@{member.username} · {member.role} · {member.status}</Text>
          {member.user !== user?.id && member.role !== 'OWNER' && <>
            {roles.map(value => <View key={value}>{button(`Set ${value.toLowerCase()}`, () => void mutate(`members/${member.id}/role/`, { role: value }, 'PATCH'))}</View>)}
            {button(member.status === 'ACTIVE' ? 'Suspend' : 'Restore', () => void mutate(`members/${member.id}/${member.status === 'ACTIVE' ? 'suspend' : 'restore'}/`))}
            {member.status !== 'REMOVED' && button('Remove member', () => Alert.alert('Remove team member?', `Remove @${member.username} from this organization?`, [{ text: 'Cancel', style: 'cancel' }, { text: 'Remove', style: 'destructive', onPress: () => void mutate(`members/${member.id}/remove/`) }]))}
            {member.status === 'ACTIVE' && button('Transfer ownership', () => Alert.alert('Transfer organization ownership?', `@${member.username} will become the owner. You will become a manager and lose owner controls.`, [{ text: 'Cancel', style: 'cancel' }, { text: 'Transfer ownership', style: 'destructive', onPress: () => void mutate('ownership-transfer/', { membership_id: member.id }) }]))}
          </>}
        </View>)}
        {!!members.length && <View style={[ui.card, { gap: 10 }]}>
          <Text>Invite an existing Awinlink account</Text>
          <TextInput accessibilityLabel="Recipient username" autoCapitalize="none" placeholder="Username" value={username} onChangeText={setUsername} style={{ borderWidth: 1, borderColor: colors.border, borderRadius: 8, padding: 12 }} />
          {roles.map(value => <View key={value}>{button(`${role === value ? 'Selected: ' : ''}${value.toLowerCase()}`, () => setRole(value))}</View>)}
          {button('Create and share invitation', () => void invite())}
          {!!pendingShare && button('Share invitation again', () => { void Share.share({ message: pendingShare }).catch(e => setError(String(e))); })}
        </View>}
        {invitations.map(invitation => <View key={invitation.id} style={[ui.card, { gap: 10 }]}>
          <Text>@{invitation.recipient_username} · {invitation.role} · {invitation.status}</Text>
          {invitation.status === 'PENDING' && button('Revoke invitation', () => void mutate(`invitations/${invitation.id}/revoke/`))}
        </View>)}
      </>}
    </Page>
  </>;
}
