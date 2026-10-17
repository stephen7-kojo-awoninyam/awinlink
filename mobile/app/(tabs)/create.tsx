import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page, ui } from '@/src/components/Page';
import { colors } from '@/src/theme';

type CreateOption = {
  key: string;
  title: string;
  description: string;
  enabled: boolean;
  icon: string;
};

type Choice = { value: string; label: string };
type Domain = { id: number; name: string };
type FormValues = Record<string, string>;

const OPTIONS_BY_ROLE: Record<string, CreateOption[]> = {
  ATHLETE: [
    { key: 'post', title: 'Post', description: 'Share an update with your ecosystem.', enabled: true, icon: '✎' },
    { key: 'portfolio', title: 'Portfolio', description: 'Showcase work, projects, and your story.', enabled: true, icon: '▧' },
    { key: 'achievement', title: 'Achievement', description: 'Add a milestone to your portfolio.', enabled: true, icon: '★' },
  ],
  ORGANIZATION: [
    { key: 'opportunity', title: 'Opportunity', description: 'Publish a role, trial, or scholarship.', enabled: true, icon: '↗' },
    { key: 'competition', title: 'Competition', description: 'Create a competition for your community.', enabled: true, icon: '♜' },
    { key: 'post', title: 'Post', description: 'Share an update with your audience.', enabled: true, icon: '✎' },
  ],
  DEFAULT: [
    { key: 'post', title: 'Post', description: 'Share an update with your ecosystem.', enabled: true, icon: '✎' },
  ],
};

const OPPORTUNITY_TYPES: Choice[] = [
  { value: 'JOB', label: 'Job' },
  { value: 'TRIAL', label: 'Sports trial' },
  { value: 'SCHOLARSHIP', label: 'Scholarship' },
  { value: 'AUDITION', label: 'Audition' },
];
const WORK_TYPES: Choice[] = [
  { value: 'REMOTE', label: 'Remote' },
  { value: 'ONSITE', label: 'On site' },
  { value: 'HYBRID', label: 'Hybrid' },
];
const EXPERIENCE_LEVELS: Choice[] = [
  { value: 'BEGINNER', label: 'Beginner' },
  { value: 'INTERMEDIATE', label: 'Intermediate' },
  { value: 'EXPERT', label: 'Expert' },
];
const COMPETITION_CATEGORIES: Choice[] = [
  { value: 'SPORTS', label: 'Sports' },
  { value: 'SCIENCE_TECHNOLOGY', label: 'Science & technology' },
  { value: 'ARTS', label: 'Arts' },
  { value: 'OTHERS', label: 'Others' },
];
const PORTFOLIO_TYPES: Choice[] = [
  { value: 'PROJECT', label: 'Project' },
  { value: 'IMAGE', label: 'Image' },
  { value: 'VIDEO', label: 'Video' },
  { value: 'DOCUMENT', label: 'Document' },
  { value: 'CERTIFICATE', label: 'Certificate' },
  { value: 'ACHIEVEMENT', label: 'Achievement' },
];

const INITIAL_VALUES: FormValues = {
  title: '',
  description: '',
  opportunity_type: 'JOB',
  domain: '',
  experience_level: 'BEGINNER',
  work_type: 'REMOTE',
  location: '',
  deadline: '',
  category: 'SPORTS',
  discipline: '',
  registration_start: '',
  registration_end: '',
  competition_start: '',
  competition_end: '',
  competition_location: '',
  requirements: '',
  prizes: '',
  rules: '',
  max_participants: '',
  item_type: 'PROJECT',
  link: '',
  caption: '',
};

