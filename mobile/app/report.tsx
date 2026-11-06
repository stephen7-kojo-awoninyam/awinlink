import { useEffect, useRef, useState } from 'react';
import { Pressable, Text, TextInput } from 'react-native';
import { Stack, useLocalSearchParams, router } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { Page, ui } from '@/src/components/Page';
import { useAuth } from '@/src/auth/AuthProvider';

export default function Report() {
  const { user } = useAuth();
  const { type, id } = useLocalSearchParams<{ type: string; id: string }>();
  const targetType = type === 'safety' ? 'safety' : type;
  const targetId = targetType === 'safety' ? 0 : Number(id);
  const key = `${user?.id}:${targetType}:${targetId}`;
  const target = useRef({ key });
  if (target.current.key !== key) target.current = { key };
  const renderedTarget = target.current;
  const mounted = useRef(true);
  const [reason, setReason] = useState(type === 'safety' ? 'child_safety' : 'spam');
  const sending = useRef(false);
  const [details, setDetails] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [sent, setSent] = useState(false);
  useEffect(() => { setReason(targetType === 'safety' ? 'child_safety' : 'spam'); setDetails(''); setSent(false); setMessage(''); }, [renderedTarget]);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function submit() {
    if (!mounted.current || sending.current || sent || target.current !== renderedTarget) return;
    const reportReason = targetType === 'safety' ? 'child_safety' : reason;
    if (reportReason === 'child_safety' && details.trim().length < 10) {
      setMessage('Describe the child-safety concern in at least 10 characters. Do not attach CSAM.'); return;
    }
    sending.current = true;
    setBusy(true); setMessage('');
    try { await apiRequest('safety/reports/', { method: 'POST', body: { target_type: targetType, target_id: targetId, reason: reportReason, details } }); if (mounted.current && target.current === renderedTarget) { setSent(true); setMessage('Report submitted for review.'); } }
    catch (e) { if (mounted.current && target.current === renderedTarget) setMessage(e instanceof Error ? e.message : 'Unable to submit report.'); }
    finally { sending.current = false; if (mounted.current) setBusy(false); }
  }
  return <><Stack.Screen options={{ headerShown: true, title: 'Report content' }} /><Page title="Report content">
    <Text>For child-safety concerns, do not upload, forward or describe graphic details of suspected CSAM. Include a username or record link and approximate time. Reports are submitted for authorized review; no response deadline is promised. For immediate danger, contact local emergency services.</Text>
    {!sent && <>{(targetType === 'safety' ? ['child_safety'] : ['spam', 'harassment', 'unsafe', 'other', 'child_safety']).map(value => <Pressable key={value} disabled={busy} accessibilityRole="radio" accessibilityState={{ checked: value === reason }} onPress={() => setReason(value)}><Text>{reason === value ? '● ' : '○ '}{value === 'child_safety' ? 'Child safety (CSAE/CSAM)' : value}</Text></Pressable>)}
      <TextInput accessibilityLabel="Report details" placeholder="Additional details (optional)" multiline maxLength={2000} value={details} onChangeText={setDetails} />
      <Pressable disabled={busy || !['post', 'user', 'message', 'safety'].includes(targetType) || !Number.isSafeInteger(targetId) || (targetType !== 'safety' && targetId < 1)} onPress={() => void submit()} style={ui.primaryButton}><Text style={ui.primaryButtonText}>{busy ? 'Submitting...' : 'Submit report'}</Text></Pressable></>}
    {!!message && <Text accessibilityRole="alert">{message}</Text>}
    {sent && <Pressable onPress={() => router.back()}><Text>Done</Text></Pressable>}
  </Page></>;
}
