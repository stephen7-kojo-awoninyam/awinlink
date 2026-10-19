import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useRouter } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page, ui } from '@/src/components/Page';
import { SafetyActions } from '@/src/components/SafetyActions';
import { colors } from '@/src/theme';
import type { Connection, TalentProfile } from '@/src/types';

type Follow = {
  following_id: number;
};

type RelationshipStatus = 'none' | 'pending' | 'connected' | 'incoming';
type PortfolioItem = { id: number; title: string; description: string; item_type: string; image: string | null; file: string | null; link: string };

export default function TalentProfileScreen() {
  const { id: routeId } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const router = useRouter();
  const talentId = Number(routeId);
  const [profile, setProfile] = useState<TalentProfile | null>(null);
  const [portfolio, setPortfolio] = useState<PortfolioItem[]>([]);
  const [relationship, setRelationship] = useState<RelationshipStatus>('none');
  const [isFollowing, setIsFollowing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const dataRevision = useRef(0);
  const loadGeneration = useRef(0);
  const viewedTalentId = useRef<number | null>(null);
  const relationshipMutation = useRef(false);
  viewedTalentId.current = Number.isInteger(talentId) ? talentId : null;

  const loadProfile = useCallback(async () => {
    if (!Number.isInteger(talentId) || talentId < 1) {
      setError('This profile link is invalid.');
      setLoading(false);
      setRefreshing(false);
      return;
    }

    const revision = dataRevision.current;
    const generation = ++loadGeneration.current;
    setError('');
    try {
      const [talent, following, connections, outgoing, incoming, portfolioItems] = await Promise.all([
        apiRequest<TalentProfile>(`talents/${talentId}/`),
        apiRequest<Follow[]>('follows/following/'),
        apiRequest<Connection[]>('connections/'),
        apiRequest<Connection[]>('connections/outgoing/'),
        apiRequest<Connection[]>('connections/incoming/'),
        apiRequest<PortfolioItem[]>(`portfolio/talent/${talentId}/`),
      ]);
      if (revision !== dataRevision.current || generation !== loadGeneration.current) return;
      setProfile(talent);
      setPortfolio(portfolioItems);
      const targetUserId = talent.user.id;
      setIsFollowing(following.some((item) => item.following_id === targetUserId));
      if (connections.some((item) => item.sender_id === targetUserId || item.receiver_id === targetUserId)) {
        setRelationship('connected');
      } else if (incoming.some((item) => item.sender_id === targetUserId)) {
        setRelationship('incoming');
      } else if (outgoing.some((item) => item.receiver_id === targetUserId)) {
        setRelationship('pending');
      } else {
        setRelationship('none');
      }
    } catch (loadError) {
      if (revision === dataRevision.current && generation === loadGeneration.current) {
        setError(loadError instanceof Error ? loadError.message : 'Unable to load this profile.');
      }
    } finally {
      if (generation === loadGeneration.current) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [talentId]);

  useFocusEffect(useCallback(() => {
    void loadProfile();
    return () => { loadGeneration.current += 1; };
  }, [loadProfile]));

  useEffect(() => {
    if (user?.role === 'SCOUT' || user?.role === 'COACH') {
      const prefix = user.role === 'SCOUT' ? 'scouts' : 'coaches';
      void apiRequest(`${prefix}/talents/${talentId}/view/`, { method: 'POST' }).catch(() => undefined);
    }
  }, [loadProfile, talentId, user?.role]);

  async function addToShortlist() {
    if (!profile) return;
    setWorking(true);
    setActionError('');
    try {
      await apiRequest('shortlists/create/', { method: 'POST', body: { talent: profile.id } });
      setActionError('Talent added to your shortlist.');
    } catch (shortlistError) {
      setActionError(shortlistError instanceof Error ? shortlistError.message : 'Unable to add talent to shortlist.');
    } finally {
      setWorking(false);
    }
  }

  async function toggleFollow() {
    if (!profile || profile.id !== talentId || working || relationshipMutation.current) return;
    relationshipMutation.current = true;
    const wasFollowing = isFollowing;
    const targetId = profile.id;
    const userId = profile.user.id;
    setWorking(true);
    setActionError('');
    try {
      let result: { followers_count: number; following_count: number };
      if (wasFollowing) {
        result = await apiRequest(`follows/${userId}/remove/`, { method: 'DELETE' });
      } else {
        result = await apiRequest('follows/create/', {
          method: 'POST',
          body: { user_id: userId },
        });
      }
      if (viewedTalentId.current === targetId) {
        dataRevision.current += 1;
        setIsFollowing(!wasFollowing);
        setProfile((current) => current?.id === targetId
          ? { ...current, followers_count: result.followers_count, following_count: result.following_count }
          : current);
      }
    } catch (followError) {
      setActionError(followError instanceof Error ? followError.message : 'Unable to update follow.');
    } finally {
      relationshipMutation.current = false;
      setWorking(false);
    }
  }

  async function sendConnectionRequest() {
    if (!profile || profile.id !== talentId || working || relationshipMutation.current || relationship !== 'none') return;
    relationshipMutation.current = true;
    const targetId = profile.id;
    setWorking(true);
    setActionError('');
    try {
      const connection = await apiRequest<Connection>('connections/create/', {
        method: 'POST',
        body: { receiver: profile.user.id },
      });
      if (viewedTalentId.current === targetId) {
        dataRevision.current += 1;
        setRelationship(connection.status === 'ACCEPTED' ? 'connected' : 'pending');
      }
    } catch (connectionError) {
      if (viewedTalentId.current !== targetId) return;
      await loadProfile();
      setActionError(
        connectionError instanceof Error
          ? connectionError.message
          : 'Unable to send a connection request.',
      );
    } finally {
      relationshipMutation.current = false;
      setWorking(false);
    }
  }

  async function openConversation() {
    if (!profile) return;
    setWorking(true);
    setActionError('');
    try {
      const conversation = await apiRequest<{ id: number }>(
        'messaging/conversations/create/',
        { method: 'POST', body: { user_ids: [profile.user.id] } },
      );
      router.push({
        pathname: '/conversation/[id]',
        params: { id: String(conversation.id), title: name },
      });
    } catch (messageError) {
      setActionError(
        messageError instanceof Error ? messageError.message : 'Unable to open this conversation.',
      );
    } finally {
      setWorking(false);
    }
  }

  const name = profile
    ? [profile.user.first_name, profile.user.last_name].filter(Boolean).join(' ') ||
      profile.user.username
    : '';
  const isOwnProfile = profile?.user.id === user?.id;

  return (
    <>
      <Stack.Screen
        options={{
          headerShown: true,
          title: name || 'Talent profile',
          headerTintColor: colors.primary,
          headerStyle: { backgroundColor: colors.background },
          headerShadowVisible: false,
        }}
      />
      <Page
        eyebrow="AWINLINK TALENT"
        title={loading ? 'Profile' : name || 'Profile'}
        refreshControl={
          <RefreshControl
            onRefresh={() => {
              setRefreshing(true);
              void loadProfile();
            }}
            refreshing={refreshing}
            tintColor={colors.primary}
          />
        }
      >
        {loading ? (
          <ActivityIndicator color={colors.primary} style={styles.loader} />
        ) : error ? (
          <EmptyState
            title="Profile unavailable"
            message={error}
            actionLabel="Try again"
            onAction={() => {
              setLoading(true);
              void loadProfile();
            }}
          />
        ) : profile ? (
          <>
            <View style={styles.profileCard}>
              {profile.profile_photo || profile.user.profile_picture ? (
                <Image
                  source={{ uri: profile.profile_photo || profile.user.profile_picture || '' }}
                  style={styles.avatar}
                />
              ) : (
                <View style={styles.avatarFallback}>
                  <Text style={styles.avatarInitial}>{name.charAt(0).toUpperCase()}</Text>
                </View>
              )}
              <Text style={styles.name}>{name}</Text>
              <Text style={styles.username}>@{profile.user.username}</Text>
              <SafetyActions userId={profile.user.id} onBlocked={() => router.replace('/(tabs)/discover')} />
              <Text style={styles.headline}>
                {profile.headline || profile.talent_category || 'Awinlink talent'}
              </Text>
              {!!profile.talent_area && <Text style={styles.headline}>{profile.talent_area}</Text>}
              <Text style={styles.location}>
                {[profile.city, profile.country || profile.user.country].filter(Boolean).join(', ') ||
                  'Location not set'}
              </Text>
              <Text style={styles.followers}>
                {profile.followers_count ?? 0} followers · {profile.following_count ?? 0} following
              </Text>
              {profile.user.id === user?.id && <Text style={styles.youBadge}>YOUR PROFILE</Text>}
            </View>

            {!isOwnProfile && (
              <>
                <View style={styles.actions}>
                  <Pressable
                    accessibilityRole="button"
                    disabled={working}
                    onPress={() => void toggleFollow()}
                    style={({ pressed }) => [
                      ui.primaryButton,
                      styles.actionButton,
                      isFollowing && styles.secondaryButton,
                      pressed && styles.pressed,
                    ]}
                  >
                    {working ? (
                      <ActivityIndicator color={isFollowing ? colors.primary : '#fff'} />
                    ) : (
                      <Text
                        style={[
                          ui.primaryButtonText,
                          isFollowing && styles.secondaryButtonText,
                        ]}
                      >
                        {isFollowing ? 'Following' : 'Follow'}
                      </Text>
                    )}
                  </Pressable>
                  <Pressable
                    accessibilityRole="button"
                    disabled={working || relationship === 'pending' || relationship === 'connected'}
                    onPress={() => relationship === 'incoming' ? router.push('/connections') : void sendConnectionRequest()}
                    style={({ pressed }) => [
                      styles.connectionButton,
                      (working || relationship === 'pending' || relationship === 'connected') && styles.connectionButtonDisabled,
                      pressed && styles.pressed,
                    ]}
                  >
                    <Text style={styles.connectionButtonText}>
                      {relationship === 'connected'
                        ? 'Connected'
                        : relationship === 'pending'
                          ? 'Request sent'
                          : relationship === 'incoming'
                            ? 'Request received'
                            : 'Connect'}
                    </Text>
                  </Pressable>
                </View>
                <Pressable
                  accessibilityRole="button"
                  disabled={working}
                  onPress={() => void openConversation()}
                  style={({ pressed }) => [
                    styles.messageButton,
                    working && styles.connectionButtonDisabled,
                    pressed && styles.pressed,
                  ]}
                >
                  <Text style={styles.messageButtonText}>Message</Text>
                </Pressable>
              </>
            )}

            {user?.role === 'ORGANIZATION' && !isOwnProfile && (
              <View style={styles.actions}>
                <Pressable accessibilityRole="button" disabled={working} onPress={() => void addToShortlist()} style={[ui.primaryButton, styles.actionButton]}>
                  <Text style={ui.primaryButtonText}>{working ? 'Working...' : 'Add to shortlist'}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" disabled={working} onPress={() => router.push({ pathname: '/recruitment', params: { talentId: String(profile.id) } })} style={styles.connectionButton}>
                  <Text style={styles.connectionButtonText}>Add to pipeline</Text>
                </Pressable>
              </View>
            )}

            {!!actionError && (
              <Text accessibilityRole="alert" style={styles.error}>
                {actionError}
              </Text>
            )}

            {!!profile.biography && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>About</Text>
                <Text style={styles.body}>{profile.biography}</Text>
              </View>
            )}
            {!!profile.skills?.length && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Skills</Text>
                <Text style={styles.body}>{profile.skills.join(' · ')}</Text>
              </View>
            )}
            {!!profile.domains?.length && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Ecosystem</Text>
                <Text style={styles.body}>{profile.domains.join(' · ')}</Text>
              </View>
            )}
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Portfolio</Text>
              {portfolio.length === 0 ? <Text style={styles.body}>No public portfolio items yet.</Text> : portfolio.map((item) => (
                <View key={item.id} style={styles.portfolioItem}>
                  <Text style={styles.portfolioTitle}>{item.title}</Text>
                  <Text style={styles.body}>{item.description}</Text>
                  {!!item.link && <Text selectable style={styles.link}>{item.link}</Text>}
                  {!!item.image && <Image source={{ uri: item.image }} style={styles.portfolioImage} />}
                  {!!item.file && <Text selectable style={styles.link}>{item.file}</Text>}
                </View>
              ))}
            </View>
          </>
        ) : null}
      </Page>
    </>
  );
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  profileCard: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 20,
    borderWidth: 1,
    gap: 7,
    padding: 22,
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
  name: { color: colors.ink, fontSize: 20, fontWeight: '800', marginTop: 5, textAlign: 'center' },
  username: { color: colors.primary, fontSize: 13, fontWeight: '700' },
  headline: { color: colors.ink, fontSize: 14, fontWeight: '600', textAlign: 'center' },
  location: { color: colors.muted, fontSize: 12, textAlign: 'center' },
  followers: { color: colors.muted, fontSize: 12, fontWeight: '700', marginTop: 3 },
  youBadge: {
    backgroundColor: colors.softBlue,
    borderRadius: 20,
    color: colors.primary,
    fontSize: 10,
    fontWeight: '800',
    marginTop: 4,
    overflow: 'hidden',
    paddingHorizontal: 11,
    paddingVertical: 6,
  },
  actions: { flexDirection: 'row', gap: 10 },
  actionButton: { flex: 1 },
  secondaryButton: { backgroundColor: colors.surface, borderColor: colors.primary, borderWidth: 1 },
  secondaryButtonText: { color: colors.primary },
  connectionButton: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 12,
    borderWidth: 1,
    flex: 1,
    justifyContent: 'center',
    minHeight: 48,
  },
  connectionButtonDisabled: { opacity: 0.65 },
  connectionButtonText: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  messageButton: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.primary,
    borderRadius: 12,
    borderWidth: 1,
    justifyContent: 'center',
    minHeight: 46,
  },
  messageButtonText: { color: colors.primary, fontSize: 14, fontWeight: '800' },
  pressed: { opacity: 0.8 },
  error: { color: colors.danger, fontSize: 13, lineHeight: 19 },
  section: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
    borderWidth: 1,
    gap: 8,
    padding: 16,
  },
  sectionTitle: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21 },
  portfolioItem: { borderTopColor: colors.border, borderTopWidth: StyleSheet.hairlineWidth, gap: 6, paddingTop: 10 },
  portfolioTitle: { color: colors.ink, fontSize: 14, fontWeight: '700' },
  link: { color: colors.primary, fontSize: 12 },
  portfolioImage: { borderRadius: 10, height: 190, width: '100%' },
});
