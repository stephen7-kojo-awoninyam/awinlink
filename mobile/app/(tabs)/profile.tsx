import { useState } from 'react';
import { Image, Pressable, StyleSheet, Text, View } from 'react-native';
import { Redirect, useRouter } from 'expo-router';

import { useAuth } from '@/src/auth/AuthProvider';
import { Page, ui } from '@/src/components/Page';
import { colors } from '@/src/theme';

const ROLE_LABELS: Record<string, string> = {
  ATHLETE: 'Talent',
  ORGANIZATION: 'Organization',
  SCOUT: 'Scout',
  COACH: 'Coach',
  ADMIN: 'Administrator',
};

export default function ProfileScreen() {
  const { user, signOut } = useAuth();
  const router = useRouter();
  const [signingOut, setSigningOut] = useState(false);
  if (!user) return <Redirect href="/login" />;
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username;

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await signOut();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <Page eyebrow="YOUR ACCOUNT" title="Profile">
      <View style={styles.profileCard}>
        {user.profile_picture ? (
          <Image source={{ uri: user.profile_picture }} style={styles.avatar} />
        ) : (
          <View style={styles.avatarFallback}>
            <Text style={styles.avatarInitial}>{name.charAt(0).toUpperCase()}</Text>
          </View>
        )}
        <Text style={styles.name}>{name}</Text>
        <Text style={styles.username}>@{user.username}</Text>
        <Text style={styles.role}>{ROLE_LABELS[user.role] || user.role}</Text>
      </View>

      <View style={styles.details}>
        <Detail label="Email" value={user.email || 'Not provided'} />
        <Detail label="Country" value={user.country || 'Not set'} />
        <Detail label="Ecosystem" value="Managed by your Awinlink profile" />
      </View>

      <Text style={styles.note}>
        Profile editing and ecosystem setup currently use the Awinlink web onboarding flow.
      </Text>

      {(user.role === 'ATHLETE' || user.role === 'ORGANIZATION') && (
        <Pressable accessibilityRole="button" onPress={() => router.push('/profile-edit')}
          style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
          <Text style={ui.primaryButtonText}>Edit profile</Text>
        </Pressable>
      )}
      {user.role === 'ATHLETE' && (
        <Pressable accessibilityRole="button" onPress={() => router.push('/portfolio')}
          style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
          <Text style={ui.primaryButtonText}>My portfolio</Text>
        </Pressable>
      )}
      {user.role === 'SCOUT' || user.role === 'COACH' ? (
        <Pressable accessibilityRole="button" onPress={() => router.push('/specialist')}
          style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
          <Text style={ui.primaryButtonText}>{user.role === 'SCOUT' ? 'Open scout workspace' : 'Open coach workspace'}</Text>
        </Pressable>
      ) : null}
      {user.role === 'ORGANIZATION' && (
        <>
          <Pressable accessibilityRole="button" onPress={() => router.push('/shortlists')}
            style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
            <Text style={ui.primaryButtonText}>Manage talent shortlist</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/recruitment')}
            style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
            <Text style={ui.primaryButtonText}>Recruitment pipeline</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/competition-management')}
            style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
            <Text style={ui.primaryButtonText}>Manage competitions</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/applications')}
            style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
            <Text style={ui.primaryButtonText}>Review applications</Text>
          </Pressable>
        </>
      )}
      {(user.role === 'ADMIN' || user.role === 'COACH') && (
        <Pressable accessibilityRole="button" onPress={() => router.push('/competition-workspace')}
          style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}>
          <Text style={ui.primaryButtonText}>{user.role === 'ADMIN' ? 'Competition moderation' : 'Competition judging'}</Text>
        </Pressable>
      )}
      <Pressable
        accessibilityRole="button"
        onPress={() => router.push('/messages')}
        style={({ pressed }) => [ui.primaryButton, styles.messages, pressed && styles.pressed]}
      >
        <Text style={ui.primaryButtonText}>Open messages</Text>
      </Pressable>

      <Pressable
        accessibilityRole="button"
        disabled={signingOut}
        onPress={() => void handleSignOut()}
        style={({ pressed }) => [ui.primaryButton, styles.signOut, pressed && styles.pressed]}
      >
        <Text style={styles.signOutText}>{signingOut ? 'Signing out…' : 'Sign out'}</Text>
      </Pressable>
    </Page>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.detail}>
      <Text style={styles.detailLabel}>{label}</Text>
      <Text style={styles.detailValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  profileCard: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 20,
    borderWidth: 1,
    gap: 8,
    padding: 23,
  },
  avatar: { backgroundColor: colors.softBlue, borderRadius: 42, height: 84, width: 84 },
  avatarFallback: {
    alignItems: 'center',
    backgroundColor: colors.softBlue,
    borderRadius: 42,
    height: 84,
    justifyContent: 'center',
    width: 84,
  },
  avatarInitial: { color: colors.primary, fontSize: 30, fontWeight: '800' },
  name: { color: colors.ink, fontSize: 20, fontWeight: '800', marginTop: 6 },
  username: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  role: {
    backgroundColor: colors.softBlue,
    borderRadius: 20,
    color: colors.primary,
    fontSize: 11,
    fontWeight: '800',
    marginTop: 4,
    overflow: 'hidden',
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  details: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 17,
    borderWidth: 1,
    paddingHorizontal: 15,
  },
  detail: { borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth, gap: 4, paddingVertical: 13 },
  detailLabel: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  detailValue: { color: colors.ink, fontSize: 13, fontWeight: '600' },
  note: { color: colors.muted, fontSize: 12, lineHeight: 18 },
  messages: { backgroundColor: colors.primary },
  signOut: { backgroundColor: '#fff', borderColor: '#f1c9c5', borderWidth: 1 },
  signOutText: { color: colors.danger, fontSize: 14, fontWeight: '800' },
  pressed: { opacity: 0.82 },
});
