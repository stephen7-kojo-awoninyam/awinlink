import { useCallback, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  RefreshControl,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';

import { useAuth } from '@/src/auth/AuthProvider';
import { apiRequest } from '@/src/api/client';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';
import type { TalentProfile } from '@/src/types';

export default function DiscoverScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [profiles, setProfiles] = useState<TalentProfile[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const loadProfiles = useCallback(async () => {
    setError('');
    try {
      setProfiles(await apiRequest<TalentProfile[]>('talents/'));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load talent profiles.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      void loadProfiles();
    }, [loadProfiles]),
  );

  const filteredProfiles = useMemo(() => {
    const needle = query.trim().replace(/^@/, '').toLocaleLowerCase();
    if (!needle) return profiles;
    return profiles.filter((profile) =>
      [
        profile.user.username,
        profile.user.first_name,
        profile.user.last_name,
        profile.headline,
        profile.talent_area,
        profile.talent_category,
        profile.country,
      ]
        .filter(Boolean)
        .join(' ')
        .toLocaleLowerCase()
        .includes(needle),
    );
  }, [profiles, query]);

  return (
    <Page
      eyebrow="EXPLORE"
      title="Discover"
      refreshControl={
        <RefreshControl
          onRefresh={() => {
            setRefreshing(true);
            void loadProfiles();
          }}
          refreshing={refreshing}
          tintColor={colors.primary}
        />
      }
    >
      <View style={styles.exploreLinks}>
        <Pressable accessibilityRole="button" onPress={() => router.push('/competitions')} style={styles.exploreLink}>
          <Text style={styles.exploreLinkText}>Explore competitions</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => router.push('/events')} style={styles.exploreLink}>
          <Text style={styles.exploreLinkText}>Explore events</Text>
        </Pressable>
      </View>
      {user?.role === 'ATHLETE' && <Pressable accessibilityRole="button" onPress={() => router.push('/event-certificates')} style={styles.organizationLink}><Text style={styles.exploreLinkText}>My event certificates</Text></Pressable>}
      <View style={styles.exploreLinks}>
        <Pressable accessibilityRole="button" onPress={() => router.push('/learning')} style={styles.exploreLink}>
          <Text style={styles.exploreLinkText}>Explore learning</Text>
        </Pressable>
        <Pressable accessibilityRole="button" onPress={() => router.push('/connections')} style={styles.exploreLink}>
          <Text style={styles.exploreLinkText}>Connection requests</Text>
        </Pressable>
      </View>
      <Pressable accessibilityRole="button" onPress={() => router.push('/organizations')} style={styles.organizationLink}>
        <Text style={styles.exploreLinkText}>Browse organizations</Text>
      </Pressable>
      {(user?.role === 'SCOUT' || user?.role === 'COACH') && (
        <Pressable accessibilityRole="button" onPress={() => router.push('/specialist')} style={styles.organizationLink}>
          <Text style={styles.exploreLinkText}>{user.role === 'SCOUT' ? 'Scout workspace' : 'Coach workspace'}</Text>
        </Pressable>
      )}
      {(user?.role === 'COACH' || user?.role === 'ADMIN') && (
        <Pressable accessibilityRole="button" onPress={() => router.push('/competition-workspace')} style={styles.organizationLink}>
          <Text style={styles.exploreLinkText}>{user.role === 'ADMIN' ? 'Competition moderation' : 'Competition judging'}</Text>
        </Pressable>
      )}
      {user?.role === 'ORGANIZATION' && (
        <View style={styles.exploreLinks}>
          <Pressable accessibilityRole="button" onPress={() => router.push('/shortlists')} style={styles.exploreLink}>
            <Text style={styles.exploreLinkText}>Talent shortlist</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/recruitment')} style={styles.exploreLink}>
            <Text style={styles.exploreLinkText}>Recruitment pipeline</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/competition-management')} style={styles.exploreLink}>
            <Text style={styles.exploreLinkText}>Manage competitions</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => router.push('/applications')} style={styles.exploreLink}>
            <Text style={styles.exploreLinkText}>Review applications</Text>
          </Pressable>
        </View>
      )}
      <TextInput
        accessibilityLabel="Search talent, username, or ecosystem"
        autoCapitalize="none"
        onChangeText={setQuery}
        placeholder="Search people or ecosystems"
        placeholderTextColor={colors.muted}
        returnKeyType="search"
        style={styles.search}
        value={query}
      />
      <Text style={styles.hint}>
        Find talent across ecosystems. Profile visibility is enforced by Django.
      </Text>

      {loading ? (
        <ActivityIndicator color={colors.primary} style={styles.loader} />
      ) : error ? (
        <EmptyState
          title="Discovery unavailable"
          message={error}
          actionLabel="Try again"
          onAction={() => void loadProfiles()}
        />
      ) : filteredProfiles.length === 0 ? (
        <EmptyState title="No matches yet" message="Try another name, username, or ecosystem." />
      ) : (
        filteredProfiles.map((profile) => {
          const name =
            [profile.user.first_name, profile.user.last_name].filter(Boolean).join(' ') ||
            profile.user.username;
          const category = profile.talent_area || profile.talent_category || 'Awinlink talent';
          return (
            <Pressable
              accessibilityLabel={`View ${name}'s profile`}
              accessibilityRole="button"
              key={profile.id}
              onPress={() =>
                router.push({
                  pathname: '/talent/[id]',
                  params: { id: String(profile.id) },
                })
              }
              style={({ pressed }) => [styles.profileCard, pressed && styles.profilePressed]}
            >
              {profile.user.profile_picture ? (
                <Image source={{ uri: profile.user.profile_picture }} style={styles.avatar} />
              ) : (
                <View style={styles.avatarFallback}>
                  <Text style={styles.avatarInitial}>{name.charAt(0).toUpperCase()}</Text>
                </View>
              )}
              <View style={styles.profileInfo}>
                <Text numberOfLines={1} style={styles.profileName}>
                  {name}
                </Text>
                <Text numberOfLines={1} style={styles.username}>
                  @{profile.user.username}
                </Text>
                <Text numberOfLines={2} style={styles.category}>
                  {[category, profile.country || profile.user.country].filter(Boolean).join(' · ')}
                </Text>
              </View>
              {profile.user.id === user?.id && <Text style={styles.youBadge}>YOU</Text>}
            </Pressable>
          );
        })
      )}
    </Page>
  );
}

