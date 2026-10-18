import { useEffect, useState } from 'react';
import { Button, Switch, Text, TextInput, View } from 'react-native';
import { Redirect } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page } from '@/src/components/Page';

type Listing = { id: number; talent_user: number; title: string; description: string; status: string; ecosystem: string; subecosystem: number; talent_name: string };
type Offer = { id: number; terms: string; status: string };
type Room = { offer: Offer; messages: { id: number; author: number; body: string }[] };
type Markets = { ecosystems: { id: string; name: string }[]; subecosystems: { id: number; name: string }[] };
type Results<T> = { results: T[]; next: string | null };

export default function Marketplace() {
  const { user, isLoading } = useAuth();
  const [markets, setMarkets] = useState<Markets>({ ecosystems: [], subecosystems: [] });
  const [items, setItems] = useState<Listing[]>([]), [offers, setOffers] = useState<Offer[]>([]);
  const [room, setRoom] = useState<Room | null>(null), [error, setError] = useState('');
  const [query, setQuery] = useState(''), [ecosystem, setEcosystem] = useState(''), [domain, setDomain] = useState('');
  const [country, setCountry] = useState(''), [skill, setSkill] = useState('');
  const [workType, setWorkType] = useState(''), [experience, setExperience] = useState('');
  const [title, setTitle] = useState(''), [description, setDescription] = useState(''), [editId, setEditId] = useState('');
  const [listingId, setListingId] = useState(''), [org, setOrg] = useState(''), [terms, setTerms] = useState(''), [body, setBody] = useState('');
  const [publicationConsent, setPublicationConsent] = useState(false), [acceptConsent, setAcceptConsent] = useState(false);
  const [busy, setBusy] = useState(false), [next, setNext] = useState<string | null>(null);
  async function request<T>(path: string, data?: object, method = 'POST') {
    return apiRequest<T>('marketplace/' + path, data ? { method, body: JSON.stringify(data) } : undefined);
  }
  async function run(fn: () => Promise<void>) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); } finally { setBusy(false); } }
  async function load(path = 'listings/') { const d = await request<Results<Listing>>(path); setItems(d.results); setNext(d.next ? d.next.split('/api/marketplace/')[1] : null); }
  async function open(id: number) { setRoom(await request<Room>(`deals/${id}/`)); setAcceptConsent(false); }
  useEffect(() => { if (user) void run(async () => { setMarkets(await request<Markets>('markets/')); await load(); }); }, [user]);
  if (!isLoading && !user) return <Redirect href="/login" />;
  const input = (label: string, value: string, setter: (v: string) => void, multiline = false) => <TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={setter} multiline={multiline} style={{ borderWidth: 1, borderColor: '#bbb', padding: 12, borderRadius: 8, marginVertical: 4, color: '#172b4d', backgroundColor: '#fff' }} />;
  const button = (label: string, fn: () => Promise<void>) => <Button title={label} disabled={busy} onPress={() => void run(fn)} />;
  return <Page title="Talent Market"><Text accessibilityRole="alert">{error}</Text>
    {input('Search', query, setQuery)}{input('Country', country, setCountry)}{input('Skill', skill, setSkill)}
    <Text>Ecosystem</Text><Button title="All ecosystems" onPress={() => setEcosystem('')} />
    {markets.ecosystems.map(x => <Button key={x.id} title={(ecosystem === x.id ? '✓ ' : '') + x.name} onPress={() => setEcosystem(x.id)} />)}
    <Text>Subecosystem</Text><Button title="All subecosystems" onPress={() => setDomain('')} />
    {markets.subecosystems.map(x => <Button key={x.id} title={(domain === String(x.id) ? '✓ ' : '') + x.name} onPress={() => setDomain(String(x.id))} />)}
    {input('Work type: REMOTE, ONSITE, HYBRID', workType, setWorkType)}{input('Experience: BEGINNER, INTERMEDIATE, EXPERT', experience, setExperience)}
    {button('Search markets', () => load('listings/?' + new URLSearchParams({ q: query, ecosystem, subecosystem: domain, country, skill, work_type: workType, experience })))}
    {button('My listings', () => load('listings/?mine=1'))}
    {items.map(x => <View key={x.id} style={{ padding: 16, marginVertical: 8, backgroundColor: '#eef3ff', borderRadius: 12 }}><Text style={{ fontSize: 20 }}>{x.title}</Text><Text>{x.talent_name} · {x.status}</Text><Text>{x.description}</Text><Button title="Offer for this listing" onPress={() => setListingId(String(x.id))} /><Button title="Edit my listing" onPress={() => { setEditId(String(x.id)); setTitle(x.title); setDescription(x.description); setEcosystem(x.ecosystem); setDomain(String(x.subecosystem)); setPublicationConsent(false); }} /></View>)}
    {!items.length && <Text>No listings found.</Text>}{next && button('Next page', () => load(next))}
    <Text style={{ fontSize: 22 }}>My listing</Text><Text>Select an ecosystem and subecosystem above.</Text>
    {input('Listing ID (empty to create)', editId, setEditId)}{input('Title', title, setTitle)}{input('Description', description, setDescription, true)}
    <Text>I consent to publishing these listing details.</Text><Switch accessibilityLabel="Publication consent" value={publicationConsent} onValueChange={setPublicationConsent} />
    {(['DRAFT', 'PUBLISHED', 'PAUSED'] as const).map(status => <View key={status}>{button('Save as ' + status, async () => { await request(editId ? `listings/${editId}/` : 'listings/', { title, description, ecosystem, subecosystem: Number(domain), status, consent: publicationConsent }, editId ? 'PATCH' : 'POST'); await load('listings/?mine=1'); })}</View>)}
    <Text style={{ fontSize: 22 }}>Send an offer</Text>{input('Listing ID', listingId, setListingId)}{input('Organization ID (optional)', org, setOrg)}{input('Exact offer terms', terms, setTerms, true)}
    {button('Send offer', async () => { const x = await request<Offer>('offers/', { listing: Number(listingId), ...(org ? { organization: Number(org) } : {}), terms }); await open(x.id); })}
    {button('My deal rooms', async () => { setOffers((await request<Results<Offer>>('offers/')).results); })}
    {offers.map(x => <View key={x.id}>{button(`Offer #${x.id} · ${x.status}`, () => open(x.id))}</View>)}
    {room && <View><Text style={{ fontSize: 22 }}>Deal room #{room.offer.id}</Text><Text>{room.offer.terms}</Text><Text>{room.offer.status}</Text>{room.messages.map(m => <Text key={m.id}>{m.author}: {m.body}</Text>)}
      {input('Message', body, setBody, true)}{button('Send message', async () => { await request(`deals/${room.offer.id}/messages/`, { body }); setBody(''); await open(room.offer.id); })}
      <Text>I have read and explicitly agree to these exact offer terms.</Text><Switch accessibilityLabel="Accept offer consent" value={acceptConsent} onValueChange={setAcceptConsent} />
      {['ACCEPT', 'DECLINE', 'WITHDRAW'].map(action => <View key={action}>{button(action, async () => { await request(`deals/${room.offer.id}/`, { action, consent: acceptConsent }); await open(room.offer.id); })}</View>)}
    </View>}
  </Page>;
}
