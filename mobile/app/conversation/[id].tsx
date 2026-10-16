import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Linking,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { router, Stack, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as DocumentPicker from 'expo-document-picker';

import { apiRequest } from '@/src/api/client';
import { useAuth } from '@/src/auth/AuthProvider';
import { EmptyState } from '@/src/components/EmptyState';
import { VideoPlayer, VoicePlayer } from '@/src/components/MediaPlayer';
import { VoiceRecorder } from '@/src/components/VoiceRecorder';
import { colors } from '@/src/theme';
import type { Message } from '@/src/types';

export default function ConversationScreen() {
  const { id: routeId, title: routeTitle } = useLocalSearchParams<{
    id: string;
    title?: string;
  }>();
  const { user } = useAuth();
  const conversationId = Number(routeId);
  const title = Array.isArray(routeTitle) ? routeTitle[0] : routeTitle;
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [startingCall, setStartingCall] = useState(false);
  const [error, setError] = useState('');

  const loadMessages = useCallback(async () => {
    if (!Number.isInteger(conversationId) || conversationId < 1) {
      setError('This conversation link is invalid.');
      setLoading(false);
      return;
    }
    setError('');
    try {
      const result = await apiRequest<Message[]>(
        `messaging/conversations/${conversationId}/messages/`,
      );
      setMessages(result);
      await apiRequest(`messaging/conversations/${conversationId}/read-all/`, {
        method: 'POST',
      });
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load this conversation.');
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    void loadMessages();
  }, [loadMessages]);

  const screenTitle = useMemo(() => title || 'Conversation', [title]);

  async function startCall(callType: 'VOICE' | 'VIDEO') {
    if (startingCall) return;
    setStartingCall(true);
    setError('');
    try {
      const call = await apiRequest<{
        id: number;
        participants: { user: { id: number }; status: string }[];
      }>(`messaging/conversations/${conversationId}/calls/start/`, {
        method: 'POST', body: { call_type: callType },
      });
      router.push({ pathname: '/call/[id]', params: {
        id: String(call.id), mode: 'outgoing', callType,
        conversationId: String(conversationId), title: screenTitle,
        participants: JSON.stringify(call.participants),
      } });
    } catch (callError) {
      setError(callError instanceof Error ? callError.message : 'Unable to start this call.');
    } finally {
      setStartingCall(false);
    }
  }

  async function sendMessage() {
    const content = draft.trim();
    if (!content || sending) return;
    setSending(true);
    setError('');
    try {
      const message = await apiRequest<Message>(
        `messaging/conversations/${conversationId}/messages/create/`,
        { method: 'POST', body: { content, message_type: 'TEXT' } },
      );
      setMessages((current) => [...current, message]);
      setDraft('');
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : 'Unable to send this message.');
    } finally {
      setSending(false);
    }
  }

  async function sendAttachment() {
    if (sending) return;
    try {
      const selection = await DocumentPicker.getDocumentAsync({ type: ['image/*', 'video/*', 'audio/*', 'application/*'], copyToCacheDirectory: true });
      if (selection.canceled) return;
      const asset = selection.assets[0];
      if (!asset) return;
      const mime = asset.mimeType || 'application/octet-stream';
      const field = mime.startsWith('image/') ? 'image' : mime.startsWith('video/') ? 'video' : mime.startsWith('audio/') ? 'audio' : 'file';
      const messageType = field.toUpperCase();
      const body = new FormData();
      body.append('message_type', messageType);
      body.append(field, Platform.OS === 'web' && asset.file ? asset.file : { uri: asset.uri, name: asset.name, type: mime } as unknown as Blob);
      setSending(true); setError('');
      const message = await apiRequest<Message>(`messaging/conversations/${conversationId}/messages/create/`, { method: 'POST', body });
      setMessages((current) => [...current, message]);
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : 'Unable to send this attachment.');
    } finally { setSending(false); }
  }

  return (
    <>
      <Stack.Screen
        options={{
          headerShown: true,
          title: screenTitle,
          headerTintColor: colors.primary,
          headerStyle: { backgroundColor: colors.background },
          headerShadowVisible: false,
        }}
      />
      <SafeAreaView edges={['bottom']} style={styles.safeArea}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 88 : 0}
          style={styles.container}
        >
          {loading ? (
            <ActivityIndicator color={colors.primary} style={styles.loader} />
          ) : error && messages.length === 0 ? (
            <View style={styles.errorState}>
              <EmptyState
                title="Conversation unavailable"
                message={error}
                actionLabel="Try again"
                onAction={() => {
                  setLoading(true);
                  void loadMessages();
                }}
              />
            </View>
          ) : (
            <>
              <View style={styles.callActions}>
                <Text style={styles.callLabel}>Start a call</Text>
                <Pressable accessibilityRole="button" disabled={startingCall} onPress={() => void startCall('VOICE')} style={styles.callButton}>
                  <Text style={styles.callButtonText}>{startingCall ? 'Starting…' : 'Audio'}</Text>
                </Pressable>
                <Pressable accessibilityRole="button" disabled={startingCall} onPress={() => void startCall('VIDEO')} style={styles.callButton}>
                  <Text style={styles.callButtonText}>Video</Text>
                </Pressable>
              </View>
              <ScrollView
                contentContainerStyle={styles.messageList}
                keyboardShouldPersistTaps="handled"
                showsVerticalScrollIndicator={false}
              >
                {messages.length === 0 ? (
                  <Text style={styles.emptyText}>No messages yet. Say hello.</Text>
                ) : (
                  messages.map((message) => {
                    const ownMessage = message.sender.id === user?.id;
                    const attachment =
                      message.message_type === 'IMAGE'
                        ? 'Photo'
                        : message.message_type === 'VIDEO'
                          ? 'Video'
                          : message.message_type === 'FILE'
                            ? 'File'
                            : message.message_type === 'AUDIO'
                              ? 'Voice message'
                              : '';
                    return (
                      <View
                        key={message.id}
                        style={[
                          styles.messageBubble,
                          ownMessage ? styles.ownMessage : styles.otherMessage,
                        ]}
                      >
                        {!ownMessage && (
                          <Text style={styles.sender}>
                            {message.sender.first_name || message.sender.username}
                          </Text>
                        )}
                        <Text style={[styles.messageText, ownMessage && styles.ownMessageText]}>
                          {message.content || attachment}
                        </Text>
                        {message.image && <Image accessibilityLabel="Message image attachment" source={{ uri: message.image }} style={styles.attachmentImage} />}
                        {!!message.video && <VideoPlayer uri={message.video} />}
                        {!!message.audio && <VoicePlayer uri={message.audio} />}
                        {!!message.file && <Pressable accessibilityRole="link" onPress={() => void Linking.openURL(message.file!)}><Text style={[styles.attachmentLink, ownMessage && styles.ownMessageText]}>Open file</Text></Pressable>}
                        <Text style={[styles.timestamp, ownMessage && styles.ownTimestamp]}>
                          {new Intl.DateTimeFormat(undefined, {
                            hour: 'numeric',
                            minute: '2-digit',
                          }).format(new Date(message.created_at))}
                        </Text>
                      </View>
                    );
                  })
                )}
              </ScrollView>
              {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
              <VoiceRecorder conversationId={conversationId} disabled={sending} onSent={message => setMessages(current => [...current, message])} />
              <View style={styles.composer}>
                <Pressable accessibilityLabel="Attach a file" accessibilityRole="button" disabled={sending} onPress={() => void sendAttachment()} style={styles.attachButton}><Text style={styles.attachText}>＋</Text></Pressable>
                <TextInput
                  accessibilityLabel="Message"
                  multiline
                  onChangeText={setDraft}
                  placeholder="Write a message..."
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  value={draft}
                />
                <Pressable
                  accessibilityLabel="Send message"
                  accessibilityRole="button"
                  disabled={!draft.trim() || sending}
                  onPress={() => void sendMessage()}
                  style={({ pressed }) => [
                    styles.sendButton,
                    (!draft.trim() || sending) && styles.sendDisabled,
                    pressed && styles.sendPressed,
                  ]}
                >
                  {sending ? (
                    <ActivityIndicator color="#fff" />
                  ) : (
                    <Text style={styles.sendText}>Send</Text>
                  )}
                </Pressable>
              </View>
            </>
          )}
        </KeyboardAvoidingView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  container: { flex: 1 },
  loader: { marginTop: 36 },
  errorState: { flex: 1, justifyContent: 'center', padding: 20 },
  messageList: { flexGrow: 1, gap: 10, justifyContent: 'flex-end', padding: 16 },
  emptyText: { color: colors.muted, fontSize: 13, marginVertical: 20, textAlign: 'center' },
  callActions: { alignItems: 'center', borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth, flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 10 },
  callLabel: { color: colors.muted, flex: 1, fontSize: 12 },
  callButton: { backgroundColor: colors.softBlue, borderRadius: 16, paddingHorizontal: 15, paddingVertical: 8 },
  callButtonText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  messageBubble: { borderRadius: 16, maxWidth: '84%', paddingHorizontal: 13, paddingVertical: 10 },
  ownMessage: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  otherMessage: {
    alignSelf: 'flex-start',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderWidth: 1,
  },
  sender: { color: colors.primary, fontSize: 10, fontWeight: '800', marginBottom: 4 },
  messageText: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  ownMessageText: { color: '#fff' },
  timestamp: { color: colors.muted, fontSize: 10, marginTop: 5, textAlign: 'right' },
  ownTimestamp: { color: '#d7e3ff' },
  composer: {
    alignItems: 'flex-end',
    backgroundColor: colors.surface,
    borderTopColor: colors.border,
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    gap: 9,
    padding: 12,
  },
  attachButton: { alignItems: 'center', backgroundColor: colors.softBlue, borderRadius: 20, height: 42, justifyContent: 'center', width: 42 },
  attachText: { color: colors.primary, fontSize: 23, fontWeight: '600', lineHeight: 27 },
  attachmentImage: { borderRadius: 10, height: 180, marginTop: 7, width: 220 },
  attachmentLink: { color: colors.primary, fontSize: 12, fontWeight: '800', marginTop: 6 },
  input: {
    backgroundColor: '#fbfcfe',
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    color: colors.ink,
    flex: 1,
    maxHeight: 110,
    minHeight: 44,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  sendButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 18,
    justifyContent: 'center',
    minHeight: 44,
    minWidth: 60,
    paddingHorizontal: 12,
  },
  sendDisabled: { opacity: 0.55 },
  sendPressed: { opacity: 0.8 },
  sendText: { color: '#fff', fontSize: 13, fontWeight: '800' },
  error: { color: colors.danger, fontSize: 12, paddingHorizontal: 14, paddingVertical: 6 },
});
