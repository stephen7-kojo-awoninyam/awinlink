import { useState } from 'react';
import { Pressable, Text, TextInput } from 'react-native';
import { Stack, useLocalSearchParams, router } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { Page, ui } from '@/src/components/Page';

export default function Report() {
  const { type, id } = useLocalSearchParams<{ type: string; id: string }>();
  const [reason, setReason] = useState('spam');
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);
  async function submit() {
    setBusy(true); setMessage('');
    try { await apiRequest('safety/reports/', { method: 'POST', body: { target_type: type, target_id: Number(id), reason, details } }); setSent(true); setMessage('Report submitted for review.'); }
    catch (e) { setMessage(e instanceof Error ? e.message : 'Unable to submit report.'); }
    finally { setBusy(false); }
  }
  return <><Stack.Screen options={{ headerShown: true, title: 'Report content' }} /><Page title="Report content">
    {!sent && <>{['spam', 'harassment', 'unsafe', 'other'].map(value => <Pressable key={value} disabled={busy} accessibilityRole="radio" accessibilityState={{ checked: value === reason }} onPress={() => setReason(value)}><Text>{reason === value ? '● ' : '○ '}{value}</Text></Pressable>)}
      <TextInput accessibilityLabel="Report details" placeholder="Additional details (optional)" multiline maxLength={2000} value={details} onChangeText={setDetails} />
      <Pressable disabled={busy || !['post', 'user', 'message'].includes(type) || !Number.isSafeInteger(Number(id)) || Number(id) < 1} onPress={() => void submit()} style={ui.primaryButton}><Text style={ui.primaryButtonText}>{busy ? 'Submitting...' : 'Submit report'}</Text></Pressable></>}
    {!!message && <Text accessibilityRole="alert">{message}</Text>}
    {sent && <Pressable onPress={() => router.back()}><Text>Done</Text></Pressable>}
  </Page></>;
}
