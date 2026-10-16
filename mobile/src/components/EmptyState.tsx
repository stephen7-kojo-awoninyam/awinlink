import { Pressable, StyleSheet, Text, View } from 'react-native';

import { colors } from '@/src/theme';
import { ui } from '@/src/components/Page';

type EmptyStateProps = {
  title: string;
  message: string;
  actionLabel?: string;
  onAction?: () => void;
};

export function EmptyState({
  title,
  message,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  return (
    <View style={styles.container}>
      <View style={styles.mark}>
        <Text style={styles.markText}>A</Text>
      </View>
      <Text style={styles.title}>{title}</Text>
      <Text style={styles.message}>{message}</Text>
      {!!actionLabel && !!onAction && (
        <Pressable onPress={onAction} style={ui.primaryButton}>
          <Text style={ui.primaryButtonText}>{actionLabel}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    gap: 10,
    paddingHorizontal: 22,
    paddingVertical: 28,
  },
  mark: {
    alignItems: 'center',
    backgroundColor: colors.softBlue,
    borderRadius: 20,
    height: 48,
    justifyContent: 'center',
    width: 48,
  },
  markText: { color: colors.primary, fontSize: 23, fontWeight: '800' },
  title: { color: colors.ink, fontSize: 16, fontWeight: '800', textAlign: 'center' },
  message: { color: colors.muted, fontSize: 13, lineHeight: 20, textAlign: 'center' },
});
