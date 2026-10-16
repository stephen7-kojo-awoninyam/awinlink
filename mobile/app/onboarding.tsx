import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Redirect, Stack, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { colors } from '@/src/theme';

const TALENT_CATEGORIES = [
  { value: 'SPORTS', label: 'Sports' },
  { value: 'SCIENCE_TECHNOLOGY', label: 'Science & technology' },
  { value: 'ARTS', label: 'Arts' },
  { value: 'OTHERS', label: 'Others' },
];

export default function OnboardingScreen() {
  const { user, isLoading } = useAuth();
  const router = useRouter();
  const [talent, setTalent] = useState({
    talent_category: '',
    talent_area: '',
    headline: '',
    biography: '',
    country: '',
    city: '',
  });
  const [organization, setOrganization] = useState({
    name: '',
    country: '',
    city: '',
    website: '',
    email: '',
    phone: '',
    description: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (isLoading) return null;
  if (!user) return <Redirect href="/login" />;
  if (user.role !== 'ATHLETE' && user.role !== 'ORGANIZATION') {
    return <Redirect href="/(tabs)" />;
  }

  async function submitTalent() {
    if (!talent.talent_category || !talent.talent_area.trim()) {
      setError('Choose your talent ecosystem and tell us your specialty.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await apiRequest('talents/me/', {
        method: 'PATCH',
        body: {
          ...talent,
          talent_area: talent.talent_area.trim(),
          headline: talent.headline.trim(),
          biography: talent.biography.trim(),
          country: talent.country.trim(),
          city: talent.city.trim(),
        },
      });
      router.replace('/(tabs)');
    } catch (onboardingError) {
      setError(
        onboardingError instanceof Error
          ? onboardingError.message
          : 'Unable to save your talent profile.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function submitOrganization() {
    if (!organization.name.trim() || !organization.country.trim()) {
      setError('Organization name and country are required.');
      return;
    }
    setSubmitting(true);
    setError('');
    try {
      await apiRequest('organizations/me/', {
        method: 'PATCH',
        body: {
          ...organization,
          name: organization.name.trim(),
          country: organization.country.trim(),
          city: organization.city.trim(),
          website: organization.website.trim(),
          email: organization.email.trim(),
          phone: organization.phone.trim(),
          description: organization.description.trim(),
        },
      });
      router.replace('/(tabs)');
    } catch (onboardingError) {
      setError(
        onboardingError instanceof Error
          ? onboardingError.message
          : 'Unable to save your organization profile.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  const isTalent = user.role === 'ATHLETE';
  const updateTalent = (key: keyof typeof talent, value: string) =>
    setTalent((current) => ({ ...current, [key]: value }));
  const updateOrganization = (key: keyof typeof organization, value: string) =>
    setOrganization((current) => ({ ...current, [key]: value }));

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <SafeAreaView style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          style={styles.flex}
        >
          <ScrollView
            contentContainerStyle={styles.content}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <Text style={styles.brand}>AWINLINK</Text>
            <Text style={styles.heading}>
              {isTalent ? 'Choose your ecosystem' : 'Complete your organization profile'}
            </Text>
            <Text style={styles.description}>
              {isTalent
                ? 'Your ecosystem shapes what you see, while you can still discover people across Awinlink.'
                : 'Add the details people need to recognize and connect with your organization.'}
            </Text>

            <View style={styles.form}>
              {isTalent ? (
                <>
                  <Text style={styles.label}>Talent category</Text>
                  <View style={styles.choices}>
                    {TALENT_CATEGORIES.map((category) => (
                      <Pressable
                        accessibilityRole="button"
                        accessibilityState={{ selected: talent.talent_category === category.value }}
                        key={category.value}
                        onPress={() => updateTalent('talent_category', category.value)}
                        style={[
                          styles.choice,
                          talent.talent_category === category.value && styles.choiceSelected,
                        ]}
                      >
                        <Text
                          style={[
                            styles.choiceText,
                            talent.talent_category === category.value && styles.choiceTextSelected,
                          ]}
                        >
                          {category.label}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                  <Field label="Your specialty" placeholder="Basketball, AI, music..." value={talent.talent_area} onChangeText={(value) => updateTalent('talent_area', value)} />
                  <Field label="Profile headline (optional)" placeholder="A short introduction" value={talent.headline} onChangeText={(value) => updateTalent('headline', value)} />
                  <Field label="About you (optional)" multiline placeholder="Tell the community about yourself" value={talent.biography} onChangeText={(value) => updateTalent('biography', value)} />
                  <Field label="Country (optional)" placeholder="Country" value={talent.country} onChangeText={(value) => updateTalent('country', value)} />
                  <Field label="City (optional)" placeholder="City" value={talent.city} onChangeText={(value) => updateTalent('city', value)} />
                </>
              ) : (
                <>
                  <Field label="Organization name" placeholder="Organization name" value={organization.name} onChangeText={(value) => updateOrganization('name', value)} />
                  <Field label="Country" placeholder="Country" value={organization.country} onChangeText={(value) => updateOrganization('country', value)} />
                  <Field label="City (optional)" placeholder="City" value={organization.city} onChangeText={(value) => updateOrganization('city', value)} />
                  <Field label="Website (optional)" autoCapitalize="none" keyboardType="url" placeholder="https://" value={organization.website} onChangeText={(value) => updateOrganization('website', value)} />
                  <Field label="Contact email (optional)" autoCapitalize="none" keyboardType="email-address" placeholder="contact@example.com" value={organization.email} onChangeText={(value) => updateOrganization('email', value)} />
                  <Field label="Phone (optional)" keyboardType="phone-pad" placeholder="Phone number" value={organization.phone} onChangeText={(value) => updateOrganization('phone', value)} />
                  <Field label="About (optional)" multiline placeholder="What does your organization do?" value={organization.description} onChangeText={(value) => updateOrganization('description', value)} />
                </>
              )}

              {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
              <Pressable
                accessibilityRole="button"
                disabled={submitting}
                onPress={() => void (isTalent ? submitTalent() : submitOrganization())}
                style={({ pressed }) => [styles.submitButton, pressed && styles.pressed]}
              >
                {submitting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.submitText}>Continue to Awinlink</Text>
                )}
              </Pressable>
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </>
  );
}

function Field({
  label,
  value,
  onChangeText,
  placeholder,
  multiline = false,
  autoCapitalize,
  keyboardType,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  multiline?: boolean;
  autoCapitalize?: 'none' | 'sentences';
  keyboardType?: 'default' | 'email-address' | 'phone-pad' | 'url';
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        autoCapitalize={autoCapitalize || 'sentences'}
        keyboardType={keyboardType || 'default'}
        multiline={multiline}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        style={[styles.input, multiline && styles.multiline]}
        textAlignVertical={multiline ? 'top' : 'center'}
        value={value}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  flex: { flex: 1 },
  content: { padding: 24, paddingBottom: 40 },
  brand: { color: colors.primary, fontSize: 13, fontWeight: '800', letterSpacing: 3, textAlign: 'center' },
  heading: { color: colors.ink, fontSize: 25, fontWeight: '800', marginTop: 24, textAlign: 'center' },
  description: { color: colors.muted, fontSize: 13, lineHeight: 20, marginTop: 8, textAlign: 'center' },
  form: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 20, borderWidth: 1, gap: 13, marginTop: 22, padding: 17 },
  field: { gap: 6 },
  label: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  choice: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 18, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 9 },
  choiceSelected: { backgroundColor: colors.softBlue, borderColor: colors.primary },
  choiceText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  choiceTextSelected: { color: colors.primary },
  input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, fontSize: 14, minHeight: 46, paddingHorizontal: 11 },
  multiline: { minHeight: 95, padding: 11 },
  error: { color: colors.danger, fontSize: 12, lineHeight: 18 },
  submitButton: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 12, justifyContent: 'center', minHeight: 50 },
  submitText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  pressed: { opacity: 0.8 },
});
