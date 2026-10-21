import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Button, Switch, Text, TextInput, View } from 'react-native';
import { Link, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { Page, ui } from '@/src/components/Page';
import { rosterPages } from '@/src/organizations/rosters';
import { Agreement, AgreementChoice, AgreementHistory, AgreementAction, agreementAction, actionLabels, consentActions, reasonActions } from '@/src/organizations/agreements';

const inputStyle = { minHeight: 44, padding: 12, borderWidth: 1, borderColor: '#889', borderRadius: 8 };
type Terms = { title: string; terms: string; starts_on: string; ends_on: string; amount: string; currency: string; destination_tag: string; destination_roster: string };
const blank = (): Terms => ({ title: '', terms: '', starts_on: '', ends_on: '', amount: '', currency: 'GHS', destination_tag: '', destination_roster: '' });
function payload(terms: Terms, transfer: boolean) {
  return { ...terms, starts_on: terms.starts_on || null, ends_on: terms.ends_on || null, amount: terms.amount === '' ? null : terms.amount,
    currency: terms.currency.trim().toUpperCase(), destination_tag: transfer ? terms.destination_tag : '', destination_roster: transfer ? terms.destination_roster : '' };
}
function TermsFields({ value, setValue, transfer, disabled }: { value: Terms; setValue: (next: Terms) => void; transfer: boolean; disabled: boolean }) {
  const fields: [keyof Terms, string, number][] = [['title', 'Title', 200], ['terms', 'Terms', 20000], ['starts_on', 'Start date (YYYY-MM-DD, optional)', 10],
    ['ends_on', 'End date (YYYY-MM-DD, optional)', 10], ['amount', 'Agreed value (optional; no collection)', 13], ['currency', 'Currency (3 letters)', 3],
    ...(transfer ? [['destination_tag', 'Destination tag', 80], ['destination_roster', 'Destination roster', 100]] as [keyof Terms, string, number][] : [])];
  return <>{fields.map(([key, label, limit]) => <View key={key} style={{ gap: 6 }}><Text>{label}</Text><TextInput accessibilityLabel={label}
    value={value[key]} onChangeText={text => setValue({ ...value, [key]: text })} editable={!disabled} maxLength={limit}
    multiline={key === 'terms'} keyboardType={key === 'amount' ? 'decimal-pad' : 'default'} autoCapitalize={key === 'currency' ? 'characters' : 'sentences'}
    style={[inputStyle, key === 'terms' && { minHeight: 140, textAlignVertical: 'top' }]} /></View>)}</>;
}

export function AgreementCard({ row, working, mutate }: { row: Agreement; working: boolean; mutate: (operation: () => Promise<unknown>) => Promise<void> }) {
  const [consent, setConsent] = useState(false), [reason, setReason] = useState('');
  const [editing, setEditing] = useState(false);
  const [terms, setTerms] = useState<Terms>({ title: row.title, terms: row.terms, starts_on: row.starts_on || '', ends_on: row.ends_on || '', amount: row.amount || '', currency: row.currency, destination_tag: row.destination_tag, destination_roster: row.destination_roster });
  const [history, setHistory] = useState<AgreementHistory[]>([]), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  async function loadHistory() {
    setLoading(true); setError('');
    try { setHistory(await rosterPages<AgreementHistory>(`organizations/agreements/${row.id}/history/`)); }
    catch (e) { setError(e instanceof Error ? e.message : 'Unable to load agreement history.'); }
    finally { setLoading(false); }
  }
  function act(action: AgreementAction) { void mutate(() => agreementAction(row, action, consent, reason.trim())); }
  return <View style={[ui.card, { gap: 12 }]}>
    <Text style={{ fontWeight: '700' }}>{row.title}</Text><Text>{row.kind} · {row.status} · Revision {row.revision}</Text>
    <Text>{row.talent_name} · {row.organization_name}{row.destination_name ? ` → ${row.destination_name}` : ''}</Text>
    <Text>Roster: {row.roster_snapshot.roster || 'General'} · {row.roster_snapshot.tag}</Text><Text selectable>{row.terms}</Text>
    {!!row.ending_reason && <Text>Ending requested: {row.ending_reason}</Text>}
    {row.amount !== null && <Text>Agreed value: {row.amount} {row.currency} · No collection</Text>}
    {(row.starts_on || row.ends_on) && <Text>{row.starts_on || 'No start date'} — {row.ends_on || 'No end date'}</Text>}
    {row.kind === 'TRANSFER' && <Text>Destination: {row.destination_tag} · {row.destination_roster || 'General roster'}</Text>}
    {row.consents.filter(c => c.revision === row.revision && (c.purpose === 'ACTIVATE' || c.round === row.end_round)).map((c, i) => <Text key={i}>{c.actor_name} · {c.party} consented to {c.purpose === 'END' ? 'ending' : 'these terms'}</Text>)}
    {row.actions.some(a => consentActions.has(a.action)) && <View><Text>I agree to the displayed terms (revision {row.revision}) and the action selected below.</Text><Switch accessibilityLabel="Consent to displayed agreement terms" value={consent} onValueChange={setConsent} disabled={working} /></View>}
    {!!row.actions.length && <TextInput accessibilityLabel="Agreement decision reason" placeholder="Decision reason" value={reason} onChangeText={setReason} editable={!working} maxLength={1000} style={inputStyle} />}
    {row.actions.map(a => <Button key={`${a.action}-${a.party}`} title={`${actionLabels[a.action]} — ${a.party === 'TALENT' ? 'talent' : a.party === 'ORIGIN' ? row.organization_name : row.destination_name}`}
      disabled={working || (consentActions.has(a.action) && !consent) || (reasonActions.has(a.action) && !reason.trim())} onPress={() => act(a)} />)}
    {row.can_revise && <><Button title="Revise terms (requires fresh consent)" disabled={working} onPress={() => setEditing(!editing)} />
      {editing && <View style={{ gap: 12 }}><TermsFields value={terms} setValue={setTerms} transfer={row.kind === 'TRANSFER'} disabled={working} />
        <Button title="Save revised draft" disabled={working || !terms.title.trim() || !terms.terms.trim()} onPress={() => void mutate(() => apiRequest(`organizations/agreements/${row.id}/`, { method: 'PATCH', body: { ...payload(terms, row.kind === 'TRANSFER'), expected_revision: row.revision } }))} /></View>}</>}
    <Button title="View agreement history" disabled={working || loading} onPress={() => void loadHistory()} />
    {history.map(e => <View key={e.id}><Text>{e.action} · {e.actor_name} · revision {e.revision} · {new Date(e.created_at).toLocaleString()}{e.reason ? ` · ${e.reason}` : ''}</Text>{!!e.snapshot.terms && <Text selectable>Terms: {e.snapshot.terms}</Text>}</View>)}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
  </View>;
}

export default function OrganizationAgreements() {
  const { entry } = useLocalSearchParams<{ entry?: string }>();
  const [rows, setRows] = useState<Agreement[]>([]), [choices, setChoices] = useState<AgreementChoice[]>([]);
  const [destinations, setDestinations] = useState<{ id: number; name: string }[]>([]);
  const [selected, setSelected] = useState<number | null>(null), [destination, setDestination] = useState<number | null>(null);
  const [kind, setKind] = useState('CONTRACT'), [terms, setTerms] = useState<Terms>(blank());
  const [search, setSearch] = useState(''), [destinationSearch, setDestinationSearch] = useState('');
  const [loading, setLoading] = useState(true), [working, setWorking] = useState(false), [error, setError] = useState('');
  const generation = useRef(0), busy = useRef(false);
  const selectedRef = useRef<number | null>(null); selectedRef.current = selected;
  const load = useCallback(async () => {
    const current = ++generation.current; setLoading(true); setError('');
    const filter = typeof entry === 'string' && /^\d+$/.test(entry) ? '?entry=' + entry : '';
    const results = await Promise.allSettled([rosterPages<Agreement>('organizations/agreements/' + filter),
      rosterPages<AgreementChoice>('organizations/agreements/roster-choices/'), rosterPages<{ id: number; name: string }>('organizations/agreements/destinations/')]);
    if (current !== generation.current) return;
    setRows(results[0].status === 'fulfilled' ? results[0].value : []);
    const sources = results[1].status === 'fulfilled' ? results[1].value : []; setChoices(sources);
    setDestinations(results[2].status === 'fulfilled' ? results[2].value : []);
    const active = sources.find(c => c.id === (selectedRef.current ?? Number(entry)));
    setSelected(active?.id || null);
    if (selectedRef.current && !active) { setTerms(blank()); setDestination(null); }
    const failure = results.find(r => r.status === 'rejected'); if (failure?.status === 'rejected') setError(failure.reason instanceof Error ? failure.reason.message : 'Unable to load part of the agreements workspace.');
    setLoading(false);
  }, [entry]);
  useFocusEffect(useCallback(() => { void load(); return () => { generation.current += 1; }; }, [load]));
  async function mutate(operation: () => Promise<unknown>) {
    if (busy.current) return; busy.current = true; setWorking(true); setError('');
    try { await operation(); await load(); }
    catch (e) { await load(); setError(e instanceof Error ? e.message : 'Unable to update agreement.'); }
    finally { busy.current = false; setWorking(false); }
  }
  const origin = choices.find(c => c.id === selected)?.organization_id;
  return <><Stack.Screen options={{ headerShown: true, title: 'Roster agreements' }} /><Page title="Roster agreements" eyebrow="TRANSFERS AND COMMERCIAL AGREEMENTS">
    <Text>Review the same terms and explicitly consent. No payments are collected or electronic signatures issued.</Text>
    <Link href="/organization-rosters">Talent rosters</Link>
    {!!entry && <Link href="/organization-agreements">All my agreements</Link>}
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    <Button title="Refresh agreements" disabled={working || loading} onPress={() => void load()} />
    {loading ? <ActivityIndicator /> : <>
      {!!choices.length && <View style={[ui.card, { gap: 12 }]}>
        <Text style={{ fontWeight: '700' }}>Propose an agreement</Text>
        <TextInput accessibilityLabel="Find roster affiliation" placeholder="Find a confirmed talent or organization" value={search} onChangeText={setSearch} style={inputStyle} />
        {choices.filter(c => `${c.organization_name} ${c.name} ${c.tag} ${c.roster}`.toLowerCase().includes(search.toLowerCase())).slice(0, 20).map(c => <Button key={c.id} title={`${selected === c.id ? 'Selected: ' : ''}${c.organization_name} · ${c.name} · ${c.tag}`} disabled={working}
          onPress={() => { if (selected !== c.id) { setTerms(blank()); setDestination(null); } setSelected(c.id); }} />)}
        {selected && <>
          <Text>Selected affiliation: {choices.find(c => c.id === selected)?.organization_name} · {choices.find(c => c.id === selected)?.name} · {choices.find(c => c.id === selected)?.tag}</Text>
          {['CONTRACT', 'SPONSORSHIP', 'AMBASSADOR', 'TRANSFER'].map(value => <Button key={value} title={`${kind === value ? 'Selected: ' : ''}${value}`} disabled={working} onPress={() => { setKind(value); setDestination(null); }} />)}
          <TermsFields value={terms} setValue={setTerms} transfer={kind === 'TRANSFER'} disabled={working} />
          {kind === 'TRANSFER' && <><Text>Destination organization{destination ? ': ' + destinations.find(org => org.id === destination)?.name : ''}</Text><TextInput accessibilityLabel="Find destination organization" placeholder="Organization name" value={destinationSearch} onChangeText={setDestinationSearch} style={inputStyle} />
            {destinations.filter(org => org.id !== origin && org.name.toLowerCase().includes(destinationSearch.toLowerCase())).slice(0, 20).map(org => <Button key={org.id} title={`${destination === org.id ? 'Destination: ' : ''}${org.name}`} disabled={working} onPress={() => setDestination(org.id)} />)}</>}
          <Button title="Save draft" disabled={working || !terms.title.trim() || !terms.terms.trim() || (kind === 'TRANSFER' && (!destination || !terms.destination_tag.trim()))}
            onPress={() => void mutate(async () => { await apiRequest('organizations/agreements/', { method: 'POST', body: { ...payload(terms, kind === 'TRANSFER'), kind, roster_entry_id: selected, destination_id: kind === 'TRANSFER' ? destination : null } }); setTerms(blank()); setDestination(null); })} />
          <Text>Saving a draft does not give consent. Review it and submit when ready.</Text>
        </>}
      </View>}
      <Text style={{ fontWeight: '700' }}>Agreements available to you</Text>{!rows.length && <Text>No agreements available to you yet.</Text>}
      {rows.map(row => <AgreementCard key={`${row.id}-${row.revision}-${row.status}-${row.consents.length}-${row.end_round}`} row={row} working={working} mutate={mutate} />)}
    </>}
  </Page></>;
}
