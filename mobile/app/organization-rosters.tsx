import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Button, Text, TextInput, View } from 'react-native';
import { Link, Stack, useFocusEffect } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { Page, ui } from '@/src/components/Page';
import { rosterPages, updateTag, TalentTag, Workspace, RosterEvent } from '@/src/organizations/rosters';

export function TagCard({ entry, working, act }: { entry: TalentTag; working: boolean; act: (id: number, action: string, username: string, reason: string) => Promise<void> }) {
  const [username, setUsername] = useState('');
  const [reason, setReason] = useState('');
  const [confirmRemoval, setConfirmRemoval] = useState(false);
  const [history, setHistory] = useState<RosterEvent[]>([]);
  const [error, setError] = useState('');
  const [loadingHistory, setLoadingHistory] = useState(false);
  async function loadHistory() {
    setLoadingHistory(true); setError('');
    try { setHistory(await rosterPages<RosterEvent>(`organizations/talent-tags/${entry.id}/`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load history.'); }
    finally { setLoadingHistory(false); }
  }
  return <View style={[ui.card, { gap: 10 }]}>
    <Text style={{ fontWeight: '700' }}>{entry.name} · {entry.organization_name}</Text>
    <Link href={{ pathname: '/organization-agreements', params: { entry: entry.id } }}>View roster agreements</Link>
    <Text>{entry.tag} · {entry.roster || 'General roster'} · {entry.status}</Text>
    {!!entry.talent_details && <Text>{entry.talent_details}</Text>}
    {!!entry.talent_id && <Link href={{ pathname: '/talent/[id]', params: { id: entry.talent_id } }}>View talent profile</Link>}
    {entry.actions?.includes('LINK') && <TextInput accessibilityLabel="Link username" placeholder="Awinlink username" autoCapitalize="none" value={username} onChangeText={setUsername} maxLength={150} style={{ minHeight: 44, padding: 12, borderWidth: 1, borderColor: '#889', borderRadius: 8 }} />}
    {!!entry.actions?.length && <TextInput accessibilityLabel="Action reason" placeholder="Reason (optional)" value={reason} onChangeText={setReason} maxLength={500} style={{ minHeight: 44, padding: 12, borderWidth: 1, borderColor: '#889', borderRadius: 8 }} />}
    {entry.actions?.filter(action => action !== 'REMOVE').map(action => <Button key={action} title={{ LINK: 'Request profile confirmation', CONFIRM: 'Confirm affiliation', DECLINE: 'Decline affiliation' }[action] || action} disabled={working || (action === 'LINK' && !username.trim())} onPress={() => void act(entry.id, action, username.trim(), reason.trim())} />)}
    {entry.actions?.includes('REMOVE') && <Button title="Remove tag" disabled={working} onPress={() => setConfirmRemoval(true)} />}
    {confirmRemoval && <View><Text>Remove this tag? Its history will be retained.</Text><Button title="Confirm removal" disabled={working} onPress={() => { setConfirmRemoval(false); void act(entry.id, 'REMOVE', '', reason.trim()); }} /><Button title="Keep tag" onPress={() => setConfirmRemoval(false)} /></View>}
    <Button title="View history" disabled={loadingHistory || working} onPress={() => void loadHistory()} />
    {history.map(event => <Text key={event.id}>{event.action} · {new Date(event.created_at).toLocaleString()}{event.reason ? ` · ${event.reason}` : ''}</Text>)}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}

export default function OrganizationRosters() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [selected, setSelected] = useState<Workspace | null>(null);
  const [mine, setMine] = useState<TalentTag[]>([]);
  const [entries, setEntries] = useState<TalentTag[]>([]);
  const [name, setName] = useState(''); const [details, setDetails] = useState('');
  const [tag, setTag] = useState(''); const [roster, setRoster] = useState(''); const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(true); const [working, setWorking] = useState(false); const [error, setError] = useState('');
  const generation = useRef(0); const busy = useRef(false);
  const load = useCallback(async () => {
    const current = ++generation.current; setError(''); setLoading(true);
    try {
      const [spaceResult, ownResult] = await Promise.allSettled([rosterPages<Workspace>('organizations/roster-workspaces/'), rosterPages<TalentTag>('organizations/talent-tags/mine/')]);
      if (current !== generation.current) return;
      const spaces = spaceResult.status === 'fulfilled' ? spaceResult.value : [];
      const own = ownResult.status === 'fulfilled' ? ownResult.value : [];
      const failure = [spaceResult, ownResult].find(result => result.status === 'rejected');
      if (failure?.status === 'rejected') setError(failure.reason instanceof Error ? failure.reason.message : 'Unable to load part of this workspace.');
      setWorkspaces(spaces); setMine(own);
      if (selected && spaces.some(space => space.id === selected.id)) {
        try {
          const rows = await rosterPages<TalentTag>(`organizations/${selected.id}/roster/`);
          if (current === generation.current) setEntries(rows);
        } catch (e) {
          if (current === generation.current) { setEntries([]); setWorkspaces(spaces.map(space => space.id === selected.id ? { ...space, can_manage: false } : space)); setError(e instanceof Error ? e.message : 'Unable to load this organization roster.'); }
        }
      } else {
        setEntries([]);
        if (selected) { setSelected(null); setName(''); setDetails(''); setTag(''); setRoster(''); setUsername(''); }
      }
    } catch (e) { if (current === generation.current) { setWorkspaces([]); setEntries([]); setMine([]); setError(e instanceof Error ? e.message : 'Unable to load rosters.'); } }
    finally { if (current === generation.current) setLoading(false); }
  }, [selected?.id]);
  useFocusEffect(useCallback(() => { void load(); return () => { generation.current += 1; }; }, [load]));
  async function mutate(operation: () => Promise<unknown>) {
    if (busy.current) return; busy.current = true; setWorking(true); setError('');
    try { await operation(); await load(); }
    catch (e) { await load(); setError(e instanceof Error ? e.message : 'Unable to update roster.'); }
    finally { busy.current = false; setWorking(false); }
  }
  const act = async (id: number, action: string, linkedUsername: string, reason: string) => mutate(() => updateTag(id, action, linkedUsername, reason));
  const input = (label: string, value: string, setter: (value: string) => void, maxLength: number) => <TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={setter} maxLength={maxLength} style={{ borderWidth: 1, borderColor: '#889', borderRadius: 8, padding: 12 }} />;
  return <><Stack.Screen options={{ headerShown: true, title: 'Talent tags and rosters' }} /><Page title="Talent tags and rosters" eyebrow="ORGANIZATION AFFILIATIONS">
    <Text>Confirm organization tags for your profile, or manage a team roster. Unclaimed entries stay private until linked and confirmed.</Text>
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    <Button title="Refresh rosters" disabled={working || loading} onPress={() => void load()} />
    {loading ? <ActivityIndicator /> : <>
      <Text style={{ fontWeight: '700' }}>Your organization tags</Text>
      {!mine.length && <Text>No organization tags yet.</Text>}
      {mine.map(entry => <TagCard key={entry.id} entry={entry} working={working} act={act} />)}
      <Text style={{ fontWeight: '700' }}>Organization workspace</Text>
      {workspaces.map(space => <Button key={space.id} title={`${selected?.id === space.id ? 'Selected: ' : ''}${space.name}`} disabled={working} onPress={() => { if (selected?.id !== space.id) { setName(''); setDetails(''); setTag(''); setRoster(''); setUsername(''); } setEntries([]); setSelected(space); }} />)}
      {selected && <>
        <Text>{selected.name}</Text>
        {workspaces.find(space => space.id === selected.id)?.can_manage && <View style={[ui.card, { gap: 10 }]}>
          <Text>Add talent; leave username empty for an unclaimed entry.</Text>
          {input('Talent name', name, setName, 200)}{input('Talent details', details, setDetails, 300)}
          {input('Tag', tag, setTag, 80)}{input('Roster', roster, setRoster, 100)}{input('Awinlink username (optional)', username, setUsername, 150)}
          <Button title="Add talent" disabled={working || !name.trim() || !tag.trim()} onPress={() => void mutate(async () => { await apiRequest(`organizations/${selected.id}/roster/`, { method: 'POST', body: { name: name.trim(), talent_details: details.trim(), tag: tag.trim(), roster: roster.trim(), username: username.trim() } }); setName(''); setDetails(''); setTag(''); setRoster(''); setUsername(''); })} />
        </View>}
        {!entries.length && <Text>No roster entries yet.</Text>}
        {entries.map(entry => <TagCard key={entry.id} entry={entry} working={working} act={act} />)}
      </>}
    </>}
  </Page></>;
}
