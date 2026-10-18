import { useCallback, useState } from 'react';
import { ActivityIndicator, Image, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from 'react-native';
import { Stack, useFocusEffect, useRouter } from 'expo-router';

import { useMessaging } from '@/src/messaging/useMessaging';
import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';
import type { Conversation, MessagingUser } from '@/src/types';

type Connection = { id: number; sender_id: number; sender_username: string; sender_name: string; receiver_id: number; receiver_username: string; receiver_name: string; status: string };

function displayName(user: MessagingUser) {
  return [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username;
}

export default function MessagesScreen() {
  const { user } = useAuth();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [contacts, setContacts] = useState<Connection[]>([]);
  const [selectedContacts, setSelectedContacts] = useState<number[]>([]);
  const [groupName, setGroupName] = useState('');
  const [showGroupForm, setShowGroupForm] = useState(false);
  const [creatingGroup, setCreatingGroup] = useState(false);

  const loadConversations = useCallback(async () => {
    setError('');
    try {
      setConversations(
        await apiRequest<Conversation[]>('messaging/conversations/'),
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load messages.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useMessaging(loadConversations);

  useFocusEffect(
    useCallback(() => {
      void loadConversations();
    }, [loadConversations]),
  );

  async function startGroup() {
    setError('');
    try {
      setContacts(await apiRequest<Connection[]>('connections/'));
      setSelectedContacts([]);
      setShowGroupForm(true);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load your connections.');
    }
  }

  async function createGroup() {
    if (!selectedContacts.length || !groupName.trim() || creatingGroup) return;
    setCreatingGroup(true);
    setError('');
    try {
      const conversation = await apiRequest<Conversation>('messaging/conversations/create/', {
        method: 'POST',
        body: { is_group: true, name: groupName.trim(), user_ids: selectedContacts },
      });
      setShowGroupForm(false);
      setGroupName('');
      setSelectedContacts([]);
      await loadConversations();
      router.push({ pathname: '/conversation/[id]', params: { id: String(conversation.id), title: conversation.name || 'Group conversation' } });
    } catch (createError) {
      setError(createError instanceof Error ? createError.message : 'Unable to create this group.');
    } finally {
      setCreatingGroup(false);
    }
  }

  return (
    <>
      <Stack.Screen
        options={{
          headerShown: true,
          title: 'Messages',
          headerTintColor: colors.primary,
          headerStyle: { backgroundColor: colors.background },
          headerShadowVisible: false,
        }}
      />
      <Page
        eyebrow="YOUR NETWORK"
        title="Messages"
        refreshControl={
          <RefreshControl
            onRefresh={() => {
              setRefreshing(true);
              void loadConversations();
            }}
            refreshing={refreshing}
            tintColor={colors.primary}
          />
        }
      >
        <Pressable accessibilityRole="button" onPress={() => void startGroup()} style={styles.newGroupButton}>
          <Text style={styles.newGroupText}>Create group conversation</Text>
        </Pressable>
        {showGroupForm && (
          <View style={styles.groupForm}>
            <Text style={styles.groupHeading}>Choose accepted connections</Text>
            <TextInput accessibilityLabel="Group name" onChangeText={setGroupName} placeholder="Group name (required)" placeholderTextColor={colors.muted} style={styles.groupInput} value={groupName} />
            {contacts.length === 0 ? <Text style={styles.groupHint}>Connect with people before creating a group.</Text> : contacts.map((connection) => {
              const contactId = connection.sender_id === user?.id ? connection.receiver_id : connection.sender_id;
              const contactName = connection.sender_id === user?.id ? connection.receiver_name || connection.receiver_username : connection.sender_name || connection.sender_username;
              const selected = selectedContacts.includes(contactId);
              return <Pressable key={connection.id} accessibilityRole="checkbox" accessibilityState={{ checked: selected }} onPress={() => setSelectedContacts((current) => selected ? current.filter((id) => id !== contactId) : [...current, contactId])} style={styles.contactRow}>
                <Text style={styles.contactName}>{selected ? '✓  ' : '○  '}{contactName}</Text>
              </Pressable>;
            })}
            <View style={styles.groupActions}>
              <Pressable onPress={() => setShowGroupForm(false)} style={styles.groupCancel}><Text style={styles.groupCancelText}>Cancel</Text></Pressable>
              <Pressable disabled={!selectedContacts.length || !groupName.trim() || creatingGroup} onPress={() => void createGroup()} style={[styles.groupCreate, (!selectedContacts.length || !groupName.trim() || creatingGroup) && styles.disabled]}><Text style={styles.groupCreateText}>{creatingGroup ? 'Creating...' : 'Create group'}</Text></Pressable>
            </View>
          </View>
        )}
        {loading ? (
          <ActivityIndicator color={colors.primary} style={styles.loader} />
        ) : error ? (
          <EmptyState
            title="Messages unavailable"
            message={error}
            actionLabel="Try again"
            onAction={() => {
              setLoading(true);
              void loadConversations();
            }}
          />
        ) : conversations.length === 0 ? (
          <EmptyState
            title="Start a conversation"
            message="Open a talent profile and choose Message to start chatting."
            actionLabel="Discover people"
            onAction={() => router.navigate('/(tabs)/discover')}
          />
        ) : (
          conversations.map((conversation) => {
            const otherParticipants = conversation.participants
              .map((participant) => participant.user)
              .filter((participant) => participant.id !== user?.id);
            const title = conversation.is_group
              ? conversation.name || 'Group conversation'
              : otherParticipants[0]
                ? displayName(otherParticipants[0])
                : 'Conversation';
            const lastMessage = conversation.last_message;
            const preview = lastMessage
              ? lastMessage.content ||
                (lastMessage.message_type === 'IMAGE'
                  ? 'Photo'
                  : lastMessage.message_type === 'VIDEO'
                    ? 'Video'
                    : lastMessage.message_type === 'FILE'
                      ? 'File'
                      : 'Attachment')
              : 'No messages yet. Say hello.';
            const hasUnread =
              (conversation.unread_count ?? 0) > 0;

            return (
              <Pressable
                accessibilityRole="button"
                key={conversation.id}
                onPress={() =>
                  router.push({
                    pathname: '/conversation/[id]',
                    params: { id: String(conversation.id), title },
                  })
                }
                style={({ pressed }) => [styles.conversation, pressed && styles.pressed]}
              >
                {conversation.is_group && conversation.name ? (
                  <View style={styles.avatarFallback}>
                    <Text style={styles.avatarInitial}>{title.charAt(0).toUpperCase()}</Text>
                  </View>
                ) : otherParticipants[0]?.profile_picture ? (
                  <Image source={{ uri: otherParticipants[0].profile_picture }} style={styles.avatar} />
                ) : (
                  <View style={styles.avatarFallback}>
                    <Text style={styles.avatarInitial}>{title.charAt(0).toUpperCase()}</Text>
                  </View>
                )}
                <View style={styles.copy}>
                  <Text numberOfLines={1} style={styles.title}>{title}</Text>
                  <Text numberOfLines={1} style={styles.preview}>{preview}</Text>
                </View>
                {hasUnread && <View accessibilityLabel="Unread message" style={styles.unreadDot} />}
              </Pressable>
            );
          })
        )}
      </Page>
    </>
  );
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  newGroupButton: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 12, padding: 12 },
  newGroupText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  groupForm: { backgroundColor: colors.surface, borderColor: colors.border, borderRadius: 15, borderWidth: 1, gap: 8, padding: 13 },
  groupHeading: { color: colors.ink, fontSize: 13, fontWeight: '800' },
  groupInput: { backgroundColor: '#fbfcfe', borderColor: colors.border, borderRadius: 10, borderWidth: 1, color: colors.ink, minHeight: 43, paddingHorizontal: 11 },
  groupHint: { color: colors.muted, fontSize: 11 },
  contactRow: { borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth, paddingVertical: 8 },
  contactName: { color: colors.ink, fontSize: 12, fontWeight: '600' },
  groupActions: { flexDirection: 'row', gap: 8, marginTop: 3 },
  groupCancel: { alignItems: 'center', backgroundColor: colors.background, borderRadius: 9, flex: 1, padding: 10 },
  groupCancelText: { color: colors.muted, fontSize: 11, fontWeight: '800' },
  groupCreate: { alignItems: 'center', backgroundColor: colors.primary, borderRadius: 9, flex: 1, padding: 10 },
  groupCreateText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  disabled: { opacity: 0.55 },
  conversation: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 16,
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
  copy: { flex: 1, gap: 4 },
  title: { color: colors.ink, fontSize: 14, fontWeight: '800' },
  preview: { color: colors.muted, fontSize: 12 },
  unreadDot: { backgroundColor: colors.primary, borderRadius: 5, height: 9, width: 9 },
  pressed: { opacity: 0.8 },
});
