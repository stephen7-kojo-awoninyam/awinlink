import type { PropsWithChildren, ReactNode } from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  type ScrollViewProps,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors } from '@/src/theme';

type PageProps = PropsWithChildren<{
  title: string;
  eyebrow?: string;
  right?: ReactNode;
  scroll?: boolean;
  refreshControl?: ScrollViewProps['refreshControl'];
}>;

export function Page({
  title,
  eyebrow,
  right,
  scroll = true,
  refreshControl,
  children,
}: PageProps) {
  const content = (
    <>
      <View style={styles.header}>
        <View style={styles.titleGroup}>
          {!!eyebrow && <Text style={styles.eyebrow}>{eyebrow}</Text>}
          <Text style={styles.title}>{title}</Text>
        </View>
        {right}
      </View>
      {children}
    </>
  );

  return (
    <SafeAreaView edges={['top']} style={styles.safeArea}>
      {scroll ? (
        <ScrollView
          contentContainerStyle={styles.content}
          keyboardShouldPersistTaps="handled"
          refreshControl={refreshControl}
          showsVerticalScrollIndicator={false}
        >
          {content}
        </ScrollView>
      ) : (
        <View style={[styles.content, styles.fullHeight]}>{content}</View>
      )}
    </SafeAreaView>
  );
}

export const ui = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderColor: colors.border,
    borderRadius: 18,
    borderWidth: 1,
    padding: 16,
  },
  primaryButton: {
    alignItems: 'center',
    backgroundColor: colors.primary,
    borderRadius: 12,
    justifyContent: 'center',
    minHeight: 48,
    paddingHorizontal: 16,
  },
  primaryButtonText: { color: '#fff', fontSize: 14, fontWeight: '800' },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
});

const styles = StyleSheet.create({
  safeArea: { backgroundColor: colors.background, flex: 1 },
  content: { gap: 16, padding: 20, paddingBottom: 28 },
  fullHeight: { flex: 1 },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 3,
    minHeight: 44,
  },
  titleGroup: { flex: 1, gap: 3 },
  eyebrow: { color: colors.primary, fontSize: 10, fontWeight: '800', letterSpacing: 1.4 },
  title: { color: colors.ink, fontSize: 27, fontWeight: '800', letterSpacing: -0.5 },
});
