import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect } from 'expo-router';

import { apiRequest } from '@/src/api/client';
import type { AppNotification } from '@/src/types';
import { EmptyState } from '@/src/components/EmptyState';
import { Page } from '@/src/components/Page';
import { colors } from '@/src/theme';

export default function AlertsScreen() {
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');

  const loadNotifications = useCallback(async () => {
    setError('');
    try {
      setNotifications(await apiRequest<AppNotification[]>('notifications/'));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load alerts.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(useCallback(() => { void loadNotifications(); }, [loadNotifications]));

  async function markRead(id: number) {
    setWorking(true);
    setActionError('');
    try {
      await apiRequest(`notifications/${id}/read/`, { method: 'POST' });
      setNotifications((current) => current.map((item) => item.id === id ? { ...item, is_read: true } : item));
    } catch (readError) {
      setActionError(readError instanceof Error ? readError.message : 'Unable to update this alert.');
    } finally {
      setWorking(false);
    }
  }

  async function markAllRead() {
    setWorking(true);
    setActionError('');
    try {
      await apiRequest('notifications/read-all/', { method: 'POST' });
      setNotifications((current) => current.map((item) => ({ ...item, is_read: true })));
    } catch (readError) {
      setActionError(readError instanceof Error ? readError.message : 'Unable to update alerts.');
    } finally {
      setWorking(false);
    }
  }

  const hasUnread = notifications.some((notification) => !notification.is_read);

  return (
    <Page eyebrow="STAY IN THE LOOP" title="Alerts"
      refreshControl={<RefreshControl onRefresh={() => { setRefreshing(true); void loadNotifications(); }}
        refreshing={refreshing} tintColor={colors.primary} />}>
      {hasUnread && !loading && !error && (
        <Pressable accessibilityRole="button" disabled={working} onPress={() => void markAllRead()}
          style={[styles.markAll, working && styles.disabled]}>
          <Text style={styles.markAllText}>{working ? 'Updating...' : 'Mark all as read'}</Text>
        </Pressable>
      )}
      {!!actionError && <Text accessibilityRole="alert" style={styles.error}>{actionError}</Text>}
      {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> :
        error ? <EmptyState title="Alerts unavailable" message={error} actionLabel="Try again"
          onAction={() => void loadNotifications()} /> :
          notifications.length === 0 ? <EmptyState title="All caught up"
            message="New connection and activity alerts will show here." /> :
            notifications.map((notification) => (
              <View key={notification.id}
                style={[styles.notification, !notification.is_read && styles.unread]}>
                <View style={[styles.dot, !notification.is_read && styles.activeDot]} />
                <View style={styles.copy}>
                  <Text style={styles.kind}>{notification.notification_type_display || 'Awinlink update'}</Text>
                  <Text style={styles.message}>{notification.message}</Text>
                  <Text style={styles.sender}>
                    {notification.sender_name || `@${notification.sender_username || 'awinlink'}`}
                  </Text>
                  {!notification.is_read && (
                    <Pressable accessibilityRole="button" disabled={working}
                      onPress={() => void markRead(notification.id)}>
                      <Text style={styles.markRead}>{working ? 'Updating...' : 'Mark as read'}</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            ))
      }
    </Page>
  );
}

const styles = StyleSheet.create({
  loader: { marginTop: 28 },
  notification: { alignItems: 'flex-start', backgroundColor: colors.surface, borderColor: colors.border,
    borderRadius: 16, borderWidth: 1, flexDirection: 'row', gap: 12, padding: 15 },
  unread: { backgroundColor: '#f1f6ff', borderColor: '#d8e5ff' },
  dot: { backgroundColor: '#d9e0ea', borderRadius: 5, height: 9, marginTop: 5, width: 9 },
  activeDot: { backgroundColor: colors.primary },
  copy: { flex: 1, gap: 5 },
  kind: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase' },
  message: { color: colors.ink, fontSize: 14, lineHeight: 20 },
  sender: { color: colors.muted, fontSize: 11 },
  markAll: { alignSelf: 'flex-end', paddingVertical: 5 },
  markAllText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  markRead: { color: colors.primary, fontSize: 12, fontWeight: '700', paddingTop: 3 },
  disabled: { opacity: 0.6 },
  error: { color: colors.danger, fontSize: 12 },
});
