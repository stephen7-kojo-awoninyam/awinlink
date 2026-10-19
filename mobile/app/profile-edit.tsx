import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Redirect, Stack, useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { colors } from '@/src/theme';

type Values = Record<string, string>;
const TALENT_FIELDS = [['talent_area', 'Specific talent (required for Others)'], ['headline', 'Headline'], ['biography', 'About'], ['country', 'Country'], ['city', 'City']] as const;
const ORGANIZATION_FIELDS = [['name', 'Organization name'], ['country', 'Country'], ['city', 'City'], ['website', 'Website'], ['email', 'Contact email'], ['phone', 'Phone'], ['description', 'About']] as const;

export default function EditProfileScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [values, setValues] = useState<Values>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const isTalent = user?.role === 'ATHLETE';
  const fields = isTalent ? TALENT_FIELDS : ORGANIZATION_FIELDS;

  useEffect(() => {
    let active = true;
    void apiRequest<Values>(isTalent ? 'talents/me/' : 'organizations/me/')
      .then((profile) => { if (active) setValues(Object.fromEntries(fields.map(([key]) => [key, String(profile[key] ?? '')]))); })
      .catch((loadError: unknown) => { if (active) setError(loadError instanceof Error ? loadError.message : 'Unable to load profile.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [isTalent]);

  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ATHLETE' && user.role !== 'ORGANIZATION') return <Redirect href="/(tabs)" />;

  async function save() {
    setSaving(true); setError(''); setSaved(false);
    try {
      const body = Object.fromEntries(fields.map(([key]) => [key, values[key] ?? '']));
      await apiRequest(isTalent ? 'talents/me/' : 'organizations/me/', { method: 'PATCH', body });
      setSaved(true);
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : 'Unable to save profile.');
    } finally { setSaving(false); }
  }

  return (
    <>
      <Stack.Screen options={{ headerShown: true, title: 'Edit profile', headerTintColor: colors.primary, headerShadowVisible: false }} />
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
        error && !Object.keys(values).length ? <EmptyState title="Profile unavailable" message={error}
          actionLabel="Try again" onAction={() => router.replace('/profile-edit')} /> :
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.hint}>Keep your public Awinlink profile up to date.</Text>
          <View style={styles.form}>
            {fields.map(([key, label]) => (
              <View key={key} style={styles.field}>
                <Text style={styles.label}>{label}</Text>
                <TextInput accessibilityLabel={label} value={values[key] ?? ''}
                  onChangeText={(value) => setValues((current) => ({ ...current, [key]: value }))}
                  placeholder={label} placeholderTextColor={colors.muted}
                  keyboardType={key === 'email' ? 'email-address' : key === 'website' ? 'url' : 'default'}
                  autoCapitalize={key === 'email' || key === 'website' ? 'none' : 'sentences'}
                  multiline={key === 'biography' || key === 'description'}
                  style={[styles.input, (key === 'biography' || key === 'description') && styles.multiline]}
                  textAlignVertical={key === 'biography' || key === 'description' ? 'top' : 'center'} />
              </View>
            ))}
            {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
            {saved && <Text style={styles.success}>Profile saved.</Text>}
            <Pressable accessibilityRole="button" disabled={saving} onPress={() => void save()} style={[styles.button, saving && styles.disabled]}>
              <Text style={styles.buttonText}>{saving ? 'Saving...' : 'Save profile'}</Text>
            </Pressable>
          </View>
        </ScrollView>}
    </>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingBottom: 36 },
  loader: { marginTop: 40 },
  hint: { color: colors.muted, fontSize: 13, marginBottom: 14 },
  form: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 14, padding: 16 },
  field: { gap: 6 },
  label: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, minHeight: 46, paddingHorizontal: 12 },
  multiline: { minHeight: 100, padding: 12 },
  button: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, justifyContent: 'center', minHeight: 48 },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  error: { color: colors.danger, fontSize: 12 },
  success: { color: colors.success, fontSize: 13, fontWeight: '700' },
});
