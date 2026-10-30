import { usePagedState } from '@/src/paged-state';
import { LoadMore } from '@/src/components/LoadMore';
import { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Button, Pressable, Text, TextInput, View } from 'react-native';
import { Link, Stack, useFocusEffect } from 'expo-router';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { Page, ui } from '@/src/components/Page';

type Choice = { id: number; name: string };
type Preferences = { discovery_enabled: boolean; alerts_enabled: boolean; category: string; skills: number[]; organization: number | null; selected_skills: Choice[] };
type Assessment = { score: number; qualified: boolean; explanations: string[]; evidence_complete?: boolean };
type Match = { talent_id: number; name: string; category_name: string; assessment: Assessment; match_explanation: string };
type Options = { categories: { id: string; name: string }[]; skills: Choice[]; organizations: Choice[] };

export default function RisingTalentScreen() {
  const { user } = useAuth();
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [options, setOptions] = useState<Options>({ categories: [], skills: [], organizations: [] });
  const [matches, setMatches] = usePagedState<Match>([]);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [query, setQuery] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const generation = useRef(0);
  const searchGeneration = useRef(0);
  const saving = useRef(false);

  const load = useCallback(async () => {
    const current = ++generation.current;
    searchGeneration.current += 1;
    setPreferences(null); setMatches([]); setAssessment(null);
    setError('');
    try {
      const [prefs, choices, results] = await Promise.all([
        apiRequest<Preferences>('rising-talent/preferences/'),
        apiRequest<Options>('rising-talent/options/'),
        apiRequest<{ results: Match[]; assessment: Assessment | null }>('rising-talent/matches/'),
      ]);
      if (current !== generation.current) return;
      setPreferences(prefs); setOptions(choices); setMatches(results.results); setAssessment(results.assessment);
    } catch (e) { if (current === generation.current) setError(e instanceof Error ? e.message : 'Unable to load Rising Talent.'); }
  }, [user?.id]);
  useFocusEffect(useCallback(() => { void load(); return () => { generation.current += 1; searchGeneration.current += 1; }; }, [load]));

  async function searchSkills() {
    const current = ++searchGeneration.current;
    try {
      const choices = await apiRequest<Options>(`rising-talent/options/?q=${encodeURIComponent(query.trim())}`);
      if (current === searchGeneration.current) setOptions(choices);
    } catch (e) { if (current === searchGeneration.current) setError(e instanceof Error ? e.message : 'Unable to search skills.'); }
  }

  async function save(withdraw = false) {
    if (!preferences || saving.current) return;
    saving.current = true; setBusy(true); setError(''); setMessage('');
    try {
      const { discovery_enabled, alerts_enabled, category, skills, organization } = preferences;
      await apiRequest('rising-talent/preferences/', { method: 'PATCH', body: withdraw ? { discovery_enabled: false, alerts_enabled: false } : { discovery_enabled, alerts_enabled, category, skills, organization } });
      await load(); setMessage('Rising Talent preferences saved.');
    } catch (e) { setError(e instanceof Error ? e.message : 'Unable to save preferences.'); }
    finally { saving.current = false; setBusy(false); }
  }

  function chooseSkill(skill: Choice) {
    if (!preferences) return;
    const selected = preferences.skills.includes(skill.id);
    if (!selected && preferences.skills.length >= 50) { setError('Choose up to 50 skills.'); return; }
    setPreferences({ ...preferences, skills: selected ? preferences.skills.filter(id => id !== skill.id) : [...preferences.skills, skill.id],
      selected_skills: selected ? preferences.selected_skills.filter(item => item.id !== skill.id) : [...preferences.selected_skills, skill] });
  }

  const toggle = (key: 'discovery_enabled' | 'alerts_enabled', label: string) => preferences && <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: preferences[key], disabled: busy }} disabled={busy}
    onPress={() => setPreferences({ ...preferences, [key]: !preferences[key] })} style={ui.card}><Text>{preferences[key] ? '✓ ' : ''}{label}</Text></Pressable>;

  return <><Stack.Screen options={{ headerShown: true, title: 'Rising Talent' }} /><Page title="Rising Talent" eyebrow="RECENT MOMENTUM">
    <Text>Discover emerging talent through public skills, dated achievements and growth. Signals support human review, not predictions of future success. Achievements are self-reported.</Text>
    <Text>Discovery and alerts are off until you enable them. Private profiles, private activity, follower counts and personal characteristics are excluded.</Text>
    {!!error && <Text accessibilityRole="alert">{error}</Text>}
    {!!message && <Text accessibilityRole="text">{message}</Text>}
    <Button title="Refresh Rising Talent" disabled={busy} onPress={() => void load()} />
    {!preferences ? !error && <ActivityIndicator /> : <>
      <Text style={{ fontWeight: '700' }}>Your choices</Text>
      {user?.role === 'ATHLETE' && toggle('discovery_enabled', 'Include my public talent profile in Rising Talent')}
      {['ORGANIZATION', 'SCOUT', 'COACH'].includes(user?.role || '') && <>
        {toggle('alerts_enabled', 'Notify me about relevant rising talents')}
        <Text>Choose a category and skills to find relevant talents. Choose an authorized organization for organization matching; leave it empty for personal coach or scout matching.</Text>
        {options.categories.map(category => <Button key={category.id} title={`${preferences.category === category.id ? 'Selected: ' : ''}${category.name}`} disabled={busy} onPress={() => setPreferences({ ...preferences, category: category.id })} />)}
        <Button title="No organization (personal matching)" disabled={busy} onPress={() => setPreferences({ ...preferences, organization: null })} />
        {options.organizations.map(org => <Button key={org.id} title={`${preferences.organization === org.id ? 'Selected: ' : ''}${org.name}`} disabled={busy} onPress={() => setPreferences({ ...preferences, organization: org.id })} />)}
        <Text>Selected skills</Text>
        {preferences.selected_skills.map(skill => <Button key={skill.id} title={`Remove ${skill.name}`} disabled={busy} onPress={() => chooseSkill(skill)} />)}
        <TextInput accessibilityLabel="Search Rising Talent skills" placeholder="Search skills" value={query} onChangeText={setQuery} editable={!busy} style={{ minHeight: 44, borderWidth: 1, padding: 12, borderRadius: 8 }} />
        <Button title="Search skills" disabled={busy} onPress={() => void searchSkills()} />
        {options.skills.filter(skill => !preferences.skills.includes(skill.id)).map(skill => <Button key={skill.id} title={`Add ${skill.name}`} disabled={busy} onPress={() => chooseSkill(skill)} />)}
      </>}
      <Button title={busy ? 'Saving...' : 'Save Rising Talent preferences'} disabled={busy} onPress={() => void save()} />
      <Button title="Turn off Rising Talent" disabled={busy} onPress={() => void save(true)} />
    </>}
    {assessment && <View style={ui.card}><Text style={{ fontWeight: '700' }}>{assessment.evidence_complete === false ? 'Your momentum' : `Your momentum: ${assessment.score}/100`}</Text>
      <Text>{assessment.evidence_complete === false ? 'Automatic matching paused. No score was assigned.' : assessment.qualified ? 'Recent momentum detected' : 'More evidence needed'}</Text>
      {assessment.explanations.map(reason => <Text key={reason}>{reason}</Text>)}
      <Text>Skills: up to 25 points; recent achievements: 30; measured skill growth: 30; achievement momentum: 15. Matching needs 45 points, two skills, a recent achievement and growth evidence.</Text>
    </View>}
    <Text style={{ fontWeight: '700' }}>Talents matching your focus</Text>
    {!matches.length && <Text>No current matches. Only opted-in public talents with enough recent evidence appear.</Text>}
    {matches.map(match => <View key={match.talent_id} style={ui.card}>
      <Link href={{ pathname: '/talent/[id]', params: { id: match.talent_id } }}>{match.name}</Link>
      <Text>{match.category_name} · Momentum {match.assessment.score}/100</Text>
      <Text>{match.match_explanation}</Text><Text style={{ fontWeight: '700' }}>Why this talent?</Text>
      {match.assessment.explanations.map(reason => <Text key={reason}>{reason}</Text>)}
    </View>)}

      <LoadMore items={matches} onChange={setMatches} label="Load more matches" />
    </Page></>;
}