function FormField({
  label,
  value,
  onChangeText,
  placeholder,
  multiline = false,
  keyboardType,
}: {
  label: string;
  value: string;
  onChangeText: (value: string) => void;
  placeholder: string;
  multiline?: boolean;
  keyboardType?: 'default' | 'numeric' | 'url';
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        accessibilityLabel={label}
        autoCapitalize={keyboardType === 'url' ? 'none' : 'sentences'}
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

function ChoiceField({
  label,
  value,
  choices,
  onChange,
}: {
  label: string;
  value: string;
  choices: Choice[];
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <View style={styles.choices}>
        {choices.map((choice) => (
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ selected: value === choice.value }}
            key={choice.value}
            onPress={() => onChange(choice.value)}
            style={[styles.choice, value === choice.value && styles.choiceSelected]}
          >
            <Text style={[styles.choiceText, value === choice.value && styles.choiceTextSelected]}>
              {choice.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export default function CreateScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const options = OPTIONS_BY_ROLE[user?.role ?? ''] ?? OPTIONS_BY_ROLE.DEFAULT;
  const [selected, setSelected] = useState('');
  const [values, setValues] = useState<FormValues>(INITIAL_VALUES);
  const [domains, setDomains] = useState<Domain[]>([]);
  const [domainLoadStatus, setDomainLoadStatus] = useState<'idle' | 'loading' | 'loaded' | 'error'>('idle');
  const [domainError, setDomainError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [isError, setIsError] = useState(false);
  const [postMedia, setPostMedia] = useState<DocumentPicker.DocumentPickerAsset | null>(null);

  async function selectPostMedia() {
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: ['image/*', 'video/*'], copyToCacheDirectory: true });
      if (!result.canceled) setPostMedia(result.assets[0]);
    } catch (e) { setIsError(true); setMessage(e instanceof Error ? e.message : 'Unable to select media.'); }
  }

  function updateValue(key: string, value: string) {
    setValues((current) => ({ ...current, [key]: value }));
  }

  useEffect(() => {
    if (selected !== 'opportunity' || domainLoadStatus !== 'idle') return;
    let active = true;
    setDomainLoadStatus('loading');
    void apiRequest<Domain[]>('domains/')
      .then((result) => {
        if (active) {
          setDomains(result);
          setDomainLoadStatus('loaded');
        }
      })
      .catch((loadError: unknown) => {
        if (active) {
          setDomainError(
            loadError instanceof Error ? loadError.message : 'Unable to load opportunity domains.',
          );
          setDomainLoadStatus('error');
        }
      })
      ;
    return () => {
      active = false;
    };
  }, [domainLoadStatus, selected]);

  async function submit() {
    setSubmitting(true);
    setMessage('');
    setIsError(false);
    try {
      if (selected === 'post') {
        if (!values.caption.trim() && !postMedia) throw new Error('Write something or attach media before sharing your post.');
        let body: unknown = { caption: values.caption.trim(), visibility: 'PUBLIC' };
        if (postMedia) {
          const form = new FormData();
          form.append('caption', values.caption.trim()); form.append('visibility', 'PUBLIC');
          const mime = postMedia.mimeType || (postMedia.name.match(/\.(mp4|mov|webm)$/i) ? 'video/mp4' : 'image/jpeg');
          form.append(mime.startsWith('video/') ? 'video' : 'image', Platform.OS === 'web' && postMedia.file ? postMedia.file : { uri: postMedia.uri, name: postMedia.name, type: mime } as unknown as Blob);
          body = form;
        }
        await apiRequest('feed/posts/create/', {
          method: 'POST',
          body,
        });
        setPostMedia(null);
        setValues(INITIAL_VALUES);
        setSelected('');
        router.navigate('/(tabs)');
        return;
      }

      if (selected === 'portfolio' || selected === 'achievement') {
        if (!values.title.trim()) throw new Error('Add a title for this portfolio item.');
        const itemType = selected === 'achievement' ? 'ACHIEVEMENT' : values.item_type;
        const body: Record<string, string> = {
          title: values.title.trim(),
          description: values.description.trim(),
          item_type: itemType,
          link: values.link.trim(),
        };
        await apiRequest('portfolio/create/', { method: 'POST', body });
        setValues(INITIAL_VALUES);
        setMessage('Added to your portfolio.');
        return;
      }

      if (selected === 'opportunity') {
        if (!values.title.trim() || !values.description.trim() || !values.domain) {
          throw new Error('Add a title, description, and domain for this opportunity.');
        }
        const body: Record<string, string> = {
          title: values.title.trim(),
          description: values.description.trim(),
          opportunity_type: values.opportunity_type,
          domain: values.domain,
          experience_level: values.experience_level,
          work_type: values.work_type,
          location: values.location.trim(),
        };
        if (values.deadline.trim()) body.deadline = values.deadline.trim();
        await apiRequest('opportunities/create/', { method: 'POST', body });
        setValues(INITIAL_VALUES);
        setMessage('Opportunity published.');
        return;
      }

      if (selected === 'competition') {
        const requiredFields = [
          'title',
          'description',
          'registration_start',
          'registration_end',
          'competition_start',
          'competition_end',
        ];
        if (requiredFields.some((field) => !values[field].trim())) {
          throw new Error('Complete the title, description, and all four competition dates.');
        }
        const body: Record<string, string | boolean> = {
          title: values.title.trim(),
          description: values.description.trim(),
          category: values.category,
          discipline: values.discipline.trim(),
          registration_start: values.registration_start.trim(),
          registration_end: values.registration_end.trim(),
          competition_start: values.competition_start.trim(),
          competition_end: values.competition_end.trim(),
          location: values.competition_location.trim(),
          online: !values.competition_location.trim(),
          requirements: values.requirements.trim(),
          prizes: values.prizes.trim(),
          rules: values.rules.trim(),
        };
        if (values.max_participants.trim()) {
          const maxParticipants = Number(values.max_participants);
          if (!Number.isInteger(maxParticipants) || maxParticipants < 1) {
            throw new Error('Maximum participants must be a positive whole number.');
          }
          body.max_participants = String(maxParticipants);
        }
        const competition = await apiRequest<{ id: number }>('competitions/create/', { method: 'POST', body });
        try {
          await apiRequest(`competitions/${competition.id}/action/`, { method: 'POST', body: { action: 'submit' } });
        } catch (submitError) {
          setIsError(true);
          setMessage(`Saved as a draft, but submission failed: ${submitError instanceof Error ? submitError.message : 'Please try again.'}`);
          return;
        }
        setValues(INITIAL_VALUES);
        setMessage('Competition submitted for review.');
      }
    } catch (createError) {
      setIsError(true);
      setMessage(
        createError instanceof Error ? createError.message : 'Unable to create this item.',
      );
    } finally {
      setSubmitting(false);
    }
  }

  const submitLabel =
    selected === 'post'
      ? 'Share post'
      : selected === 'portfolio' || selected === 'achievement'
        ? 'Add to portfolio'
        : selected === 'competition'
          ? 'Create competition'
          : 'Publish opportunity';

  return (
    <Page eyebrow="SHARE WITH YOUR ECOSYSTEM" title="Create">
      <View style={styles.intro}>
        <Text style={styles.introTitle}>What would you like to create?</Text>
        <Text style={ui.muted}>
          Options are tailored for your {user?.role?.toLowerCase() || 'Awinlink'} account.
        </Text>
      </View>

      {options.map((option) => (
        <Pressable
          accessibilityRole="button"
          disabled={!option.enabled}
          key={option.key}
          onPress={() => {
            setSelected(option.key);
            setMessage('');
            setIsError(false);
          }}
          style={({ pressed }) => [
            styles.option,
            selected === option.key && option.enabled && styles.optionSelected,
            !option.enabled && styles.optionDisabled,
            pressed && option.enabled && styles.optionPressed,
          ]}
        >
          <View style={styles.optionIcon}>
            <Text style={styles.optionIconText}>{option.icon}</Text>
          </View>
          <View style={styles.optionCopy}>
            <Text style={styles.optionTitle}>{option.title}</Text>
            <Text style={styles.optionDescription}>{option.description}</Text>
            {!option.enabled && <Text style={styles.comingSoon}>Purchases are unavailable in this build</Text>}
          </View>
          {option.enabled && <Text style={styles.chevron}>›</Text>}
        </Pressable>
      ))}

      {!!selected && (
        <View style={styles.composer}>
          <Text style={styles.composerTitle}>
            {selected === 'post'
              ? 'Write your post'
              : selected === 'portfolio' || selected === 'achievement'
                ? selected === 'achievement'
                  ? 'Add an achievement'
                  : 'Add a portfolio item'
                : selected === 'competition'
                  ? 'Competition details'
                  : 'Opportunity details'}
          </Text>

          {selected === 'post' && (
            <>
            <FormField
              label="Post"
              multiline
              onChangeText={(value) => updateValue('caption', value)}
              placeholder="Share a moment, an idea, or a milestone..."
              value={values.caption}
            />
            <Pressable accessibilityRole="button" disabled={submitting} onPress={() => void selectPostMedia()} style={ui.primaryButton}><Text style={ui.primaryButtonText}>{postMedia?.name || 'Attach photo or video'}</Text></Pressable>
            {!!postMedia && <Pressable accessibilityRole="button" disabled={submitting} onPress={() => setPostMedia(null)}><Text style={ui.muted}>Remove attachment</Text></Pressable>}
            </>
          )}

          {(selected === 'portfolio' || selected === 'achievement') && (
            <>
              <FormField label="Title" onChangeText={(value) => updateValue('title', value)} placeholder="Give it a name" value={values.title} />
              {selected === 'portfolio' && (
                <ChoiceField label="Type" choices={PORTFOLIO_TYPES.slice(0, 5)} onChange={(value) => updateValue('item_type', value)} value={values.item_type} />
              )}
              <FormField label="Description" multiline onChangeText={(value) => updateValue('description', value)} placeholder="Add some details" value={values.description} />
              <FormField label="Link (optional)" keyboardType="url" onChangeText={(value) => updateValue('link', value)} placeholder="https://" value={values.link} />
              <Text style={styles.note}>You can attach media from your portfolio after adding it.</Text>
            </>
          )}

          {selected === 'opportunity' && (
            <>
              <FormField label="Title" onChangeText={(value) => updateValue('title', value)} placeholder="e.g. Junior developer" value={values.title} />
              <FormField label="Description" multiline onChangeText={(value) => updateValue('description', value)} placeholder="Describe the opportunity" value={values.description} />
              <ChoiceField label="Opportunity type" choices={OPPORTUNITY_TYPES} onChange={(value) => updateValue('opportunity_type', value)} value={values.opportunity_type} />
              {domainLoadStatus === 'loading' ? (
                <ActivityIndicator color={colors.primary} />
              ) : domainLoadStatus === 'error' ? (
                <View style={styles.domainError}>
                  <Text accessibilityRole="alert" style={styles.error}>{domainError}</Text>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => {
                      setDomainError('');
                      setDomainLoadStatus('idle');
                    }}
                  >
                    <Text style={styles.retry}>Retry loading domains</Text>
                  </Pressable>
                </View>
              ) : domains.length ? (
                <ChoiceField
                  label="Ecosystem domain"
                  choices={domains.map((domain) => ({ value: String(domain.id), label: domain.name }))}
                  onChange={(value) => updateValue('domain', value)}
                  value={values.domain}
                />
              ) : (
                <Text style={styles.note}>No domains are available for opportunities yet.</Text>
              )}
              <ChoiceField label="Experience level" choices={EXPERIENCE_LEVELS} onChange={(value) => updateValue('experience_level', value)} value={values.experience_level} />
              <ChoiceField label="Work type" choices={WORK_TYPES} onChange={(value) => updateValue('work_type', value)} value={values.work_type} />
              <FormField label="Location" onChangeText={(value) => updateValue('location', value)} placeholder="City or region" value={values.location} />
              <FormField label="Application deadline (optional)" onChangeText={(value) => updateValue('deadline', value)} placeholder="YYYY-MM-DD" value={values.deadline} />
            </>
          )}

          {selected === 'competition' && (
            <>
              <FormField label="Title" onChangeText={(value) => updateValue('title', value)} placeholder="Competition name" value={values.title} />
              <FormField label="Description" multiline onChangeText={(value) => updateValue('description', value)} placeholder="What is this competition about?" value={values.description} />
              <ChoiceField label="Ecosystem" choices={COMPETITION_CATEGORIES} onChange={(value) => updateValue('category', value)} value={values.category} />
              <FormField label="Discipline" onChangeText={(value) => updateValue('discipline', value)} placeholder="e.g. Basketball, Robotics, Music" value={values.discipline} />
              <FormField label="Registration starts" onChangeText={(value) => updateValue('registration_start', value)} placeholder="YYYY-MM-DD" value={values.registration_start} />
              <FormField label="Registration ends" onChangeText={(value) => updateValue('registration_end', value)} placeholder="YYYY-MM-DD" value={values.registration_end} />
              <FormField label="Competition starts" onChangeText={(value) => updateValue('competition_start', value)} placeholder="YYYY-MM-DD" value={values.competition_start} />
              <FormField label="Competition ends" onChangeText={(value) => updateValue('competition_end', value)} placeholder="YYYY-MM-DD" value={values.competition_end} />
              <FormField label="Location (leave blank for online)" onChangeText={(value) => updateValue('competition_location', value)} placeholder="City or venue" value={values.competition_location} />
              <FormField label="Maximum participants (optional)" keyboardType="numeric" onChangeText={(value) => updateValue('max_participants', value)} placeholder="No limit" value={values.max_participants} />
              <FormField label="Requirements (optional)" multiline onChangeText={(value) => updateValue('requirements', value)} placeholder="Eligibility or entry requirements" value={values.requirements} />
              <FormField label="Prizes (optional)" multiline onChangeText={(value) => updateValue('prizes', value)} placeholder="Describe prizes" value={values.prizes} />
              <FormField label="Rules (optional)" multiline onChangeText={(value) => updateValue('rules', value)} placeholder="Competition rules" value={values.rules} />
            </>
          )}

          {!!message && (
            <Text accessibilityRole="alert" style={[styles.message, isError ? styles.error : styles.success]}>
              {message}
            </Text>
          )}
          <Pressable
            accessibilityRole="button"
            disabled={submitting || (selected === 'opportunity' && domainLoadStatus === 'loading')}
            onPress={() => void submit()}
            style={({ pressed }) => [
              ui.primaryButton,
              (submitting || (selected === 'opportunity' && domainLoadStatus === 'loading')) && styles.disabledButton,
              pressed && styles.optionPressed,
            ]}
          >
            {submitting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={ui.primaryButtonText}>{submitLabel}</Text>
            )}
          </Pressable>
        </View>
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  intro: { gap: 5, marginBottom: 2 },
  introTitle: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  option: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 13,
  },
  optionSelected: { backgroundColor: colors.softBlue, borderColor: '#a9c4ff' },
  optionDisabled: { opacity: 0.66 },
  optionPressed: { opacity: 0.8 },
  optionIcon: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 13, height: 42, justifyContent: 'center', width: 42 },
  optionIconText: { color: colors.primary, fontSize: 20, fontWeight: '700' },
  optionCopy: { flex: 1, gap: 3 },
  optionTitle: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  optionDescription: { color: colors.muted, fontSize: 12, lineHeight: 17 },
  comingSoon: { color: colors.muted, fontSize: 10, fontWeight: '700', marginTop: 2 },
  chevron: { color: colors.primary, fontSize: 27, paddingHorizontal: 3 },
  composer: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 18, borderWidth: 1, gap: 14, padding: 15 },
  composerTitle: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  field: { gap: 7 },
  fieldLabel: { color: colors.ink, fontSize: 12, fontWeight: '700' },
  input: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 12, borderWidth: 1, color: colors.ink, fontSize: 14, minHeight: 46, paddingHorizontal: 12 },
  multiline: { minHeight: 100, padding: 12 },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  choice: { backgroundColor: colors.background, borderColor: colors.border, borderRadius: 18, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 8 },
  choiceSelected: { backgroundColor: colors.softBlue, borderColor: colors.primary },
  choiceText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  choiceTextSelected: { color: colors.primary },
  message: { fontSize: 13, lineHeight: 19 },
  error: { color: colors.danger },
  success: { color: colors.success },
  note: { color: colors.muted, fontSize: 11, lineHeight: 16 },
  domainError: { gap: 7 },
  retry: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  disabledButton: { opacity: 0.55 },
});