const styles = StyleSheet.create({
  exploreLinks: { flexDirection: "row", gap: 9 },
  exploreLink: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, flex: 1, padding: 12 },
  exploreLinkText: { color: colors.primary, fontSize: 12, fontWeight: "800" },
  organizationLink: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 12, borderWidth: 1, padding: 12 },
  search: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 13,
    borderWidth: 1,
    color: colors.ink,
    fontSize: 14,
    minHeight: 50,
    paddingHorizontal: 15,
  },
  hint: { color: colors.muted, fontSize: 12, lineHeight: 18, marginTop: -7 },
  loader: { marginTop: 28 },
  profileCard: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 17,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    padding: 13,
  },
  avatar: { backgroundColor: colors.softBlue, borderRadius: 25, height: 50, width: 50 },
  avatarFallback: {
    alignItems: 'center',
    backgroundColor: colors.softBlue,
    borderRadius: 25,
    height: 50,
    justifyContent: 'center',
    width: 50,
  },
  avatarInitial: { color: colors.primary, fontSize: 18, fontWeight: '800' },
  profileInfo: { flex: 1, gap: 3 },
  profileName: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  username: { color: colors.primary, fontSize: 12, fontWeight: '600' },
  category: { color: colors.muted, fontSize: 12, marginTop: 2 },
  youBadge: { color: colors.primary, fontSize: 10, fontWeight: '800' },
  profilePressed: { opacity: 0.78 },
});
