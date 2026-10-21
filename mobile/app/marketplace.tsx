import { useEffect, useState } from 'react';
import { Button, Switch, Text, TextInput, View } from 'react-native';
import { Link, Redirect } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page } from '@/src/components/Page';

type Listing = { id: number; talent_user: number; title: string; description: string; status: string; ecosystem: string; subecosystem: number; talent_name: string; pricing_mode?: string; base_price?: string | null; currency?: string; duration_minutes?: number; buffer_minutes?: number; booking_enabled?: boolean; revision?: number };
type Offer = { id: number; terms: string; status: string; workflow_version?: number; quoted_amount?: string; quoted_currency?: string; requested_start?: string; requested_end?: string; booking_id?: number | null };
type MessagePage = { messages: { id: number; author: number; body: string }[]; next_before: number | null };
type Room = MessagePage & { offer: Offer; permissions: { can_message: boolean; can_accept: boolean; can_decline: boolean; can_withdraw: boolean } };
type Markets = { currency?: string; ecosystems: { id: string; name: string }[]; subecosystems: { id: number; name: string }[] };
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
  const [pricingMode, setPricingMode] = useState('QUOTE_ONLY'), [basePrice, setBasePrice] = useState('');
  const [currency, setCurrency] = useState('GHS'), [duration, setDuration] = useState('60'), [buffer, setBuffer] = useState('0');
  const [bookingEnabled, setBookingEnabled] = useState(false), [revision, setRevision] = useState('');
  const [startsAt, setStartsAt] = useState(''), [negotiated, setNegotiated] = useState('');
  const [openings, setOpenings] = useState<{ starts_at: string; ends_at: string; timezone: string }[]>([]);
  const [openingNext, setOpeningNext] = useState<string | null>(null), [reviewText, setReviewText] = useState('');
  const [reviewNext, setReviewNext] = useState<string | null>(null);
  async function request<T>(path: string, data?: object, method = 'POST') {
    return apiRequest<T>('marketplace/' + path, data ? { method, body: data } : undefined);
  }
  async function showReviews(path: string, append = false) {
    const d = await request<Results<{rating: number; text: string}>>(path);
    const text = d.results.length ? d.results.map(r => `${r.rating}/5: ${r.text}`).join('\n') : 'No published reviews';
    setReviewText(current => append ? current + '\n' + text : text);
    setReviewNext(d.next ? d.next.split('/api/marketplace/')[1] : null);
  }
  async function run(fn: () => Promise<void>) { setBusy(true); setError(''); try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : 'Request failed'); } finally { setBusy(false); } }
  async function load(path = 'listings/') { const d = await request<Results<Listing>>(path); setItems(d.results); setNext(d.next ? d.next.split('/api/marketplace/')[1] : null); }
  async function open(id: number) { setRoom(await request<Room>(`deals/${id}/`)); setAcceptConsent(false); }
  async function loadOlderMessages() {
    if (!room || room.next_before === null) return;
    const id = room.offer.id, cursor = room.next_before;
    const page = await request<MessagePage>(`deals/${id}/messages/?before=${cursor}`);
    setRoom(current => {
      if (current?.offer.id !== id || current.next_before !== cursor) return current;
      const olderIds = new Set(page.messages.map(message => message.id));
      return { ...current, messages: [...page.messages, ...current.messages.filter(message => !olderIds.has(message.id))], next_before: page.next_before };
    });
  }
  useEffect(() => { if (user) void run(async () => { const d = await request<Markets>('markets/'); setMarkets(d); setCurrency(d.currency || 'GHS'); await load(); }); }, [user]);
  if (!isLoading && !user) return <Redirect href="/login" />;
  const input = (label: string, value: string, setter: (v: string) => void, multiline = false) => <TextInput accessibilityLabel={label} placeholder={label} value={value} onChangeText={setter} multiline={multiline} style={{ borderWidth: 1, borderColor: '#bbb', padding: 12, borderRadius: 8, marginVertical: 4, color: '#172b4d', backgroundColor: '#fff' }} />;
  const button = (label: string, fn: () => Promise<void>) => <Button title={label} disabled={busy} onPress={() => void run(fn)} />;
  return <Page title="Talent Market"><Link href="/market-bookings">My bookings and availability</Link><Text>No online payments. Prices are agreed service prices.</Text><Text accessibilityRole="alert">{error}</Text>
    {input('Search', query, setQuery)}{input('Country', country, setCountry)}{input('Skill', skill, setSkill)}
    <Text>Ecosystem</Text><Button title="All ecosystems" onPress={() => setEcosystem('')} />
    {markets.ecosystems.map(x => <Button key={x.id} title={(ecosystem === x.id ? '✓ ' : '') + x.name} onPress={() => setEcosystem(x.id)} />)}
    <Text>Subecosystem</Text><Button title="All subecosystems" onPress={() => setDomain('')} />
    {markets.subecosystems.map(x => <Button key={x.id} title={(domain === String(x.id) ? '✓ ' : '') + x.name} onPress={() => setDomain(String(x.id))} />)}
    {input('Work type: REMOTE, ONSITE, HYBRID', workType, setWorkType)}{input('Experience: BEGINNER, INTERMEDIATE, EXPERT', experience, setExperience)}
    {button('Search markets', () => load('listings/?' + new URLSearchParams({ q: query, ecosystem, subecosystem: domain, country, skill, work_type: workType, experience })))}
    {button('My listings', () => load('listings/?mine=1'))}
    {items.map(x => <View key={x.id} style={{ padding: 16, marginVertical: 8, backgroundColor: '#eef3ff', borderRadius: 12 }}><Text style={{ fontSize: 20 }}>{x.title}</Text><Text>{x.talent_name} · {x.status}</Text><Text>{x.description}</Text>{button('Offer for this listing', async () => { setListingId(String(x.id)); setRevision(x.booking_enabled ? String(x.revision) : ''); setStartsAt(''); setNegotiated(''); setOpenings([]); setOpeningNext(null); if(x.booking_enabled) { const d = await request<Results<{starts_at: string; ends_at: string; timezone: string}>>(`availability/?listing=${x.id}`); setOpenings(d.results); setOpeningNext(d.next ? d.next.split('/api/marketplace/')[1] : null); } })}<Text>{x.booking_enabled ? `${x.pricing_mode}: ${x.base_price || 'Propose price'} ${x.currency}; ${x.duration_minutes} minutes` : 'Negotiation only'}</Text>{button('Verified reviews', () => showReviews(`listings/${x.id}/reviews/`))}{x.talent_user === user?.id && <Button title="Edit my listing" onPress={() => { setEditId(String(x.id)); setTitle(x.title); setDescription(x.description); setEcosystem(x.ecosystem); setDomain(String(x.subecosystem)); setPublicationConsent(false); setPricingMode(x.pricing_mode || 'QUOTE_ONLY'); setBasePrice(x.base_price || ''); setCurrency(x.currency || 'GHS'); setDuration(String(x.duration_minutes || 60)); setBuffer(String(x.buffer_minutes || 0)); setBookingEnabled(!!x.booking_enabled); }} />}</View>)}
    {!items.length && <Text>No listings found.</Text>}{next && button('Next page', () => load(next))}
    <Text>{reviewText}</Text>{reviewNext && button('More reviews', () => showReviews(reviewNext, true))}<Text style={{ fontSize: 22 }}>My listing</Text><Text>Select an ecosystem and subecosystem above.</Text>
    {input('Listing ID (empty to create)', editId, setEditId)}{input('Title', title, setTitle)}{input('Description', description, setDescription, true)}
    <Text>Pricing</Text>{['QUOTE_ONLY','FIXED','HOURLY'].map(mode => <Button key={mode} title={(pricingMode===mode?'Selected: ':'')+mode} onPress={() => setPricingMode(mode)} />)}
    {input('Base price (empty for quote-only)', basePrice, setBasePrice)}{input('Currency', currency, setCurrency)}{input('Duration minutes', duration, setDuration)}{input('Buffer minutes each side', buffer, setBuffer)}
    <Text>Enable scheduled bookings</Text><Switch accessibilityLabel="Enable bookings" value={bookingEnabled} onValueChange={setBookingEnabled} />
    <Text>I consent to publishing these listing details.</Text><Switch accessibilityLabel="Publication consent" value={publicationConsent} onValueChange={setPublicationConsent} />
    {(['DRAFT', 'PUBLISHED', 'PAUSED'] as const).map(status => <View key={status}>{button('Save as ' + status, async () => { await request(editId ? `listings/${editId}/` : 'listings/', { title, description, ecosystem, subecosystem: Number(domain), status, consent: publicationConsent, pricing_mode: pricingMode, base_price: basePrice || null, currency, duration_minutes: Number(duration), buffer_minutes: Number(buffer), booking_enabled: bookingEnabled }, editId ? 'PATCH' : 'POST'); await load('listings/?mine=1'); })}</View>)}
    <Text style={{ fontSize: 22 }}>Send an offer</Text>{input('Listing ID', listingId, setListingId)}{input('Organization ID (optional)', org, setOrg)}{input('Exact offer terms', terms, setTerms, true)}
    {input('Appointment start (ISO with UTC offset)', startsAt, setStartsAt)}{input('Listing revision', revision, setRevision)}{input('Proposed price (quote-only)', negotiated, setNegotiated)}
    <Text>Either participant may cancel before the appointment starts. No cancellation after work starts.</Text>
    {openings.map(w => <View key={w.starts_at}><Text>{w.starts_at} - {w.ends_at} ({w.timezone})</Text><Button title="Choose this opening" onPress={() => setStartsAt(w.starts_at)} /></View>)}
    {openingNext && button('More openings', async () => { const d = await request<Results<{starts_at: string; ends_at: string; timezone: string}>>(openingNext); setOpenings(d.results); setOpeningNext(d.next ? d.next.split('/api/marketplace/')[1] : null); })}
    {button('Send offer', async () => { const x = await request<Offer>('offers/', { listing: Number(listingId), ...(org ? { organization: Number(org) } : {}), terms, ...(startsAt ? {starts_at: startsAt} : {}), ...(revision ? {expected_revision: Number(revision)} : {}), ...(negotiated ? {negotiated_amount: negotiated} : {}) }); await open(x.id); })}
    {button('My deal rooms', async () => { setOffers((await request<Results<Offer>>('offers/')).results); })}
    {offers.map(x => <View key={x.id}>{button(`Offer #${x.id} · ${x.status}`, () => open(x.id))}</View>)}
    {room && <View><Text style={{ fontSize: 22 }}>Deal room #{room.offer.id}</Text><Text>{room.offer.terms}</Text><Text>{room.offer.status}</Text>{room.offer.workflow_version === 2 && <Text>{room.offer.quoted_amount} {room.offer.quoted_currency}: {room.offer.requested_start} - {room.offer.requested_end}</Text>}{room.offer.booking_id && <Link href={{pathname: "/market-bookings", params: {booking: String(room.offer.booking_id)}}}>Open booking</Link>}{room.messages.map(m => <Text key={m.id}>{m.author}: {m.body}</Text>)}
      {room.next_before !== null && button('Load older messages', loadOlderMessages)}
      {room.permissions.can_message ? <>{input('Message', body, setBody, true)}{button('Send message', async () => { await request(`deals/${room.offer.id}/messages/`, { body }); setBody(''); await open(room.offer.id); })}</> : <Text>This deal room is read-only after a decision.</Text>}
      {room.permissions.can_accept && <><Text>I have read and explicitly agree to these exact offer terms.</Text><Switch accessibilityLabel="Accept offer consent" value={acceptConsent} onValueChange={setAcceptConsent} /></>}
      {(['ACCEPT', 'DECLINE', 'WITHDRAW'] as const).filter(action => room.permissions[('can_' + action.toLowerCase()) as keyof Room['permissions']]).map(action => <View key={action}>{button(action, async () => { await request(`deals/${room.offer.id}/`, { action, consent: acceptConsent }); await open(room.offer.id); })}</View>)}
    </View>}
  </Page>;
}
